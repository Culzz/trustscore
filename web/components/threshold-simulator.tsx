"use client";

import { useMemo, useState } from "react";
import { formatNum, formatPct } from "@/lib/utils";

interface Bin {
  pd: number;
  count: number;
  mean_exposure: number;
}

export function ThresholdSimulator({
  bins,
  initial,
  costMatrix,
}: {
  bins: Bin[];
  initial: { approve_max_pd: number; decline_min_pd: number };
  costMatrix: { false_approve: number; false_decline: number; review: number };
}) {
  const [approveMax, setApproveMax] = useState(initial.approve_max_pd);
  const [declineMin, setDeclineMin] = useState(initial.decline_min_pd);

  // Keep thresholds ordered.
  const ta = Math.min(approveMax, declineMin - 0.01);
  const td = Math.max(declineMin, ta + 0.01);

  const result = useMemo(() => {
    let approve = 0;
    let refer = 0;
    let decline = 0;
    let exposure = 0;
    let cost = 0;
    for (const b of bins) {
      const exp = b.mean_exposure * b.count;
      exposure += exp;
      if (b.pd <= ta) {
        approve += b.count;
        cost += costMatrix.false_approve * b.pd * exp;
      } else if (b.pd >= td) {
        decline += b.count;
        cost += costMatrix.false_decline * (1 - b.pd) * exp;
      } else {
        refer += b.count;
        cost += costMatrix.review * exp;
      }
    }
    const total = approve + refer + decline || 1;
    return {
      approve: approve / total,
      refer: refer / total,
      decline: decline / total,
      costPerLoan: exposure ? cost / exposure : 0,
    };
  }, [bins, ta, td, costMatrix]);

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <Slider
          label="Approve band — approve when risk ≤"
          value={ta}
          onChange={setApproveMax}
        />
        <Slider
          label="Decline band — decline when risk ≥"
          value={td}
          onChange={setDeclineMin}
        />
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Mini label="Approved" value={formatPct(result.approve)} tone="emerald" />
        <Mini label="Referred" value={formatPct(result.refer)} tone="amber" />
        <Mini label="Declined" value={formatPct(result.decline)} tone="rose" />
        <Mini
          label="Est. cost / loan"
          value={formatNum(result.costPerLoan, 4)}
          tone="slate"
        />
      </div>
      <p className="text-[11px] text-slate-400">
        Simulated on the recorded out-of-sample scores. Cost per unit of loan
        exposure using the cost matrix from the model card.
      </p>
    </div>
  );
}

function Slider({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between text-xs text-slate-600">
        <span>{label}</span>
        <span className="font-medium tabular-nums text-slate-800">{formatPct(value, 0)}</span>
      </div>
      <input
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-brand-600"
      />
    </div>
  );
}

function Mini({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "emerald" | "amber" | "rose" | "slate";
}) {
  const tones: Record<string, string> = {
    emerald: "text-emerald-700",
    amber: "text-amber-700",
    rose: "text-rose-700",
    slate: "text-slate-700",
  };
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`text-lg font-semibold tabular-nums ${tones[tone]}`}>{value}</p>
    </div>
  );
}
