"""Rule-based analysis engines and the liver research model."""
import pytest

from backend.services.analyzers.blood import analyze_blood
from backend.services.analyzers.echo import analyze_echo
from backend.services.analyzers.lipid import analyze_lipid, estimate_ldl, friedewald, sampson
from backend.services.analyzers.liver import analyze_liver
from ml.model_registry import load_metadata


def M(key, value, rng=None, unit=""):
    return {"key": key, "test": key, "value": value, "unit": unit, "status": "ok", "reference_range": rng,
            "issues": [], "origin": "manual"}


def test_blood_microcytic_pattern_without_diagnosis():
    r = analyze_blood([M("hemoglobin", 10.5), M("mcv", 72), M("mch", 21), M("rdw", 16.9), M("rbc", 4.9)], sex="female")
    names = [p["pattern"] for p in r["patterns"]]
    assert "Microcytic (± hypochromic) anaemia pattern" in names
    assert all("deficiency" not in n.lower() for n in names)  # no deficiency claims without markers
    assert r["missing_haematinics_note"]
    assert any(d["name"].startswith("Mentzer") for d in r["derived"])


def test_blood_uses_lab_range_over_default():
    r = analyze_blood([M("hemoglobin", 12.5, {"low": 13.0, "high": 17.0})], sex="female")
    a = r["measurements"][0]["assessment"]
    assert a["range_used"]["source"] == "laboratory" and a["interpretation"] == "low"


def test_lipid_friedewald_and_guard():
    assert friedewald(200, 50, 150) == pytest.approx(120)
    assert estimate_ldl(200, 50, 450)["method"].startswith("Sampson")
    assert estimate_ldl(300, 40, 900)["value"] is None
    assert sampson(200, 50, 150) == pytest.approx(200 / 0.948 - 50 / 0.971 - (150 / 8.56 + 150 * 150 / 2140 - 150 ** 2 / 16100) - 9.44)


def test_lipid_derived_labelled():
    r = analyze_lipid([M("total_cholesterol", 232), M("hdl", 38), M("triglycerides", 180)])
    d = {x["key"]: x for x in r["derived"]}
    assert d["non_hdl"]["value"] == pytest.approx(194)
    assert d["tc_hdl_ratio"]["value"] == pytest.approx(232 / 38, rel=1e-3)
    assert d["ldl_estimated"]["value"] == pytest.approx(232 - 38 - 36)
    assert all(x["origin"] == "derived" for x in r["derived"])


def test_lipid_no_ldl_estimate_when_tg_too_high():
    r = analyze_lipid([M("total_cholesterol", 300), M("hdl", 35), M("triglycerides", 950)])
    assert not any(x["key"] == "ldl_estimated" for x in r["derived"])
    assert any("direct LDL" in w for w in r["warnings"])


def test_echo_does_not_infer_ef():
    r = analyze_echo([M("lvidd", 5.0)], {"lv_function_text": ["Normal LV systolic function"]}, sex="male")
    assert not any(m["key"] == "ef" for m in r["measurements"])
    assert any("not inferred" in n for n in r["notes"])


def test_liver_rules_and_ratios():
    r = analyze_liver([M("alt", 96, {"low": 7, "high": 56}), M("ast", 71), M("alp", 160, {"low": 44, "high": 147}),
                       M("total_bilirubin", 1.8), M("direct_bilirubin", 0.6), M("albumin", 3.9), M("total_protein", 7.1)],
                      sex="male", age=52)
    d = {x["key"]: x for x in r["derived"]}
    assert d["ast_alt_ratio"]["value"] == pytest.approx(71 / 96, rel=1e-3)
    assert d["globulin"]["value"] == pytest.approx(3.2)
    assert d["r_ratio"]["value"] == pytest.approx((96 / 56) / (160 / 147), rel=1e-3)


@pytest.mark.skipif(load_metadata("liver") is None, reason="liver model not trained")
def test_liver_model_score_and_shap():
    ms = [M("alt", 96), M("ast", 71), M("alp", 160), M("total_bilirubin", 1.8), M("direct_bilirubin", 0.6),
          M("albumin", 3.9), M("total_protein", 7.1), M("ag_ratio", 1.22)]
    rm = analyze_liver(ms, sex="male", age=52)["research_model"]
    assert rm["available"] and 0 <= rm["score"] <= 1
    assert len(rm["explanation"]) == 13
    # missing required input -> no score
    rm2 = analyze_liver(ms[:3], sex="male", age=52)["research_model"]
    assert rm2["available"] is False


@pytest.mark.skipif(load_metadata("liver") is None, reason="liver model not trained")
def test_liver_metadata_metrics_are_from_test_set():
    meta = load_metadata("liver")
    for name in ("logistic_regression", "random_forest", "gradient_boosting", "xgboost"):
        t = meta["models"][name]["test"]
        assert t["n"] == meta["dataset"]["test_size"]
        assert 0 <= t["roc_auc"] <= 1 and sum(map(sum, t["confusion_matrix"]["matrix"])) == t["n"]
