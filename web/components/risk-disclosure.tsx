"use client";

import { useState } from "react";
import { Eye, EyeOff, Info } from "lucide-react";
import type { Band, Thresholds } from "@/lib/types";
import { BAND_STYLES, bandText, cn, formatPct } from "@/lib/utils";
import { BandBadge } from "@/components/ui/badge";

/**
 * Progressive risk-band disclosure.
 *
 * The first thing an applicant sees is the band, in plain words, with no raw
 * probability. The exact PD, the decision thresholds and the model version sit
 * behind one deliberate "show me the numbers" step, so the headline stays
 * human-readable while the detail is still fully available.
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
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <BandBadge band={band} label={label} />
        <span className="text-xs text-slate-500">
          Estimated risk category — {label.toLowerCase()}
        </span>
      </div>

      <button
        type="button"
        onClick={() => setRevealed((v) => !v)}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition",
          "border-slate-200 bg-white text-slate-600 hover:border-brand-300 hover:text-brand-700",
        )}
        aria-expanded={revealed}
      >
        {revealed ? (
          <EyeOff className="h-3.5 w-3.5" />
        ) : (
          <Eye className="h-3.5 w-3.5" />
        )}
        {revealed ? "Hide the numbers" : "Show me the numbers"}
      </button>

      {revealed ? (
        <dl className="grid grid-cols-2 gap-3 rounded-lg border border-slate-100 bg-slate-50 p-3 text-xs sm:grid-cols-4">
          <div>
            <dt className="text-slate-500">Probability of default</dt>
            <dd className="mono mt-0.5 text-base font-semibold text-slate-900">
              {formatPct(probability, 2)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Approve if PD ≤</dt>
            <dd className="mono mt-0.5 text-base font-semibold text-slate-900">
              {formatPct(thresholds.approve_max_pd, 1)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Decline if PD ≥</dt>
            <dd className="mono mt-0.5 text-base font-semibold text-slate-900">
              {formatPct(thresholds.decline_min_pd, 1)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Group / model</dt>
            <dd className="mono mt-0.5 text-base font-semibold text-slate-900">
              {group ?? "—"}
            </dd>
            <dd className="mono mt-0.5 text-[10px] text-slate-400">{modelVersion}</dd>
          </div>
        </dl>
      ) : (
        <p className="flex items-start gap-1.5 text-[11px] text-slate-400">
          <Info className="mt-0.5 h-3 w-3 shrink-0" />
          The estimate is a calibrated probability of default. The exact figure is
          hidden until you ask for it, because the category is what matters for a
          decision.
        </p>
      )}

      {revealed ? (
        <p className="flex items-start gap-1.5 text-[11px] text-slate-400">
          <Info className="mt-0.5 h-3 w-3 shrink-0" />
          This is one model estimate and it carries real uncertainty — it is not a
          precise probability and not a promise of any outcome. A small change in
          the inputs can move the estimate across a band boundary.
        </p>
      ) : null}

      <div className="flex gap-1">
        {(["approve", "refer", "decline"] as Band[]).map((b) => (
          <span
            key={b}
            className={cn(
              "h-1.5 flex-1 rounded-full",
              b === band ? BAND_STYLES[b].chip.split(" ")[0] : "bg-slate-200",
            )}
          />
        ))}
      </div>
    </div>
  );
}
