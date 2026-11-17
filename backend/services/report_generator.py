"""Combined health summary (JSON) and downloadable PDF.

No overall "health score" is produced: we are not aware of a validated method to combine these
heterogeneous modules into one number.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DISCLAIMER = ("MediScan AI is an educational research prototype. It is not a medical device, has not been clinically "
              "validated and does not provide diagnoses. Clinical interpretation must be performed by a qualified "
              "healthcare professional.")
MODULE_LABEL = {"blood": "Blood / CBC", "liver": "Liver function", "lipid": "Lipid profile", "echo": "Echocardiography report",
                "ecg": "ECG"}


def build_summary(reports: list[dict]) -> dict:
    """reports: [{'id','report_type','report_date','created_at','analysis'}] (already decrypted)."""
    modules: dict[str, list] = {}
    abnormal, uncertain, missing, model_outputs, limitations, dates = [], [], [], [], set(), []
    for r in reports:
        a = r.get("analysis") or {}
        dates.append({"report_id": r["id"], "type": r["report_type"], "report_date": r.get("report_date"),
                      "uploaded": r["created_at"]})
        for mod, res in a.items():
            if mod.startswith("_") or not isinstance(res, dict):
                continue
            modules.setdefault(mod, []).append({"report_id": r["id"], "report_date": r.get("report_date")})
            for m in res.get("measurements", []):
                interp = m.get("assessment", {}).get("interpretation")
                if interp in ("low", "high"):
                    abnormal.append({"module": mod, "test": m["test"], "value": m["value"], "unit": m.get("unit_display", m.get("unit")),
                                     "interpretation": interp, "range_used": m["assessment"].get("range_used"),
                                     "report_date": r.get("report_date"), "report_id": r["id"]})
                if m.get("origin") not in ("manual",) and m.get("issues") and not m.get("confirmed_by_user"):
                    uncertain.append({"module": mod, "test": m["test"], "issues": m["issues"]})
            for x in res.get("missing", []):
                missing.append({"module": mod, "test": x["test"], "report_id": r["id"]})
            if mod == "liver" and res.get("research_model", {}).get("available"):
                rm = res["research_model"]
                model_outputs.append({"module": "liver", "model": rm["model"], "version": rm["model_version"],
                                      "output": f"Research score {rm['score']}", "meaning": rm["score_meaning"],
                                      "report_id": r["id"]})
                limitations.update(rm["limitations"])
            if mod == "ecg" and (res.get("classification") or {}).get("available"):
                c = res["classification"]
                model_outputs.append({"module": "ecg", "model": c["model"], "version": c["model_version"],
                                      "output": "Beat counts " + ", ".join(f"{k}: {v}" for k, v in c["counts"].items()),
                                      "meaning": c["caveat"], "report_id": r["id"]})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_reports": len(reports),
        "modules": {MODULE_LABEL.get(k, k): v for k, v in modules.items()},
        "abnormal_values": abnormal,
        "uncertain_values": uncertain,
        "missing_measurements": missing,
        "model_outputs": model_outputs,
        "model_limitations": sorted(limitations),
        "report_dates": dates,
        "overall_score": None,
        "overall_score_note": "No single overall health score is computed because no validated method exists for "
                              "combining these measurements.",
        "disclaimer": DISCLAIMER,
    }


def summary_pdf(summary: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title="MediScan AI – Combined Summary")
    ss = getSampleStyleSheet()
    navy = colors.HexColor("#0b2545")
    story = [Paragraph("<font color='#0b2545'><b>MediScan AI</b></font> – Combined Report Summary", ss["Title"]),
             Paragraph(f"Generated {summary['generated_at'][:19].replace('T', ' ')} UTC · {summary['n_reports']} report(s)", ss["Normal"]),
             Spacer(1, 4 * mm),
             Paragraph(f"<i>{DISCLAIMER}</i>", ss["Normal"]), Spacer(1, 5 * mm)]

    def table(title, header, rows):
        story.append(Paragraph(title, ss["Heading2"]))
        if not rows:
            story.append(Paragraph("None.", ss["Normal"]))
            return
        t = Table([header] + rows, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef6f8")])]))
        story.append(t)
        story.append(Spacer(1, 4 * mm))

    def rng(r):
        if not r:
            return "–"
        return f"{r.get('low') if r.get('low') is not None else '–'} – {r.get('high') if r.get('high') is not None else '–'} ({r.get('source')})"

    table("Values outside the range used", ["Module", "Test", "Value", "Unit", "Flag", "Range used", "Report date"],
          [[a["module"], a["test"], f"{a['value']:g}", a["unit"] or "", a["interpretation"], rng(a["range_used"]), a["report_date"] or "–"]
           for a in summary["abnormal_values"]])
    table("Model outputs (research use only)", ["Module", "Model", "Version", "Output"],
          [[m["module"], m["model"], m["version"], Paragraph(m["output"], ss["BodyText"])] for m in summary["model_outputs"]])
    table("Missing measurements", ["Module", "Test"], [[m["module"], m["test"]] for m in summary["missing_measurements"]])
    table("Report dates", ["Type", "Report date", "Uploaded"],
          [[d["type"], d["report_date"] or "not found", str(d["uploaded"])[:10]] for d in summary["report_dates"]])
    if summary["model_limitations"]:
        story.append(Paragraph("Model limitations", ss["Heading2"]))
        for l in summary["model_limitations"]:
            story.append(Paragraph("• " + l, ss["Normal"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(summary["overall_score_note"], ss["Italic"]))
    doc.build(story)
    return buf.getvalue()
