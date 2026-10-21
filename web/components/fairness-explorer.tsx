"use client";

import { useState } from "react";
import type { FairnessReport } from "@/lib/types";
import { cn, formatNum, formatPct } from "@/lib/utils";

export function FairnessExplorer({ fairness }: { fairness: FairnessReport }) {
  const attributes = Object.entries(fairness.attributes);
  const [selected, setSelected] = useState(attributes[0]?.[0] ?? "");
  const current = fairness.attributes[selected];

  if (!attributes.length) {
    return <p className="text-sm text-slate-500">No fairness data available.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {attributes.map(([key, block]) => (
          <button
            key={key}
            onClick={() => setSelected(key)}
            className={cn(
              "rounded-sm border px-3 py-1.5 text-[9px] font-semibold uppercase tracking-[0.12em] transition",
              key === selected
                ? "border-brand-600 bg-brand-50 text-brand-700"
                : "border-slate-300 bg-paper text-slate-600 hover:border-slate-500 hover:text-slate-900",
            )}
          >
            {block.label}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-300 text-left text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              <th className="py-2 pr-4">Group</th>
              <th className="py-2 pr-4 text-right">n</th>
              <th className="py-2 pr-4 text-right">Approval rate</th>
              <th className="py-2 pr-4 text-right">TPR</th>
              <th className="py-2 pr-4 text-right">FPR</th>
              <th className="py-2 pr-4 text-right">Precision</th>
            </tr>
          </thead>
          <tbody>
            {current.groups.map((g) => (
              <tr key={g.group} className="border-b border-slate-200/70">
                <td className="py-2 pr-4 font-medium text-slate-700">
                  {g.group}
                  {g.low_sample ? (
                    <span className="ml-2 rounded-sm bg-slate-100 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-slate-500">
                      small sample
                    </span>
                  ) : null}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums text-slate-600">
                  {g.n.toLocaleString()}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {formatPct(g.selection_rate)}
                  {g.selection_rate_ci ? (
                    <span className="ml-1 text-[10px] text-slate-400">
                      [{formatPct(g.selection_rate_ci[0], 0)},{" "}
                      {formatPct(g.selection_rate_ci[1], 0)}]
                    </span>
                  ) : null}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">{formatPct(g.tpr)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{formatPct(g.fpr)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{formatPct(g.precision)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <Metric
          label="Selection-rate ratio"
          value={formatNum(current.summary.selection_rate_ratio, 3)}
          hint={
            current.summary.disparate_impact_ratio_ci
              ? `95% CI [${formatNum(current.summary.disparate_impact_ratio_ci[0], 3)}, ${formatNum(current.summary.disparate_impact_ratio_ci[1], 3)}]`
              : "min ÷ max approval rate (1.0 = parity)"
          }
        />
        <Metric
          label="Demographic parity gap"
          value={formatNum(current.summary.demographic_parity_difference, 3)}
          hint="max − min approval rate"
        />
        <Metric
          label="Equal opportunity gap"
          value={formatNum(current.summary.equal_opportunity_difference, 3)}
          hint="max − min TPR"
        />
        <Metric
          label="Equalized odds gap"
          value={formatNum(current.summary.equalized_odds_difference, 3)}
          hint={
            current.summary.equalized_odds_difference_ci
              ? `95% CI [${formatNum(current.summary.equalized_odds_difference_ci[0], 3)}, ${formatNum(current.summary.equalized_odds_difference_ci[1], 3)}]`
              : "max TPR/FPR gap"
          }
        />
      </div>

      <p className="text-[11px] text-slate-400">
        Groups used in the ratios: {current.summary.n_groups_considered} of{" "}
        {current.summary.n_groups_total ?? current.groups.length}. Groups below the
        minimum size are shown but excluded from the ratios. Intervals are Wilson
        (rates) and bootstrap (ratios) sampling uncertainty only.
      </p>

      <p className="text-[11px] text-slate-500">{fairness.disclaimer}</p>
      {fairness.unavailable_attributes?.length ? (
        <p className="text-[11px] text-slate-400">
          Not available in this dataset: {fairness.unavailable_attributes.join(", ")}.
        </p>
      ) : null}
    </div>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-sm border border-slate-200 bg-slate-100/40 px-3 py-2.5">
      <p className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-500">
        {label}
      </p>
      <p className="mono mt-1 text-lg font-medium text-slate-900">{value}</p>
      <p className="mt-0.5 text-[10px] text-slate-400">{hint}</p>
    </div>
  );
}
