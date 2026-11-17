# Datasets, provenance and investigation notes

Datasets are not committed (see `.gitignore`). Run `bash scripts/download_datasets.sh` (Kaggle CLI + `wfdb`) or follow the manual steps below. Expected layout:

```
datasets/
├── liver/indian_liver_patient.csv
├── mitdb/100.dat 100.hea 100.atr … 234.*      (48 records)
├── heartbeat/mitbih_train.csv mitbih_test.csv   (optional)
├── cardio/cardio_train.csv                      (EDA only)
├── blood_cells/ …                               (investigation only)
├── ecg_images/ …                                (not yet used)
└── echo/ …                                      (not yet used)
```

## <a id="ilpd"></a>Indian Liver Patient Dataset (ILPD)

* Source: UCI ML Repository id 225 (Ramana & Venkateswarlu), mirrored on Kaggle as `uciml/indian-liver-patient-records`. Licence CC BY 4.0.
* Schema validated by `ml/liver/data.py`: 11 columns – Age, Gender, Total_Bilirubin, Direct_Bilirubin, Alkaline_Phosphotase, Alamine_Aminotransferase, Aspartate_Aminotransferase, Total_Protiens, Albumin, Albumin_and_Globulin_Ratio, Dataset (1 = liver patient, 2 = non-patient). Accepts both the Kaggle (header) and UCI (no header) files.
* Validation results: 583 rows, 416/167 labels, 441 male/142 female, 4 missing A/G ratios, **13 exact duplicate rows** (dropped before splitting), 3 rows with direct > total bilirubin (kept and reported), no physiologically implausible values.

**Provenance of the copy used to train the shipped model.** Kaggle and the UCI site were not reachable from the build environment (egress policy). The file was therefore reconstructed from two public GitHub mirrors:

1. `mp1610/Data_Mining` – “Indian Liver Patient Dataset (ILPD).csv”: 583 rows in original UCI order, but a data-mining course had injected 6 missing values and 5 corrupted values (e.g. total protein 83, ALT 5000).
2. `abhiroy96/indian-liver-patient-uci-dataset` – “ILPD.csv”: the 579 complete-case rows (the 4 rows with missing A/G ratio removed), with correct values but in a different order.

The 11 corrupted/missing cells in (1) were replaced with the value from the uniquely matching row in (2). The result reproduces the published dataset statistics exactly (UCI/Kaggle `describe()`): mean age 44.746141, mean TB 3.298799, mean DB 1.486106, mean ALP 290.576329, mean ALT 80.713551, mean AST 109.910806, mean TP 6.483190, mean albumin 3.141852, mean A/G 0.947064 (n = 579), maxima 90 / 75 / 19.7 / 2110 / 2000 / 4929 / 9.6 / 5.5 / 2.8, class counts 416/167, sex counts 441/142. SHA-256 of the file used: `0156b19779d9f7fc1f96382f92ab2c3052cdce527ec9f2d7b25c953a7a98656f`.

For strict reproducibility re-download the official file (`kaggle datasets download -d uciml/indian-liver-patient-records`) and re-run `python -m ml.liver.train`; the training metadata records the SHA-256 of whatever file was used.

## MIT-BIH Arrhythmia Database (ECG)

* Source: PhysioNet `mitdb` v1.0.0, ODC-By 1.0. 48 half-hour two-lead Holter recordings, 47 subjects, 360 Hz.
* Obtained from a public GitHub mirror (`breznak/nupic.biodat`) because physionet.org was not reachable; **all 48 records pass the WFDB header signal checksums**, and AAMI class totals (DS1: N 45 868, S 942, V 3 787, F 415; DS2: N 44 258, S 1 837, V 3 221, F 388 annotations) are consistent with the counts reported by de Chazal et al. (2004). The official route is `wfdb.dl_database("mitdb", "datasets/mitdb")`.
* After windowing (beats too close to the record edges are dropped) the training set has 50 968 beats and the test set 49 660.

## Kaggle ECG Heartbeat Categorization (`shayanfazeli/heartbeat`)

* Expected schema (validated by `ml/ecg/beat_dataset.load_kaggle_csv`): 187 float columns in [0, 1] (single beat at 125 Hz, zero-padded) + 1 integer label (0 N, 1 S, 2 V, 3 F, 4 Q). `mitbih_train.csv` 87 554 rows, `mitbih_test.csv` 21 892 rows (per dataset card).
* **Not a 12-lead ECG**, and **no patient/record ID** – train and test share patients. Therefore it is used only as an optional, clearly labelled intra-patient benchmark (`--kaggle-dir`). Not executed for the shipped results because Kaggle was not reachable.

## ECG images (`dsv/19217307`)

Not accessed. Before use: inspect licence and structure (image resolution, whether paper-speed/gain are printed, whether ground-truth signals are provided). If ground-truth signals exist, evaluate the digitiser with correlation / RMSE / HR error per lead. The digitiser is currently evaluated only on a strip rendered from MIT-BIH record 233 (`scripts/make_sample_data.py`), which is easier than real scans.

## Echocardiography (`echo2022`, Mendeley `nvx2kchfyh`)

Not accessed. `echo2022` is a Kaggle competition (accept rules, then `kaggle competitions download -c echo2022`). The Mendeley dataset requires manual download from data.mendeley.com. No ECHO model is trained or claimed; the ECHO module is structured report extraction only. A future image/video model must use a separate dataset (e.g. EchoNet-Dynamic) and its own evaluation.

## <a id="blood"></a>Blood: why there is no ML model

* `paultimothymooney/blood-cells` contains ~12 500 augmented images of four white-blood-cell types (eosinophil, lymphocyte, monocyte, neutrophil) derived from BCCD. WBC morphology says nothing about iron, B12 or folate status, so it cannot support the requested deficiency analysis; it is not used.
* Public tabular “anaemia” datasets on Kaggle typically derive their label from the same Hb/MCV/MCH thresholds that are inputs, or do not document how the label was obtained. A model trained on them would only re-learn a threshold rule while appearing to be “AI”. Following the brief (“If a reliable dataset is unavailable, do not fabricate a supervised model”), the blood module is rule-based with cited thresholds. Plug-in point: `ml/blood/` (add a loader + `train.py` mirroring `ml/liver/train.py`) if a dataset with independently confirmed diagnoses becomes available.

## Lipid / cardiovascular (`sulianova/cardiovascular-disease-dataset`)

70 000 rows; `cholesterol` is an ordinal category (1 normal, 2 above normal, 3 well above normal) and the target `cardio` is presence of cardiovascular disease. Neither is a measured lipid value nor a labelled lipid abnormality, so it cannot train a lipid classifier. It is explored in `notebooks/cardiovascular_eda.ipynb` only. The lipid module uses exact measurements + documented equations.
