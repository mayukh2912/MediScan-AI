"""CBC / haematinic rule-based analysis.

There is no ML model here on purpose: we did not find a public, properly labelled dataset in
which anaemia subtypes were confirmed independently of the CBC indices themselves (several
Kaggle "anaemia" datasets derive their label from the same Hb/MCV thresholds, which would make a
model merely re-learn the rule). All logic below is transparent and each finding cites its rule.
"""
from __future__ import annotations

from backend.services.analyzers.common import assess_all, by_key, missing_fields

CBC_FIELDS = ["hemoglobin", "rbc", "wbc", "platelets", "mcv", "mch", "mchc", "rdw", "hematocrit"]
HAEMATINIC_FIELDS = ["ferritin", "vitamin_b12", "folate"]

DISCLAIMER = ("These are laboratory patterns that require clinical context. A CBC alone cannot diagnose iron, "
              "vitamin B12 or folate deficiency; confirmatory tests and a clinician's assessment are needed.")


def analyze_blood(measurements: list[dict], sex: str | None = None) -> dict:
    assessed = assess_all([m for m in measurements if m["key"] in CBC_FIELDS + HAEMATINIC_FIELDS], sex)
    b = by_key(assessed)

    def interp(k):
        return b[k]["assessment"]["interpretation"] if k in b else None

    def val(k):
        return b[k]["value"] if k in b else None

    patterns, derived = [], []

    if val("mcv") and val("rbc"):
        mentzer = val("mcv") / val("rbc")
        derived.append({
            "name": "Mentzer index (derived)", "value": round(mentzer, 2), "unit": "",
            "formula": "MCV (fL) / RBC (×10⁶/µL)",
            "note": "Screening heuristic only when microcytosis is present: <13 is more often seen with thalassaemia trait, "
                    ">13 with iron deficiency. Limited sensitivity/specificity; not diagnostic.",
            "applicable": interp("mcv") == "low",
        })

    low_hb = interp("hemoglobin") == "low"
    if low_hb:
        sev = None
        hb = val("hemoglobin")
        # WHO 2011 severity bands for non-pregnant adults
        if hb is not None:
            sev = "severe (<8 g/dL)" if hb < 8 else ("moderate (8–10.9 g/dL)" if hb < 11 else "mild")
        patterns.append({
            "pattern": "Low haemoglobin",
            "evidence": [b["hemoglobin"]["assessment"]["rule"]],
            "explanation": f"Haemoglobin is below the range used. WHO severity band: {sev}. "
                           "Anaemia has many causes; red cell indices help narrow them.",
            "rule": "Hb < lower limit of range used (WHO 2011 bands for severity)",
        })
        if interp("mcv") == "low":
            ev = [b["mcv"]["assessment"]["rule"]]
            if interp("mch") == "low":
                ev.append(b["mch"]["assessment"]["rule"])
            if interp("rdw") == "high":
                ev.append(b["rdw"]["assessment"]["rule"])
            patterns.append({
                "pattern": "Microcytic (± hypochromic) anaemia pattern",
                "evidence": ev,
                "explanation": "Low Hb with low MCV is commonly seen with iron deficiency, thalassaemia trait, "
                               "anaemia of chronic disease or sideroblastic anaemia. A raised RDW is more typical of iron "
                               "deficiency but is not specific. Iron studies (ferritin) are needed to assess iron status.",
                "rule": "Hb low AND MCV low",
            })
        elif interp("mcv") == "high":
            patterns.append({
                "pattern": "Macrocytic anaemia pattern",
                "evidence": [b["mcv"]["assessment"]["rule"]],
                "explanation": "Low Hb with high MCV can be associated with vitamin B12 or folate deficiency, but also "
                               "with alcohol use, liver disease, hypothyroidism, reticulocytosis and some medicines. "
                               "B12 and folate levels are needed.",
                "rule": "Hb low AND MCV high",
            })
        elif interp("mcv") == "within_range":
            patterns.append({
                "pattern": "Normocytic anaemia pattern",
                "evidence": [b["mcv"]["assessment"]["rule"]],
                "explanation": "Low Hb with normal MCV has a broad differential (e.g. acute blood loss, chronic disease, "
                               "kidney disease, mixed deficiencies).",
                "rule": "Hb low AND MCV within range",
            })

    # Haematinic markers (only when actually measured)
    if interp("ferritin") == "low":
        patterns.append({
            "pattern": "Low ferritin",
            "evidence": [b["ferritin"]["assessment"]["rule"]],
            "explanation": "Low serum ferritin is a specific marker of depleted iron stores (WHO 2020). "
                           "Interpretation by a clinician is still required.",
            "rule": "Ferritin < lower limit of range used",
        })
    elif "ferritin" in b and low_hb and interp("mcv") == "low":
        patterns.append({
            "pattern": "Ferritin not low despite microcytosis",
            "evidence": [b["ferritin"]["assessment"]["rule"]],
            "explanation": "Ferritin rises with inflammation, so a normal value does not exclude iron deficiency; "
                           "other causes of microcytosis (e.g. thalassaemia trait) may also be considered by a clinician.",
            "rule": "Ferritin ≥ lower limit AND Hb low AND MCV low",
        })
    if interp("vitamin_b12") == "low":
        patterns.append({"pattern": "Low vitamin B12", "evidence": [b["vitamin_b12"]["assessment"]["rule"]],
                         "explanation": "Below the range used. Borderline results may need methylmalonic acid testing.",
                         "rule": "B12 < lower limit of range used"})
    if interp("folate") == "low":
        patterns.append({"pattern": "Low folate", "evidence": [b["folate"]["assessment"]["rule"]],
                         "explanation": "Below the range used. Serum folate reflects recent dietary intake.",
                         "rule": "Folate < lower limit of range used"})

    for k, label_low, label_high in (("wbc", "Low WBC (leukopenia range)", "High WBC (leukocytosis range)"),
                                     ("platelets", "Low platelets (thrombocytopenia range)", "High platelets (thrombocytosis range)")):
        if interp(k) in ("low", "high"):
            patterns.append({"pattern": label_low if interp(k) == "low" else label_high,
                             "evidence": [b[k]["assessment"]["rule"]],
                             "explanation": "Outside the range used; significance depends on the clinical context and trend.",
                             "rule": f"{k} outside range used"})

    return {
        "module": "blood",
        "method": "rule-based (no ML model; see docs/DATASETS.md)",
        "measurements": assessed,
        "derived": derived,
        "patterns": patterns,
        "missing": missing_fields(measurements, CBC_FIELDS + HAEMATINIC_FIELDS),
        "missing_haematinics_note": None if all(k in b for k in HAEMATINIC_FIELDS)
        else "Ferritin, vitamin B12 and/or folate were not provided, so nutritional deficiencies cannot be assessed.",
        "disclaimer": DISCLAIMER,
    }
