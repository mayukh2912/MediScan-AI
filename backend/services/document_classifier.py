"""Report-type detection with transparent keyword scoring.

A lab report frequently contains several panels (e.g. CBC + LFT + lipid on one page), so we
return every panel whose evidence passes a threshold, plus a primary type. The scoring is
deterministic and the matched keywords are returned so the user can see why a type was chosen.
"""
from __future__ import annotations

import re

PANEL_KEYWORDS: dict[str, dict[str, float]] = {
    "ECG": {
        r"\becg\b|\bekg\b|electrocardiogra": 4, r"\bqrs\b": 2, r"\bqtc?\b": 2, r"\bpr interval\b": 2,
        r"\b(?:avr|avl|avf)\b": 2, r"\bv[1-6]\b": 1, r"sinus rhythm": 2, r"25\s*mm/s": 2, r"10\s*mm/mv": 2,
        r"\bp axis\b|\bqrs axis\b": 2, r"\brate\b": 0.5,
    },
    "ECHO": {
        r"echocardiogra|\b2d echo\b|\becho\b": 4, r"ejection fraction|\blvef\b|\bef\b": 3,
        r"\blvid[ds]?\b": 3, r"\bivs[d]?\b": 2, r"\blvpw[d]?\b": 2, r"mitral|tricuspid|aortic valve|pulmonary valve": 2,
        r"regurgitation|stenosis": 1.5, r"wall motion|hypokinesi|akinesi": 2, r"diastolic (?:dys)?function": 2,
        r"\btapse\b": 2, r"\bla\b.*\bcm\b|left atri": 1, r"doppler": 1.5, r"e/a|e/e'": 1.5, r"pericardial": 1,
    },
    "CBC": {
        r"complete blood count|\bcbc\b|haemogram|hemogram": 4, r"ha?emoglobin|\bhb\b|\bhgb\b": 2,
        r"\brbc\b|red blood cell|red cell count|erythrocyte": 1.5, r"\bwbc\b|white blood cell|leucocyte|leukocyte|\btlc\b": 2,
        r"platelet|\bplt\b": 2, r"\bmcv\b": 2, r"\bmch\b": 1.5, r"\bmchc\b": 1.5, r"\brdw": 1.5,
        r"ha?ematocrit|\bhct\b|\bpcv\b": 1.5, r"neutrophil|lymphocyte|monocyte|eosinophil|basophil": 1,
    },
    "IRON_VITAMIN": {
        r"ferritin": 3, r"vitamin\s*b\s*12|cobalamin|\bb12\b": 3, r"folate|folic acid": 3, r"\btibc\b|transferrin": 2,
        r"serum iron": 2,
    },
    "LFT": {
        r"liver function|\blft\b": 4, r"\balt\b|\bsgpt\b|alanine amino": 2.5, r"\bast\b|\bsgot\b|aspartate amino": 2.5,
        r"alkaline phosphatase|\balp\b": 2, r"bilirubin": 2.5, r"albumin": 1.5, r"globulin": 1.5,
        r"\ba\s*/\s*g ratio\b": 2, r"total protein": 1.5, r"\bggt\b|gamma.?glutamyl": 1.5,
    },
    "LIPID": {
        r"lipid profile|lipid panel|lipidogram": 4, r"cholesterol": 2.5, r"\bhdl\b": 2.5, r"\bldl\b": 2.5,
        r"\bvldl\b": 2, r"triglyceride": 2.5, r"non.?hdl": 1.5,
    },
}
THRESHOLD = 5.0
BLOOD_TYPES = {"CBC", "IRON_VITAMIN"}


def classify_document(text: str) -> dict:
    t = text.lower()
    scores, evidence = {}, {}
    for panel, kws in PANEL_KEYWORDS.items():
        s, hits = 0.0, []
        for pat, w in kws.items():
            n = len(re.findall(pat, t))
            if n:
                s += w * min(n, 3) ** 0.5  # diminishing returns for repeated words
                hits.append(re.findall(pat, t)[0] if isinstance(re.findall(pat, t)[0], str) else pat)
        scores[panel] = round(s, 2)
        evidence[panel] = hits[:8]
    # ECHO vs ECG disambiguation: an ECHO report often mentions "ECG" once in the history.
    if scores["ECHO"] >= THRESHOLD and scores["ECG"] < 2 * scores["ECHO"]:
        scores["ECG"] = min(scores["ECG"], THRESHOLD - 0.01) if scores["ECHO"] > scores["ECG"] else scores["ECG"]
    panels = [p for p, s in sorted(scores.items(), key=lambda kv: -kv[1]) if s >= THRESHOLD]
    if not panels:
        primary = "UNKNOWN"
    else:
        primary = panels[0]
        if primary == "IRON_VITAMIN":
            primary = "BLOOD"
    total = sum(scores.values()) or 1.0
    confidence = round(scores.get(panels[0], 0) / total, 3) if panels else 0.0
    return {
        "report_type": primary,
        "panels": panels,
        "scores": scores,
        "evidence": {p: evidence[p] for p in panels},
        "confidence": confidence,
        "method": "keyword scoring (deterministic); user can override",
    }
