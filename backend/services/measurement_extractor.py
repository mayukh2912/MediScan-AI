"""Deterministic measurement extraction from OCR lines.

For every line we look for known analyte names (with common lab synonyms), then parse the
first number after the name, the unit right after it, an optional lab flag (H/L/*) and an
optional reference range. Nothing is ever filled in from defaults: a field that cannot be
read is reported as missing.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from backend.services.units import DISPLAY, convert, find_unit


@dataclass
class Analyte:
    key: str
    name: str
    panel: str
    canonical_unit: str
    aliases: str
    exclude: str | None = None


CATALOG: list[Analyte] = [
    # --- CBC / blood
    Analyte("hemoglobin", "Hemoglobin", "CBC", "g/dL", r"ha?emoglobin|\bhb\b|\bhgb\b", r"a\s*1\s*c|glycat|mean corpuscular|\bmch|plasma free"),
    Analyte("rbc", "RBC count", "CBC", "10^6/uL", r"\brbc\b|red blood cells?(?: count)?|red cell count|r\.b\.c|erythrocyte count|\btotal rbc", r"nucleated|nrbc|morpholog|distribution"),
    Analyte("wbc", "WBC count", "CBC", "10^3/uL", r"\bwbc\b|total leu[ck]ocyte count|\btlc\b|white blood cells?(?: count)?|total wbc|leu[ck]ocyte count|\btotal count\b", r"differential|\bdlc\b"),
    Analyte("platelets", "Platelet count", "CBC", "10^3/uL", r"platelet count|platelets?|\bplt\b", r"mean platelet|\bmpv\b|\bpdw\b|\bpct\b|plateletcrit|large"),
    Analyte("mcv", "MCV", "CBC", "fL", r"\bmcv\b|mean corpuscular volume|mean cell volume"),
    Analyte("mch", "MCH", "CBC", "pg", r"\bmch\b(?!c)|mean corpuscular ha?emoglobin(?!\s*conc)|mean cell ha?emoglobin(?!\s*conc)", r"\bmchc\b|concentration"),
    Analyte("mchc", "MCHC", "CBC", "g/dL", r"\bmchc\b|mean corpuscular ha?emoglobin conc|mean cell ha?emoglobin conc"),
    Analyte("rdw", "RDW", "CBC", "%", r"\brdw(?:[\s-]*cv)?\b|red cell distribution width", r"rdw[\s-]*sd"),
    Analyte("hematocrit", "Hematocrit", "CBC", "%", r"ha?ematocrit|\bhct\b|\bpcv\b|packed cell volume"),
    Analyte("ferritin", "Ferritin", "BLOOD", "ng/mL", r"ferritin"),
    Analyte("vitamin_b12", "Vitamin B12", "BLOOD", "pg/mL", r"vitamin\s*b\s*-?\s*12|\bb\s*12\b|cobalamin"),
    Analyte("folate", "Folate", "BLOOD", "ng/mL", r"folate|folic acid", r"rbc folate|red cell folate"),
    # --- LFT
    Analyte("alt", "ALT (SGPT)", "LFT", "U/L", r"\balt\b|\bsgpt\b|alanine\s*(?:amino)?\s*transaminase|alanine aminotransferase", r"ratio|\bast\s*/"),
    Analyte("ast", "AST (SGOT)", "LFT", "U/L", r"\bast\b|\bsgot\b|aspartate\s*(?:amino)?\s*transaminase|aspartate aminotransferase", r"ratio|/\s*alt|/\s*sgpt"),
    Analyte("alp", "ALP", "LFT", "U/L", r"alkaline phosphatase|\balp\b|\balk\.?\s*phos"),
    Analyte("total_bilirubin", "Total bilirubin", "LFT", "mg/dL", r"(?:total|t\.)\s*bilirubin|bilirubin[\s,(-]*total|s\.?\s*bilirubin\s*\(?t", r"direct|indirect|conjugated"),
    Analyte("direct_bilirubin", "Direct bilirubin", "LFT", "mg/dL", r"direct bilirubin|bilirubin[\s,(-]*direct|conjugated bilirubin", r"indirect|unconjugated"),
    Analyte("indirect_bilirubin", "Indirect bilirubin", "LFT", "mg/dL", r"indirect bilirubin|bilirubin[\s,(-]*indirect|unconjugated bilirubin"),
    Analyte("albumin", "Albumin", "LFT", "g/dL", r"\balbumin\b", r"ratio|globulin|micro|urine"),
    Analyte("total_protein", "Total protein", "LFT", "g/dL", r"total proteins?|proteins?[\s,(-]*total|serum protein", r"urine"),
    Analyte("globulin", "Globulin", "LFT", "g/dL", r"\bglobulin\b", r"ratio|albumin\s*/|a\s*/\s*g|thyroxine|binding"),
    Analyte("ag_ratio", "A/G ratio", "LFT", "", r"a\s*/\s*g\s*ratio|albumin\s*/\s*globulin|alb\s*/\s*glob|\ba:g\b"),
    # --- Lipid
    Analyte("total_cholesterol", "Total cholesterol", "LIPID", "mg/dL", r"total cholesterol|cholesterol[\s,(-]*total|serum cholesterol|\bcholesterol\b", r"hdl|ldl|vldl|ratio|/|non"),
    Analyte("hdl", "HDL cholesterol", "LIPID", "mg/dL", r"\bhdl\b|high[\s-]density lipoprotein", r"non[\s-]*hdl|ratio|/"),
    Analyte("ldl", "LDL cholesterol", "LIPID", "mg/dL", r"\bldl\b|low[\s-]density lipoprotein", r"ratio|/|\bvldl\b|very low"),
    Analyte("vldl", "VLDL cholesterol", "LIPID", "mg/dL", r"\bvldl\b|very low[\s-]density", r"ratio|/"),
    Analyte("triglycerides", "Triglycerides", "LIPID", "mg/dL", r"triglycerides?|\btg\b|\btgl\b", r"ratio|/"),
    Analyte("non_hdl", "Non-HDL cholesterol", "LIPID", "mg/dL", r"non[\s-]*hdl"),
    # --- ECHO numeric
    Analyte("ef", "LV ejection fraction", "ECHO", "%", r"ejection fraction|\blvef\b|\bl\.?v\.?\s*e\.?f\b|\bef\b"),
    Analyte("lvidd", "LVIDd", "ECHO", "cm", r"lvid\s*\(?\s*d\b\)?|\blvidd\b|\blvedd\b|lv internal (?:dimension|diameter)[^\d]{0,12}diast"),
    Analyte("lvids", "LVIDs", "ECHO", "cm", r"lvid\s*\(?\s*s\b\)?|\blvids\b|\blvesd\b|lv internal (?:dimension|diameter)[^\d]{0,12}syst"),
    Analyte("ivsd", "IVSd", "ECHO", "cm", r"ivs\s*\(?\s*d\b\)?|\bivsd\b|interventricular septum", r"ivs\s*\(?\s*s\b"),
    Analyte("lvpwd", "LVPWd", "ECHO", "cm", r"lvpw\s*\(?\s*d\b\)?|\blvpwd\b|posterior wall", r"lvpw\s*\(?\s*s\b"),
    Analyte("la_diameter", "Left atrium (diameter)", "ECHO", "cm", r"\bla\b(?!\s*vol)(?:\s*(?:dimension|diameter|size))?|left atri(?:um|al)(?:\s*(?:dimension|diameter|size))?|\blad\b", r"volume|area|index"),
    Analyte("aortic_root", "Aortic root", "ECHO", "cm", r"aortic root|\bao\b(?:\s*root)?", r"valve|velocity|gradient"),
    Analyte("rv_diameter", "RV diameter", "ECHO", "cm", r"\brv\b(?:\s*(?:dimension|diameter|basal))?|\brvid\b|right ventric\w*\s*(?:dimension|diameter)", r"rvsp|systolic pressure|function|tapse"),
    Analyte("tapse", "TAPSE", "ECHO", "cm", r"\btapse\b"),
    Analyte("e_a_ratio", "Mitral E/A ratio", "ECHO", "", r"\be\s*/\s*a\b(?:\s*ratio)?"),
    Analyte("e_e_prime", "E/e' ratio", "ECHO", "", r"\be\s*/\s*e\s*['’`′]"),
    Analyte("rvsp", "RVSP / PASP", "ECHO", "mmHg", r"\brvsp\b|\bpasp\b|pa systolic pressure|pulmonary artery systolic pressure"),
]
CATALOG_BY_KEY = {a.key: a for a in CATALOG}
_ALIAS = {a.key: re.compile(a.aliases, re.I) for a in CATALOG}
_EXCL = {a.key: re.compile(a.exclude, re.I) for a in CATALOG if a.exclude}

PANEL_FIELDS = {
    "CBC": ["hemoglobin", "rbc", "wbc", "platelets", "mcv", "mch", "mchc", "rdw", "hematocrit"],
    "BLOOD": ["ferritin", "vitamin_b12", "folate"],
    "LFT": ["alt", "ast", "alp", "total_bilirubin", "direct_bilirubin", "indirect_bilirubin", "albumin",
            "total_protein", "globulin", "ag_ratio"],
    "LIPID": ["total_cholesterol", "hdl", "ldl", "vldl", "triglycerides"],
    "ECHO": ["ef", "lvidd", "lvids", "ivsd", "lvpwd", "la_diameter", "aortic_root", "rv_diameter", "tapse",
             "e_a_ratio", "e_e_prime", "rvsp"],
}

NUM = r"(?<![\w.])(?:[<>≤≥]\s*)?\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|(?<![\w.])(?:[<>≤≥]\s*)?\d+(?:[.,]\d+)?"
NUM_RX = re.compile(NUM)
RANGE_RX = re.compile(
    r"(?P<lo>\d+(?:[.,]\d+)?)\s*(?:-|–|—|to)\s*(?P<hi>\d+(?:[.,]\d+)?)"
    r"|(?P<op><|>|≤|≥|<=|>=|up\s*to|upto|less than|more than|below|above)\s*(?P<v>\d+(?:[.,]\d+)?)",
    re.I,
)
FLAG_RX = re.compile(r"^\s*[\[(]?\s*(H|L|HIGH|LOW|\*+|A|ABN|CRIT(?:ICAL)?)\b[\])]?", re.I)
OCR_DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "S": "5", "B": "8"})


@dataclass
class Measurement:
    test: str
    key: str
    panel: str
    value: float | None
    unit: str
    original_value: str | None
    original_unit: str | None
    reference_range: dict | None
    lab_flag: str | None
    extraction_confidence: float
    status: str = "ok"  # ok | uncertain | invalid | missing
    issues: list[str] = field(default_factory=list)
    source_line: str | None = None
    page: int | None = None
    origin: str = "ocr"  # ocr | pdf_text | manual | derived
    lab_calculated: bool = False

    def as_dict(self):
        d = asdict(self)
        d["unit_display"] = DISPLAY.get(self.unit, self.unit)
        return d


def _parse_number(tok: str) -> tuple[float | None, str | None, bool]:
    """Returns (value, comparator, was_fixed)."""
    s = tok.strip()
    comp = None
    if s[:1] in "<>≤≥":
        comp, s = s[:1], s[1:].strip()
    fixed = False
    if re.fullmatch(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?", s):  # 2,50,000 / 7,500
        s = s.replace(",", "")
    elif re.fullmatch(r"\d+,\d{1,2}", s):  # decimal comma 10,5
        s, fixed = s.replace(",", "."), True
    try:
        return float(s), comp, fixed
    except ValueError:
        return None, comp, fixed


def _fix_ocr_digits(text: str) -> str:
    # Replace O/l/I/S/B only when sandwiched between digits / decimal points ("1O.5" -> "10.5")
    return re.sub(r"(?<=[\d.])[OolISB](?=[\d.])|(?<=\s)[Ol](?=\.\d)", lambda m: m.group(0).translate(OCR_DIGIT_FIX), text)


def _parse_after_alias(rest: str) -> dict | None:
    rest = _fix_ocr_digits(rest)
    # skip label noise such as "(SGPT)", ":", "-" and method names like "(Calculated)"
    m = NUM_RX.search(rest)
    if not m:
        return None
    prefix = rest[: m.start()]
    if re.search(r"\d", prefix):
        return None
    if len(prefix) > 60:  # value too far from the label: probably a different column/line
        return None
    raw = m.group(0)
    val, comp, fixed = _parse_number(raw)
    if val is None:
        return None
    after = rest[m.end():]
    # a range such as "13.0 - 17.0" immediately after the label is a reference range, not a value
    if re.match(r"\s*(?:-|–|to)\s*\d", after):
        return None
    flag = None
    fm = FLAG_RX.match(after)
    unit_key, unit_txt, uend = find_unit(after)
    if fm and (unit_key is None or fm.end() <= after.find(unit_txt)):
        flag = fm.group(1).upper()
    tail = after[uend:] if unit_key else after
    if fm and not unit_key:
        tail = after[fm.end():]
    rng = None
    rm = RANGE_RX.search(tail)
    if rm:
        if rm.group("lo"):
            lo, _, _ = _parse_number(rm.group("lo"))
            hi, _, _ = _parse_number(rm.group("hi"))
            if lo is not None and hi is not None and lo <= hi:
                rng = {"low": lo, "high": hi, "text": rm.group(0).strip()}
        else:
            v, _, _ = _parse_number(rm.group("v"))
            op = rm.group("op").lower().replace(" ", "")
            if v is not None:
                if op in ("<", "≤", "<=", "upto", "lessthan", "below"):
                    rng = {"low": None, "high": v, "text": rm.group(0).strip()}
                else:
                    rng = {"low": v, "high": None, "text": rm.group(0).strip()}
    return {"raw": raw, "value": val, "comparator": comp, "decimal_comma_fixed": fixed,
            "unit_key": unit_key, "unit_text": unit_txt, "flag": flag, "range": rng}


def _convert_range(key: str, rng: dict | None, unit_key: str | None) -> dict | None:
    if not rng:
        return None
    out = dict(rng)
    for b in ("low", "high"):
        if out.get(b) is not None:
            v, st = convert(key, out[b], unit_key)
            out[b] = round(v, 4) if v is not None else None
    out["unit_basis"] = "canonical"
    return out


def extract_measurements(lines: list[dict], panels: list[str] | None = None) -> list[Measurement]:
    """lines: [{'text', 'confidence', 'page', 'source'}]. Returns one Measurement per analyte found
    (the highest-confidence candidate if an analyte appears several times)."""
    found: dict[str, list[Measurement]] = {}
    for ln in lines:
        # OCR often glues an abbreviation to its value ("LA4.2cm"); separate letters from a decimal number
        text = re.sub(r"\b([A-Za-z]{2,6})(?=\d+[.,]\d)", r"\1 ", ln["text"])
        for a in CATALOG:
            # ECHO abbreviations (LA, RV, EF, Ao) are short and ambiguous, so they are only
            # searched for when the document was classified as an ECHO report.
            if a.panel == "ECHO" and panels is not None and "ECHO" not in panels:
                continue
            m = _ALIAS[a.key].search(text)
            if not m:
                continue
            # exclusion words are only checked in the label part (before the value), not in units
            nm = NUM_RX.search(text, m.end())
            label_part = text[: nm.start()] if nm else text
            if a.key in _EXCL and _EXCL[a.key].search(label_part):
                continue
            parsed = _parse_after_alias(text[m.end():])
            if not parsed:
                continue
            conf = float(ln.get("confidence", 0.5))
            issues = []
            canon, ustatus = convert(a.key, parsed["value"], parsed["unit_key"])
            if ustatus == "unit_missing":
                issues.append("Unit not found on the report line")
                conf -= 0.2
            elif ustatus == "unit_mismatch":
                issues.append(f"Unit '{parsed['unit_text']}' is not valid for {a.name}")
                conf -= 0.3
            elif ustatus == "converted":
                issues.append(f"Converted from {DISPLAY.get(parsed['unit_key'], parsed['unit_key'])} to {DISPLAY.get(a.canonical_unit, a.canonical_unit)}")
            if parsed["comparator"]:
                issues.append(f"Reported as a bound ('{parsed['comparator']}{parsed['raw']}') rather than an exact value")
                conf -= 0.1
            if parsed["decimal_comma_fixed"]:
                issues.append("Decimal comma interpreted as a decimal point")
                conf -= 0.1
            rng = _convert_range(a.key, parsed["range"], parsed["unit_key"]) if canon is not None else None
            meas = Measurement(
                test=a.name, key=a.key, panel=a.panel,
                value=round(canon, 4) if canon is not None else None,
                unit=a.canonical_unit,
                original_value=parsed["raw"], original_unit=parsed["unit_text"],
                reference_range=rng, lab_flag=parsed["flag"],
                extraction_confidence=round(max(0.0, min(1.0, conf)), 3),
                issues=issues, source_line=text, page=ln.get("page"),
                origin="pdf_text" if str(ln.get("source", "")).startswith("pdf") else "ocr",
                lab_calculated=bool(re.search(r"calculat|derived|friedewald", text, re.I)),
            )
            found.setdefault(a.key, []).append(meas)
    out = []
    for key, cands in found.items():
        # prefer candidates with a unit and higher confidence
        cands.sort(key=lambda c: (c.value is not None, c.original_unit is not None, c.extraction_confidence), reverse=True)
        best = cands[0]
        distinct = {c.value for c in cands if c.value is not None}
        if len(distinct) > 1:
            best.issues.append(f"Multiple different values found for {best.test}: {sorted(distinct)}")
            best.extraction_confidence = round(best.extraction_confidence * 0.8, 3)
        out.append(best)
    order = {a.key: i for i, a in enumerate(CATALOG)}
    return sorted(out, key=lambda m: order[m.key])


# ------------------------------------------------------------------ dates & demographics

DATE_PATTERNS = [
    (r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", "ymd"),
    (r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", "dmy"),
    (r"\b(\d{1,2})[\s-]([A-Za-z]{3,9})[\s,-]+(\d{4})\b", "dMy"),
]
DATE_LABELS = [r"report(?:ed)?\s*(?:on|date)|date of report", r"collect(?:ed|ion)|sample(?:\s*date)?|received|registered", r"\bdate\b"]


def extract_report_date(lines: list[dict]) -> dict | None:
    def parse(s: str):
        for pat, kind in DATE_PATTERNS:
            m = re.search(pat, s)
            if not m:
                continue
            try:
                if kind == "ymd":
                    d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    amb = False
                elif kind == "dmy":
                    a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    d = datetime(y, b, a)  # day-first convention (India/UK/EU)
                    amb = a <= 12 and b <= 12 and a != b
                else:
                    d = datetime.strptime(f"{m.group(1)} {m.group(2)[:3]} {m.group(3)}", "%d %b %Y")
                    amb = False
                if 1950 <= d.year <= datetime.now().year + 1:
                    return d.date().isoformat(), amb, m.group(0)
            except ValueError:
                continue
        return None

    for label in DATE_LABELS:
        for ln in lines:
            if re.search(label, ln["text"], re.I):
                p = parse(ln["text"])
                if p:
                    return {"date": p[0], "ambiguous_day_month": p[1], "original": p[2],
                            "label": re.search(label, ln["text"], re.I).group(0)}
    return None


def extract_demographics(lines: list[dict]) -> dict:
    """Only age and sex (needed for sex-specific reference ranges and the liver research model).
    Names, IDs, addresses and phone numbers are deliberately never extracted."""
    age = sex = None
    for ln in lines:
        t = ln["text"]
        if age is None:
            m = re.search(r"\bage\b[^\d]{0,12}(\d{1,3})\s*(?:y|yrs?|years?)?", t, re.I) or \
                re.search(r"\b(\d{1,3})\s*(?:y|yrs?|years?)\s*/\s*[mf]", t, re.I)
            if m and 0 < int(m.group(1)) < 110:
                age = int(m.group(1))
        if sex is None:
            m = re.search(r"\b(?:sex|gender)\b\s*[:\-]?\s*(male|female|m|f)\b", t, re.I) or \
                re.search(r"\d{1,3}\s*(?:y|yrs?|years?)\s*/\s*(male|female|m|f)\b", t, re.I)
            if m:
                sex = "male" if m.group(1).lower().startswith("m") else "female"
    return {"age": age, "sex": sex}


# ------------------------------------------------------------------ ECHO narrative findings

def extract_echo_findings(lines: list[dict]) -> dict:
    text_lines = [l["text"].strip() for l in lines if l["text"].strip()]
    seen, uniq = set(), []
    for t in text_lines:
        if t.lower() not in seen:
            seen.add(t.lower()); uniq.append(t)
    valves = {}
    for valve in ("mitral", "aortic", "tricuspid", "pulmonary"):
        hits = [t for t in uniq if re.search(rf"\b{valve}\b", t, re.I)
                and re.search(r"valve|regurg|stenosis|prolapse|sclero|thicken|calcif|normal|\b[MATP]R\b|\b[MATP]S\b|leaflet", t, re.I)
                and not re.search(r"root|annulus diameter", t, re.I)]
        if hits:
            valves[valve] = hits[:4]
    wall = [t for t in uniq if re.search(r"wall motion|rwma|hypokines|akines|dyskines", t, re.I)]
    diastolic = [t for t in uniq if re.search(r"diastolic|relaxation|grade\s*[i1-3]+\s*dd|filling pressure", t, re.I)]
    pericardium = [t for t in uniq if re.search(r"pericardial|effusion", t, re.I)]
    impression = []
    start = None
    for i, t in enumerate(uniq):
        if re.search(r"^\s*(final\s+)?(impression|conclusion|summary|interpretation)\b", t, re.I):
            start = i
            rest = re.sub(r"^\s*(final\s+)?(impression|conclusion|summary|interpretation)\s*[:\-]?\s*", "", t, flags=re.I)
            if rest:
                impression.append(rest)
            continue
        if start is not None:
            if re.search(r"^(signature|dr\.|doctor|consultant|reported by|end of report)", t, re.I) or len(impression) >= 12:
                break
            impression.append(t)
    qualitative_lv = [t for t in uniq if re.search(r"(normal|good|fair|mild(ly)?|moderate(ly)?|severe(ly)?)\s+(lv|left ventricular)\s+(systolic\s+)?(function|dysfunction)|lv(\s+systolic)?\s+function", t, re.I)]
    return {
        "valve_findings": valves,
        "wall_motion": wall[:5],
        "diastolic_function": diastolic[:5],
        "pericardium": pericardium[:3],
        "lv_function_text": qualitative_lv[:3],
        "impression": impression,
        "note": "Narrative findings are quoted verbatim from the report and are not re-interpreted.",
    }
