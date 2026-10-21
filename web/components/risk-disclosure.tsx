"use client";

import { useState } from "react";
import { Eye, EyeOff, Info } from "lucide-react";
import type { Band, Thresholds } from "@/lib/types";
import { BAND_STYLES, bandText, cn, formatPct } from "@/lib/utils";

/**
 * Progressive risk-band disclosure.
 *
 * The first thing an applicant sees is the category, set like a verdict in a
 * printed notice, with no raw probability. The exact PD, the decision
 * thresholds and the model version sit behind one deliberate "show me the
 * numbers" step, so the headline stays human-readable while the detail is still
 * fully available.
 */
export function RiskDisclosure({
  band,
  probability,
  thresholds,
  modelVersion,
  group,
}: {
  band: Band;
  probability: number;
  thresholds: Thresholds;
  modelVersion: string;
  group?: string;
}) {
  const [revealed, setRevealed] = useState(false);
  const label = bandText(band);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Estimated category</p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <span
              className={cn(
                "font-display text-[34px] font-medium leading-none tracking-tight",
                BAND_STYLES[band].text,
              )}
            >
              {label}
            </span>
            <span className="stamp">Simulated</span>
          </div>
          <p className="mt-2 max-w-xs text-xs leading-relaxed text-slate-500">
            A category, not a promise. The exact estimate is available if you
            want it.
          </p>
        </div>

        <button
          type="button"
          onClick={() => setRevealed((v) => !v)}
          className="group inline-flex items-center gap-1.5 border-b border-slate-300 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-600 transition hover:border-brand-600 hover:text-brand-700"
          aria-expanded={revealed}
        >
          {revealed ? (
            <EyeOff className="h-3.5 w-3.5" strokeWidth={1.5} />
          ) : (
            <Eye className="h-3.5 w-3.5" strokeWidth={1.5} />
          )}
          {revealed ? "Hide the numbers" : "Show me the numbers"}
        </button>
      </div>

      <div className="space-y-1.5">
        <div className="flex gap-1">
          {(["approve", "refer", "decline"] as Band[]).map((b) => (
            <span
              key={b}
              className={cn(
                "h-2 flex-1 transition-colors",
                b === band ? BAND_STYLES[b].bar : "bg-slate-200",
              )}
            />
          ))}
        </div>
        <div className="flex justify-between text-[8px] font-semibold uppercase tracking-[0.16em] text-slate-400">
          <span>Approve</span>
          <span>Review</span>
          <span>Decline</span>
        </div>
      </div>

      {revealed ? (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-4 border-t border-slate-200 pt-4 sm:grid-cols-4">
          <div>
            <dt className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Probability of default
            </dt>
            <dd className="mono mt-1 text-base font-medium text-slate-900">
              {formatPct(probability, 2)}
            </dd>
          </div>
          <div>
            <dt className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Approve if PD ≤
            </dt>
            <dd className="mono mt-1 text-base font-medium text-slate-900">
              {formatPct(thresholds.approve_max_pd, 1)}
            </dd>
          </div>
          <div>
            <dt className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Decline if PD ≥
            </dt>
            <dd className="mono mt-1 text-base font-medium text-slate-900">
              {formatPct(thresholds.decline_min_pd, 1)}
            </dd>
          </div>
          <div>
            <dt className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Group / model
            </dt>
            <dd className="mono mt-1 text-base font-medium text-slate-900">
              {group ?? "—"}
            </dd>
            <dd className="mono mt-0.5 text-[9px] text-slate-400">{modelVersion}</dd>
          </div>
        </dl>
      ) : null}

      <p className="flex items-start gap-1.5 border-t border-slate-200 pt-3 text-[10px] leading-relaxed text-slate-400">
        <Info className="mt-0.5 h-3 w-3 shrink-0" strokeWidth={1.5} />
        <span>
          This is one model estimate and it carries real uncertainty — it is not
          a precise probability and not a promise of any outcome. A small change
          in the inputs can move the estimate across a category boundary.
        </span>
      </p>
    </div>
  );
}
