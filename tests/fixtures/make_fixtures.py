"""Generate SYNTHETIC test documents (fabricated, non-patient values used only to test parsing).
They are clearly labelled 'SYNTHETIC TEST DOCUMENT' and must never be presented as real data."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
FONT_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
                   "/System/Library/Fonts/Supplemental/Arial.ttf", "C:/Windows/Fonts/arial.ttf"]

CBC_LINES = [
    "SYNTHETIC TEST DOCUMENT - NOT A REAL PATIENT",
    "COMPLETE BLOOD COUNT (CBC)",
    "Age/Sex: 34 Y / F        Report Date: 14/03/2025",
    "Test                     Result   Unit          Reference Range",
    "Hemoglobin               10.5 L   g/dL          12.0 - 15.5",
    "RBC Count                4.9      mill/cumm     4.0 - 5.2",
    "Total Leucocyte Count    7,500    cells/cumm    4000 - 11000",
    "Platelet Count           2.5      lakhs/cumm    1.5 - 4.0",
    "Hematocrit (PCV)         33.0     %             36 - 46",
    "MCV                      72 L     fL            80 - 100",
    "MCH                      21.4 L   pg            27 - 33",
    "MCHC                     31.8     g/dL          32 - 36",
    "RDW-CV                   16.9 H   %             11.5 - 14.5",
    "Serum Ferritin           9.0 L    ng/mL         15 - 150",
]
LFT_LIPID_LINES = [
    "SYNTHETIC TEST DOCUMENT - NOT A REAL PATIENT",
    "LIVER FUNCTION TEST",
    "Report Date: 2025-01-20     Age: 52 Years   Sex: Male",
    "Bilirubin Total            1.8      mg/dL     0.2 - 1.2",
    "Bilirubin Direct           0.6      mg/dL     0.0 - 0.3",
    "SGPT (ALT)                 96       U/L       7 - 56",
    "SGOT (AST)                 71       U/L       10 - 40",
    "Alkaline Phosphatase       160      U/L       44 - 147",
    "Total Protein              7.1      g/dL      6.0 - 8.3",
    "Albumin                    3.9      g/dL      3.5 - 5.0",
    "Globulin                   3.2      g/dL      2.0 - 3.5",
    "A/G Ratio                  1.22               1.0 - 2.2",
    "LIPID PROFILE",
    "Total Cholesterol          232      mg/dL     < 200",
    "Triglycerides              180      mg/dL     < 150",
    "HDL Cholesterol            38       mg/dL     > 40",
    "VLDL Cholesterol           36       mg/dL     < 30",
]
ECHO_LINES = [
    "SYNTHETIC TEST DOCUMENT - NOT A REAL PATIENT",
    "2D ECHOCARDIOGRAPHY AND DOPPLER REPORT",
    "Date: 05-Feb-2025   Sex: Male",
    "LVIDd 5.1 cm   LVIDs 3.6 cm",
    "IVSd 1.1 cm",
    "LVPWd 1.0 cm",
    "LA 4.2 cm      Aortic root 3.1 cm",
    "LVEF: 45 %",
    "TAPSE 1.9 cm",
    "E/A ratio 0.8",
    "Mitral valve: mild mitral regurgitation.",
    "Aortic valve: trileaflet, no stenosis.",
    "Regional wall motion: hypokinesia of inferior wall.",
    "Grade I diastolic dysfunction.",
    "No pericardial effusion.",
    "IMPRESSION:",
    "Mildly reduced LV systolic function. Mild MR. Inferior wall hypokinesia.",
]


def font(size=26):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def render_png(lines, path, rotate=0.0, blur=0.0, rot90=False):
    f = font(26)
    img = Image.new("RGB", (1500, 80 + 48 * len(lines)), "white")
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        d.text((50, 40 + 48 * i), l, fill="black", font=f)
    if rotate:
        img = img.rotate(rotate, expand=True, fillcolor="white", resample=Image.BICUBIC)
    if rot90:
        img = img.rotate(90, expand=True)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    img.save(path)
    return path


def render_pdf(lines, path):
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for l in lines:
        c.setFont("Helvetica", 10)
        c.drawString(40, y, l)
        y -= 18
    c.save()
    return path


def build_all(out: Path = HERE):
    out.mkdir(parents=True, exist_ok=True)
    return {
        "cbc_png": render_png(CBC_LINES, out / "synthetic_cbc.png"),
        "cbc_rotated_png": render_png(CBC_LINES, out / "synthetic_cbc_rot4.png", rotate=4),
        "cbc_rot90_png": render_png(CBC_LINES, out / "synthetic_cbc_rot90.png", rot90=True),
        "cbc_blurry_png": render_png(CBC_LINES, out / "synthetic_cbc_blurry.png", blur=4.5),
        "lft_lipid_pdf": render_pdf(LFT_LIPID_LINES, out / "synthetic_lft_lipid.pdf"),
        "lft_lipid_png": render_png(LFT_LIPID_LINES, out / "synthetic_lft_lipid.png"),
        "echo_pdf": render_pdf(ECHO_LINES, out / "synthetic_echo.pdf"),
        "echo_png": render_png(ECHO_LINES, out / "synthetic_echo.png"),
    }


if __name__ == "__main__":
    print(build_all())
