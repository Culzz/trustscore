"use client";

import { CheckCircle2, Info, ShieldAlert } from "lucide-react";
import type { Narrative } from "@/lib/types";
import { cn } from "@/lib/utils";

const TONE_STYLE: Record<string, string> = {
  positive: "border-emerald-200 bg-emerald-50 text-emerald-900",
  neutral: "border-slate-200 bg-slate-50 text-slate-800",
  supportive: "border-brand-100 bg-brand-50 text-brand-900",
};

/**
 * The applicant-facing outline of reasons ("adverse-action notice").
 *
 * Rendered from deterministic, guardrailed templates: each reason carries an
 * ECOA-style code, protected characteristics are withheld from the notice, and
 * the whole thing passed a denylist + length guardrail before it got here. The
 * guardrail badge proves that check ran rather than asserting it.
 */
export function NoticeCard({ narrative }: { narrative: Narrative }) {
  const tone = TONE_STYLE[narrative.tone] ?? TONE_STYLE.neutral;

  return (
    <div className="space-y-4">
      <div className={cn("rounded-sm border border-l-2 p-3", tone)}>
        <p className="text-sm font-semibold">{narrative.headline}</p>
        <p className="mt-1 text-xs opacity-90">{narrative.encouragement}</p>
      </div>

      {narrative.reason_codes.length > 0 ? (
        <ul className="divide-y divide-slate-200 rounded-sm border border-slate-200">
          {narrative.reason_codes.map((code) => (
            <li key={code.code + code.factor} className="flex gap-3 p-3">
              <span className="mono shrink-0 rounded-sm bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                {code.code}
              </span>
              <div>
                <p className="text-xs font-semibold text-slate-800">{code.title}</p>
                <p className="mt-0.5 text-xs text-slate-600">{code.reason}</p>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {narrative.next_steps.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-slate-700">What you can do next</p>
          <ul className="mt-1.5 space-y-1">
            {narrative.next_steps.map((step) => (
              <li key={step} className="flex items-start gap-2 text-xs text-slate-600">
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                {step}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="rounded-sm border border-slate-200 bg-slate-100/40 p-3">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-600">
          {narrative.guardrail.passed ? (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
          ) : (
            <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
          )}
          Language guardrail:{" "}
          {narrative.guardrail.passed
            ? "passed"
            : `${narrative.guardrail.violations.length} violation(s)`}
        </p>
        <p className="mt-1 flex items-start gap-1.5 text-[11px] text-slate-500">
          <Info className="mt-0.5 h-3 w-3 shrink-0" />
          Provider: {narrative.guardrail.provider}. Protected characteristics are
          never cited in a consumer notice
          {narrative.protected_factors_excluded.length > 0
            ? ` (withheld here: ${narrative.protected_factors_excluded.join(", ")})`
            : ""}
          .
        </p>
      </div>

      <p className="text-[11px] text-slate-400">{narrative.notice}</p>
    </div>
  );
}
