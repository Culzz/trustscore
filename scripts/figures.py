"""Generate the model figures used in the README and docs.

    python scripts/figures.py

Reads the committed reports/JSON (no data or model needed) and writes PNGs to
docs/figures/. Uses matplotlib only.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
OUT = ROOT / "docs" / "figures"

INDIGO = "#4f46e5"
SLATE = "#64748b"
EMERALD = "#10b981"
AMBER = "#f59e0b"
ROSE = "#f43f5e"


def _load(name: str) -> dict:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def _style(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#e2e8f0", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=SLATE, labelsize=9)


def calibration(cal: dict) -> None:
    bins = [b for b in cal["bins"] if b["mean_predicted"] is not None and b["count"] >= 10]
    x = [b["mean_predicted"] * 100 for b in bins]
    y = [b["observed_rate"] * 100 for b in bins]
    size = [max(20, min(600, b["count"] / 8)) for b in bins]

    fig, ax = plt.subplots(figsize=(7, 4.6), dpi=150)
    ax.plot([0, 100], [0, 100], "--", color=SLATE, linewidth=1, label="Perfect calibration")
    ax.scatter(x, y, s=size, color=INDIGO, alpha=0.75, zorder=3, label="Risk bins")
    ax.plot(x, y, color=INDIGO, linewidth=1.2, alpha=0.6)
    ax.set_xlabel("Predicted risk (%)", color=SLATE, fontsize=10)
    ax.set_ylabel("Observed default rate (%)", color=SLATE, fontsize=10)
    ax.set_title(
        f"Calibration — Brier {cal['brier']:.4f}, ECE {cal['ece']:.4f}\nbins with ≥10 applicants",
        color="#0f172a",
        fontsize=11,
    )
    ax.legend(frameon=False, fontsize=9)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    _style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "calibration.png")
    plt.close(fig)


def score_distribution(meta: dict) -> None:
    bins = meta["score_distribution"]["bins"]
    x = [b["pd"] * 100 for b in bins]
    y = [b["count"] for b in bins]

    fig, ax = plt.subplots(figsize=(7, 4.6), dpi=150)
    ax.bar(x, y, width=3.2, color=INDIGO, alpha=0.85)
    ax.set_xlabel("Estimated risk (%)", color=SLATE, fontsize=10)
    ax.set_ylabel("Applicants", color=SLATE, fontsize=10)
    ax.set_title(
        f"Out-of-sample score distribution — {meta['score_distribution']['n']:,} applicants",
        color="#0f172a",
        fontsize=11,
    )
    _style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "score_distribution.png")
    plt.close(fig)


def performance(metrics: dict) -> None:
    keys = ["baseline_lr", "lightgbm", "calibrated"]
    labels = ["Logistic\nregression", "LightGBM\n(raw)", "LightGBM\n(calibrated)"]
    roc = [metrics[k]["roc_auc"] for k in keys]
    pr = [metrics[k]["pr_auc"] for k in keys]
    idx = range(len(keys))
    width = 0.38

    fig, ax = plt.subplots(figsize=(7, 4.6), dpi=150)
    b1 = ax.bar([i - width / 2 for i in idx], roc, width, label="ROC-AUC", color=INDIGO)
    b2 = ax.bar([i + width / 2 for i in idx], pr, width, label="PR-AUC", color=EMERALD)
    ax.bar_label(b1, fmt="%.3f", fontsize=8, color=SLATE, padding=2)
    ax.bar_label(b2, fmt="%.3f", fontsize=8, color=SLATE, padding=2)
    ax.axhline(0.75, color=ROSE, linestyle="--", linewidth=1)
    ax.text(len(keys) - 0.5, 0.76, "target ROC-AUC 0.75", color=ROSE, fontsize=8, ha="right")
    ax.set_xticks(list(idx))
    ax.set_xticklabels(labels, color=SLATE, fontsize=9)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score", color=SLATE, fontsize=10)
    ax.set_title("Test-set performance", color="#0f172a", fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    _style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "performance.png")
    plt.close(fig)


def fairness(report: dict) -> None:
    attrs = report["attributes"]
    n = len(attrs)
    cols = 2
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(10, 2.6 * rows), dpi=150)
    axes = axes.ravel()

    for ax, (key, block) in zip(axes, attrs.items()):
        groups = block["groups"]
        names = [g["group"] for g in groups]
        rates = [(g["selection_rate"] or 0) * 100 for g in groups]
        colors = [INDIGO if not g["low_sample"] else SLATE for g in groups]
        ax.barh(names[::-1], rates[::-1], color=colors[::-1], alpha=0.85)
        ratio = block["summary"]["selection_rate_ratio"]
        title = block["label"]
        if ratio is not None:
            title += f"  ·  selection-rate ratio {ratio:.2f}"
        ax.set_title(title, color="#0f172a", fontsize=9.5)
        ax.set_xlabel("Approval rate (%)", color=SLATE, fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(colors=SLATE, labelsize=8)
        ax.grid(axis="x", color="#e2e8f0", linewidth=0.8)
        ax.set_axisbelow(True)

    for ax in axes[n:]:
        ax.axis("off")

    fig.suptitle(
        "Fairness audit — approval rate by group (test split)",
        color="#0f172a",
        fontsize=12,
        y=0.995,
    )
    fig.text(
        0.5,
        0.005,
        "Statistical disparities, not a legal compliance verdict. Grey = small sample.",
        ha="center",
        fontsize=8,
        color=SLATE,
    )
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))
    fig.savefig(OUT / "fairness.png")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    calibration(_load("calibration_v1.json"))
    performance(_load("metrics_v1.json"))
    fairness(_load("fairness_v1.json"))
    meta = json.loads((ROOT / "api" / "artifacts" / "metadata.json").read_text(encoding="utf-8"))
    score_distribution(meta)
    print(f"wrote figures to {OUT}")


if __name__ == "__main__":
    main()
