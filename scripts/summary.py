import json
from pathlib import Path

root = Path(r"C:\Users\hp\Documents\Default Project\trustscore")
rep = root / "reports"
md = json.loads((root / "api" / "artifacts" / "metadata.json").read_text(encoding="utf-8"))
f = json.loads((rep / "fairness_v1.json").read_text(encoding="utf-8"))
m = json.loads((rep / "metrics_v1.json").read_text(encoding="utf-8"))

print("== metrics (test) ==")
for k in ("baseline_lr", "lightgbm", "calibrated"):
    b = m[k]
    print(f"{k:12s} roc={b['roc_auc']:.4f} pr={b['pr_auc']:.4f} brier={b['brier']:.4f} "
          f"prec={b['precision']:.3f} rec={b['recall']:.3f} f1={b['f1']:.3f}")
print("calibration ece:", round(md["calibration"]["ece"], 5))
print("thresholds:", md["thresholds"]["approve_max_pd"], md["thresholds"]["decline_min_pd"])
print("approval rate:", round(md["thresholds"]["test_approval_rate"], 4))
print("bands:", md["thresholds"]["test_band_counts"])
print("expected cost/loan:", round(md["thresholds"]["expected_cost_per_loan"], 5))
print("target rate:", round(md["dataset"]["target_rate"], 4), "rows:", md["dataset"]["rows"])
print("\n== fairness ==")
for k, v in f["attributes"].items():
    s = v["summary"]
    def r(x):
        return None if x is None else round(x, 3)
    print(f"{k:28s} sel_ratio={r(s['selection_rate_ratio'])} dpd={r(s['demographic_parity_difference'])} eod={r(s['equal_opportunity_difference'])}")
print("\n== top features ==")
for t in md["top_features"][:8]:
    print(f"  {t['feature']:32s} {t['mean_abs_contribution']:.4f}")
print("\n== drift verdicts ==")
for feat, d in md["drift"]["features"].items():
    print(f"  {feat:28s} psi={d['psi']:.4f} {d['verdict']}")
