"""Server-side "Compliance Alignment & Fair Lending" PDF.

One click in the audit console returns a real PDF built with ReportLab. Charts
are drawn with ReportLab's own primitives, so the runtime never pulls in
matplotlib -- which keeps the serverless bundle small.

The report contains only numbers the training pipeline actually produced: model
metrics, the cost policy, the fairness audit for every audited attribute, the
mitigation before/after and the model lineage. Where something is unknown it
says so rather than estimating.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PRIMARY = colors.HexColor("#0f766e")
DARK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
DANGER = colors.HexColor("#b91c1c")
OK = colors.HexColor("#15803d")


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("TSTitle", parent=styles["Title"], textColor=DARK, fontSize=22))
    styles.add(ParagraphStyle("TSH2", parent=styles["Heading2"], textColor=PRIMARY, spaceBefore=14))
    styles.add(ParagraphStyle("TSH3", parent=styles["Heading3"], textColor=DARK, spaceBefore=8))
    styles.add(ParagraphStyle("TSBody", parent=styles["BodyText"], textColor=DARK, fontSize=9.5))
    styles.add(ParagraphStyle("TSMuted", parent=styles["BodyText"], textColor=MUTED, fontSize=8))
    return styles


def _fmt(value, digits=4):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _table(rows, styles, col_widths=None, header=True):
    table = Table(rows, colWidths=col_widths, hAlign="LEFT")
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    table.setStyle(TableStyle(style))
    return table


def _calibration_drawing(curve: list[dict], size: float = 320) -> Drawing:
    """Draw the reliability curve with ReportLab primitives (no matplotlib)."""
    drawing = Drawing(size, size)
    pad = 34
    plot = size - 2 * pad

    def x(v):
        return pad + max(0.0, min(1.0, v)) * plot

    def y(v):
        return pad + max(0.0, min(1.0, v)) * plot

    # axes
    drawing.add(Line(pad, pad, pad + plot, pad, strokeColor=MUTED))
    drawing.add(Line(pad, pad, pad, pad + plot, strokeColor=MUTED))
    # diagonal reference
    drawing.add(
        Line(pad, pad, pad + plot, pad + plot, strokeColor=colors.HexColor("#cbd5e1"),
             strokeDashArray=[3, 3])
    )
    drawing.add(String(pad, size - 20, "Reliability curve (predicted vs observed)",
                       fontSize=8, fillColor=MUTED))
    drawing.add(String(pad, pad - 14, "predicted PD", fontSize=7, fillColor=MUTED))
    drawing.add(String(4, pad + plot - 8, "observed", fontSize=7, fillColor=MUTED))

    points = [
        (x(b["mean_predicted"]), y(b["observed_rate"]))
        for b in curve
        if b.get("mean_predicted") is not None and b.get("observed_rate") is not None
    ]
    if len(points) >= 2:
        flat = []
        for px, py in points:
            flat.extend([px, py])
        drawing.add(PolyLine(flat, strokeColor=PRIMARY, strokeWidth=1.6))
        for px, py in points:
            drawing.add(Line(px - 1.6, py, px + 1.6, py, strokeColor=PRIMARY, strokeWidth=1.6))
            drawing.add(Line(px, py - 1.6, px, py + 1.6, strokeColor=PRIMARY, strokeWidth=1.6))
    return drawing


def build_compliance_report(metadata: dict, registry: dict | None = None) -> bytes:
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="TrustScore Compliance Alignment & Fair Lending Report",
    )

    registry = registry or {}
    story: list = []
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    version = metadata.get("version", "unknown")
    fairness = metadata.get("fairness", {}) or {}
    thr = metadata.get("thresholds", {}) or {}
    metrics = metadata.get("metrics", {}) or {}
    calibration = metadata.get("calibration", {}) or {}
    mitigation = metadata.get("mitigation", {}) or {}

    story.append(Paragraph("Compliance Alignment &amp; Fair Lending Report", styles["TSTitle"]))
    story.append(
        Paragraph(
            f"Model <b>{version}</b> &nbsp;•&nbsp; generated {generated}",
            styles["TSBody"],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "<b>SIMULATION ENVIRONMENT.</b> TrustScore is a demonstration of "
            "responsible-AI credit decisioning. Nothing in this report is a legal "
            "opinion, a compliance certificate, or a real credit decision.",
            styles["TSMuted"],
        )
    )
    story.append(Spacer(1, 10))

    # -- 1. Model overview -------------------------------------------------
    story.append(Paragraph("1. Model overview", styles["TSH2"]))
    ds = metadata.get("dataset", {}) or {}
    overview = [
        ["Field", "Value"],
        ["Model version", version],
        ["Trained at", metadata.get("trained_at", "n/a")],
        ["Dataset", ds.get("name", "n/a")],
        ["Rows after cleaning", f"{ds.get('rows', 0):,}" if ds.get("rows") else "n/a"],
        ["Default rate", _fmt(ds.get("target_rate"), 4)],
        ["Seed", str(ds.get("seed", "n/a"))],
        ["Registry default", registry.get("default", version)],
        ["Fairness-tuned model", registry.get("fair", "n/a")],
    ]
    story.append(_table(overview, styles))

    # -- 2. Performance ----------------------------------------------------
    story.append(Paragraph("2. Discrimination and calibration", styles["TSH2"]))
    perf = [["Model", "ROC-AUC", "PR-AUC", "Brier"]]
    for name, key in (
        ("Logistic regression (baseline)", "baseline_lr"),
        ("LightGBM (uncalibrated)", "lightgbm"),
        ("LightGBM (calibrated)", "calibrated"),
    ):
        m = metrics.get(key, {}) or {}
        perf.append([name, _fmt(m.get("roc_auc")), _fmt(m.get("pr_auc")), _fmt(m.get("brier"))])
    story.append(_table(perf, styles))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            f"Brier score (calibrated): <b>{_fmt(calibration.get('brier'))}</b> &nbsp; "
            f"Expected calibration error: <b>{_fmt(calibration.get('ece'))}</b>",
            styles["TSBody"],
        )
    )
    curve = calibration.get("curve") or []
    if curve:
        story.append(Spacer(1, 6))
        story.append(_calibration_drawing(curve))

    story.append(PageBreak())

    # -- 3. Policy ---------------------------------------------------------
    story.append(Paragraph("3. Decision policy and cost matrix", styles["TSH2"]))
    cm = thr.get("cost_matrix", {}) or {}
    policy_rows = [["Parameter", "Value"]]
    policy_rows.append(["Approve when PD ≤", _fmt(thr.get("approve_max_pd"))])
    policy_rows.append(["Decline when PD ≥", _fmt(thr.get("decline_min_pd"))])
    policy_rows.append(["Cost of false approve", _fmt(cm.get("false_approve"), 2)])
    policy_rows.append(["Cost of false decline", _fmt(cm.get("false_decline"), 2)])
    policy_rows.append(["Cost of review", _fmt(cm.get("review"), 2)])
    policy_rows.append(["Expected cost / loan (validation)", _fmt(thr.get("expected_cost_per_loan"))])
    policy_rows.append(["Test approval rate", _fmt(thr.get("test_approval_rate"), 3)])
    story.append(_table(policy_rows, styles))

    # -- 4. Fairness -------------------------------------------------------
    story.append(Paragraph("4. Fairness audit", styles["TSH2"]))
    story.append(Paragraph(fairness.get("disclaimer", ""), styles["TSMuted"]))
    story.append(Spacer(1, 6))
    guardrail = fairness.get("guardrail", {}) or {}
    status_color = OK if guardrail.get("passed") else DANGER
    story.append(
        Paragraph(
            f"<b>Four-fifths guardrail:</b> "
            f"<font color='#{status_color.hexval()[2:]}'>"
            f"{'PASS' if guardrail.get('passed') else 'BREACH'}</font> "
            f"&nbsp; floor {_fmt(guardrail.get('disparate_impact_floor'), 2)} &nbsp; "
            f"({guardrail.get('n_breaches', 0)} attribute(s) below the floor)",
            styles["TSBody"],
        )
    )
    story.append(Spacer(1, 6))

    for attr, block in (fairness.get("attributes", {}) or {}).items():
        summary = block.get("summary", {}) or {}
        story.append(Paragraph(block.get("label", attr), styles["TSH3"]))
        rows = [["Group", "n", "Approval rate", "TPR", "FPR"]]
        for g in block.get("groups", []):
            flag = " *" if g.get("low_sample") else ""
            rows.append(
                [
                    f"{g['group']}{flag}",
                    f"{g['n']:,}",
                    _fmt(g.get("selection_rate")),
                    _fmt(g.get("tpr")),
                    _fmt(g.get("fpr")),
                ]
            )
        story.append(_table(rows, styles))
        di = summary.get("disparate_impact_ratio")
        passed = summary.get("disparate_impact_pass")
        di_text = "PASS" if passed else "BREACH"
        story.append(
            Paragraph(
                f"Disparate-impact ratio: <b>{_fmt(di)}</b> [{di_text}] &nbsp; "
                f"Equalized-odds difference: {_fmt(summary.get('equalized_odds_difference'))}",
                styles["TSMuted"],
            )
        )
        story.append(Spacer(1, 4))

    story.append(PageBreak())

    # -- 5. Mitigation -----------------------------------------------------
    story.append(Paragraph("5. Fairness mitigation (equalized odds)", styles["TSH2"]))
    if mitigation:
        story.append(
            Paragraph(
                "The fairness-tuned model keeps the same booster and appends a "
                "post-processing rule: per-group randomised probability thresholds "
                "that equalise true- and false-positive rates. The table shows the "
                "effect on the held-out test split for each attribute it was fitted on.",
                styles["TSBody"],
            )
        )
        story.append(Spacer(1, 6))
        rows = [["Attribute", "DI before", "DI after", "EO before", "EO after", "Breaches"]]
        for attr in registry.get("mitigation_attributes", []) or []:
            imp = attr.get("impact", {}) or {}
            rows.append(
                [
                    attr.get("label", attr.get("id")),
                    _fmt(imp.get("disparate_impact_ratio_base")),
                    _fmt(imp.get("disparate_impact_ratio_mitigated")),
                    _fmt(imp.get("equalized_odds_difference_base")),
                    _fmt(imp.get("equalized_odds_difference_mitigated")),
                    f"{imp.get('n_breaches_base')} → {imp.get('n_breaches_mitigated')}",
                ]
            )
        if len(rows) > 1:
            story.append(_table(rows, styles))
        story.append(Spacer(1, 6))
        story.append(
            Paragraph(
                f"Default mitigation attribute: <b>{mitigation.get('attribute')}</b>. "
                "Equalized odds targets true/false-positive parity, not selection-rate "
                "parity; the four-fifths guardrail can still flag other attributes.",
                styles["TSMuted"],
            )
        )
    else:
        story.append(Paragraph("No mitigation configuration present.", styles["TSBody"]))

    # -- 6. Lineage --------------------------------------------------------
    story.append(Paragraph("6. Model lineage", styles["TSH2"]))
    lineage = registry.get("lineage", []) or []
    if lineage:
        rows = [["Version", "Role", "Parent", "Trained at", "Note"]]
        for item in lineage:
            rows.append(
                [
                    item.get("version", ""),
                    item.get("role", ""),
                    item.get("parent", "—"),
                    item.get("trained_at", ""),
                    item.get("note", ""),
                ]
            )
        story.append(_table(rows, styles))
    else:
        story.append(Paragraph("No lineage recorded.", styles["TSBody"]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("7. Limitations", styles["TSH2"]))
    for item in metadata.get("limitations", []) or []:
        story.append(Paragraph(f"• {item}", styles["TSMuted"]))

    doc.build(story)
    return buffer.getvalue()
