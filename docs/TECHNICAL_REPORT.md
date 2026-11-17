# MediScan AI – Technical Report

*Version 1.0 · Educational research prototype · Not clinically validated*

## Abstract

MediScan AI is an end-to-end system that converts photographed or PDF medical reports into validated, structured measurements and runs domain-specific analyses for ECG, echocardiography, blood, liver and lipid reports. Extraction uses local Tesseract OCR with OpenCV preprocessing and a deterministic, rule-based parser; every value is confidence-scored, unit-normalised and validated, and nothing is analysed until a human has confirmed it. Two supervised tasks were trained on real public data with leakage-aware protocols: a liver research classifier on the Indian Liver Patient Dataset (served XGBoost: held-out ROC-AUC 0.810, CV ROC-AUC 0.708 ± 0.039) and an inter-patient heartbeat classifier on MIT-BIH (served XGBoost on 22 unseen patients: V-class F1 0.922, S-class F1 0.199, F-class F1 0.008, macro-F1 0.516). Blood, lipid and ECHO modules are rule-based because no suitably labelled public data was available. We report the limitations of each component explicitly.

## 1. System design

**Requirements driving the design**: (i) never fabricate a value, (ii) every automated statement traceable to a rule, range or model with known test performance, (iii) privacy by default, (iv) runnable offline, (v) deployable with the UI on Vercel.

**Components**
* *Frontend* (Next.js 14 / TypeScript / Tailwind / Recharts): 10 pages – dashboard, upload, review/correction, ECG, ECHO, blood, liver, lipid, combined summary, model performance, history.
* *API* (FastAPI / Pydantic): upload validation, asynchronous job runner (status, progress, retry), review/confirm endpoints, stateless manual-analysis endpoints, model registry, summary/PDF generation.
* *Persistence* (SQLAlchemy; PostgreSQL in production, SQLite locally): `reports` (clear metadata + Fernet-encrypted OCR/extraction/analysis blobs) and `audit_events` (encrypted details).
* *ML package* (`ml/`): independent pipelines per task, shared metric code, a JSON model registry consumed by the UI so that no metric is ever hard-coded in the frontend.

**Processing state machine**: `processing → awaiting_confirmation | needs_manual_entry | failed → analysed`.

## 2. Document understanding

### 2.1 Preprocessing
EXIF transpose → Tesseract OSD for quarter-turn rotation (low-confidence proposals are verified by comparing OCR word-confidence before/after rotating) → skew estimation from Hough lines on a horizontally dilated binary image (median angle within ±15°) → affine deskew → non-local-means denoising → CLAHE → upscaling to ≥ 1500 px width. A variance-of-Laplacian < 60 raises a blur warning. PDFs use the embedded text layer when ≥ 40 non-space characters exist on a page, plus row re-assembly from word boxes; otherwise the page is rasterised at 300 dpi.

### 2.2 Classification
Keyword scoring with diminishing returns per term over six panels; panels scoring ≥ 5 are reported, the highest becomes the primary type. ECHO/ECG disambiguation prevents an ECHO report that mentions “ECG” in its history from being misrouted. Matched evidence and scores are returned and the user can override the type.

### 2.3 Extraction
A catalogue of 40 analytes (synonyms + exclusion patterns). The parser takes the first number after the label, rejects numbers further than 60 characters away or preceded by other digits, treats “label a–b …” as a range rather than a value, captures H/L/* flags, a unit within 25 characters and a reference range after the unit. Fixes: OCR digit confusions between digits, Indian digit grouping, decimal commas (flagged), glued abbreviations. When an analyte appears on several lines the candidate with a unit and the highest confidence wins and conflicting values are flagged.

### 2.4 Units and validation
Conversion tables per analyte (molar-mass based). Unknown or missing units produce *no value* and an *uncertain* status. Validation layers: plausibility bounds (wide, intended to catch misreads), lab-range sanity (value > 20 range-widths above the upper limit), confidence < 0.80, and identities between fields (bilirubin fractions, HDL/LDL < TC, albumin < total protein, LVIDs < LVIDd, MCHC/MCH/MCV vs Hb/Hct/RBC within 15 %). *Invalid* values block analysis until corrected or removed.

### 2.5 Verification of the extraction layer
64 automated tests (pytest) cover unit detection/conversion, alias collisions, missing units, SI units, range-vs-value ambiguity, OCR digit fixes, classification of six report types, validation rules, OCR on synthetic CBC images (clean, 4° skew, 90° rotation, heavy blur), PDF text-layer extraction, ECHO narrative extraction, the API flow (upload → job → review → correction → audit → analysis → summary → PDF → deletion), encrypted storage and deletion, duplicate detection, file-validation rejections and size limits. On the clean synthetic CBC image 10/10 values were extracted with correct values; 3 were flagged *uncertain* due to OCR confidence (e.g. “mill/cumm” read as “millcumm”). On the 4°-skewed image one decimal point was lost (MCH 21.4 → 214); validation marked it *invalid* rather than passing it through. The heavily blurred image produced no measurements and quality warnings (safe failure). These are synthetic documents; performance on real-world reports has not been measured.

## 3. ECG

### 3.1 Data and protocol
MIT-BIH Arrhythmia Database (48 records; header checksums verified). AAMI mapping N {N,L,R,e,j}, S {A,a,J,S}, V {V,E}, F {F}, Q {/,f,Q}; paced records excluded; Q not modelled. Inter-patient split: DS1 = 22 records (50 968 beats: N 45 826, S 941, V 3 787, F 414), DS2 = 22 records (49 660 beats: N 44 217, S 1 836, V 3 219, F 388). Reference R-peak annotations are used for segmentation during training; the built-in detector is used at inference.

### 3.2 Features and models
MLII lead → 0.5–40 Hz zero-phase filtering + 60 Hz notch → 125 Hz → window [−0.30, +0.50] s (99 samples), per-beat z-score. RR features: pre, post, local mean (10 beats), pre/local, pre/recording-mean, post/recording-mean, post/pre. Tabular models additionally use 9 morphology statistics and 25 down-sampled amplitudes (41 features).
* Random forest (balanced subsample weights), XGBoost (balanced sample weights) – 3 configurations each, 4-fold GroupKFold by record on DS1, selection by macro-F1.
* 1-D CNN: 3 × (2 conv-BN-ReLU + max-pool) → global average pooling, concatenated with an RR branch → 2 dense layers; AdamW, sqrt-inverse-frequency class weights, early stopping on 4 DS1 records (116, 203, 208, 223).

### 3.3 Results on DS2 (unseen patients)

| Model | DS1 val. macro-F1 | Acc. | Bal. acc. | Macro-F1 | Macro ROC-AUC | F1 N | F1 S | F1 V | F1 F |
|---|---|---|---|---|---|---|---|---|---|
| Random forest | 0.491 ± 0.100 | 0.917 | 0.522 | 0.525 | 0.927 | 0.955 | 0.208 | 0.929 | 0.006 |
| XGBoost (served) | 0.498 ± 0.120 | 0.882 | 0.522 | 0.516 | 0.875 | 0.936 | 0.199 | 0.922 | 0.008 |
| 1-D CNN | 0.487 | 0.848 | 0.517 | 0.420 | 0.843 | 0.927 | 0.226 | 0.521 | 0.007 |

Served model precision/recall: N 0.959/0.913, S 0.210/0.189, V 0.892/0.954, F 0.005/0.031.

**Discussion.** V beats generalise well; S and F do not. In DS2 many S beats are misclassified as N (1 249 of 1 836 for XGBoost) and most F beats as N; conversely 2 439 N beats were predicted as F, so F predictions are almost always wrong (precision 0.005). F training examples come almost entirely from one patient (208), so the model learns that patient's morphology rather than the class. The CNN is worse on V because of over-prediction of V on N beats (precision 0.356), likely because its validation set held most F/V-rich records. These outcomes match the well-known difficulty of the inter-patient protocol; intra-patient splits (such as the Kaggle CSV split) report much higher numbers because the same patients appear in train and test. A first full run with 4 RR features gave macro-F1 0.513 (RF), 0.518 (XGB), 0.455 (CNN); the RR-normalisation change was made once after that run and is disclosed.

### 3.4 Signal quality and digitisation
SQIs gate both HR and classification. The image digitiser was checked on a strip rendered from MIT-BIH 233 at 200 dpi: grid spacing 7.95 px/mm vs 7.87 true (0.9 %), HR 97.7 vs 97.3 bpm from the source signal, Pearson r ≈ 0.69 between the aligned digitised and source signals (residual time-scale error accumulates over 10 s). Real scanned ECGs (12-lead layouts, text overlays, faded grids) were not evaluated.

## 4. Liver research classifier

### 4.1 Data
ILPD (583 rows; provenance and verification in DATASETS.md). 13 exact duplicates removed before splitting (570 rows). Stratified 80/20 split: 456 train / 114 test (81 positive). Label 1 = record labelled “liver patient”.

### 4.2 Pipeline
Derived features (indirect bilirubin, globulin, AST/ALT, sex indicator) → median imputation → (linear model only) log1p for skewed variables + standardisation → classifier. RandomizedSearchCV (40 iterations) with stratified 5-fold CV and ROC-AUC on the training split only.

### 4.3 Results (held-out test, threshold 0.5)

| Model | CV ROC-AUC | Test ROC-AUC | PR-AUC | F1 | Prec. | Recall | Spec. | Bal. acc. | Brier | Confusion [[TN,FP],[FN,TP]] |
|---|---|---|---|---|---|---|---|---|---|---|
| Logistic regression | 0.734 ± 0.043 | 0.807 | 0.929 | 0.794 | 0.933 | 0.691 | 0.879 | 0.785 | 0.215 | [[29,4],[25,56]] |
| Random forest | 0.719 ± 0.036 | 0.795 | 0.913 | 0.800 | 0.870 | 0.741 | 0.727 | 0.734 | 0.168 | [[24,9],[21,60]] |
| Gradient boosting | 0.707 ± 0.047 | 0.779 | 0.903 | 0.838 | 0.765 | 0.926 | 0.303 | 0.614 | 0.181 | [[10,23],[6,75]] |
| XGBoost (served) | 0.708 ± 0.039 | 0.810 | 0.909 | 0.789 | 0.918 | 0.691 | 0.848 | 0.770 | 0.205 | [[28,5],[25,56]] |

Note the PR-AUC baseline is the positive rate (0.71). Differences between models are within the uncertainty expected from a 114-record test set. Class-weighting shifts the 0.5 threshold toward specificity for LR/XGB; gradient boosting (no weighting) is the opposite. Probabilities are not well calibrated (Brier 0.17–0.22; reliability curves in the UI), so the score is shown as a research score, not a probability of disease.

### 4.4 Explainability
TreeExplainer SHAP on the test set: mean |SHAP| ranks direct bilirubin (0.129), total bilirubin (0.106), ALP (0.084), ALT (0.067), AST (0.044) highest. Per-request SHAP values accompany every score in the UI.

## 5. Rule-based modules
* **Blood**: lab or cited default ranges; WHO severity bands; microcytic/macrocytic/normocytic patterns; haematinic markers only when measured; Mentzer index as a caveated derived value.
* **Lipid**: non-HDL, TC/HDL, LDL/HDL, TG/HDL; Friedewald (TG < 400), Sampson (400–800), none above 800 mg/dL; NCEP ATP III categories; consistency warning for reported vs implied LDL.
* **ECHO**: ASE/EACVI ranges, EF bands with no inference from text, verbatim narrative and impression.
* **Liver rules**: De Ritis ratio, R ratio (ACG 2017) only when ALT or ALP is raised.

## 6. Privacy and security
See README §16. Key properties: local OCR; opt-in encrypted file storage; encrypted sensitive blobs; minimal, content-free logging; strict upload validation; CORS allow-list; optional API key; HTTPS enforcement; complete deletion. Missing: user accounts and access control (documented).

## 7. Threats to validity
Synthetic OCR test documents; single-centre ILPD; 1970s Holter ECGs from 47 subjects; datasets obtained from verified mirrors rather than official hosts in the build environment; reference defaults that may not match local labs; no clinical validation of any component.

## 8. Reproducibility
`python -m ml.liver.train` and `python -m ml.ecg.train` regenerate every metric, figure and registry entry with fixed seeds (42); dataset SHA-256 and timings are recorded in `models/metadata/*.json`. EDA notebooks are executed by `scripts/build_notebooks.py`. Library versions are pinned in `backend/requirements.txt` (pickled models require matching scikit-learn/XGBoost versions).
