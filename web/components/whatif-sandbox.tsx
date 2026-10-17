"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Loader2, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import type { Applicant, DecisionResponse } from "@/lib/types";
import { BAND_LABEL_TEXT, cn, formatMoney, formatPct } from "@/lib/utils";
import { BandBadge } from "@/components/ui/badge";
import { Label, Select } from "@/components/ui/field";
import { Button } from "@/components/ui/button";

const INTENTS: Applicant["loan_intent"][] = [
  "DEBTCONSOLIDATION",
  "EDUCATION",
  "HOMEIMPROVEMENT",
  "MEDICAL",
  "PERSONAL",
  "VENTURE",
];
const GRADES: Applicant["loan_grade"][] = ["A", "B", "C", "D", "E", "F", "G"];

interface Options {
  model?: string | null;
  applyFairness?: boolean;
  mitigationAttribute?: string | null;
}

function Pane({
  title,
  subtitle,
  result,
  loading,
  children,
}: {
  title: string;
  subtitle: string;
  result: DecisionResponse | null;
  loading: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col rounded-xl border border-slate-200 bg-white">
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            {title}
          </p>
          <p className="mt-0.5 text-[11px] text-slate-400">{subtitle}</p>
        </div>
        {loading ? <Loader2 className="h-4 w-4 animate-spin text-brand-500" /> : null}
      </div>

      <div className="space-y-3 px-4 py-4">
        <div className="flex items-center gap-3">
          {result ? (
            <BandBadge
              band={result.decision}
              label={BAND_LABEL_TEXT[result.band_label]}
            />
          ) : (
            <span className="h-6 w-20 animate-pulse rounded-full bg-slate-100" />
          )}
          <div className="text-xs text-slate-500">
            {result ? (
              <>
                <span className="mono font-semibold text-slate-800">
                  {formatPct(result.probability_of_default, 2)}
                </span>{" "}
                PD · expected cost{" "}
                <span className="mono">{formatMoney(result.expected_cost)}</span>
              </>
            ) : (
              "scoring…"
            )}
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

/**
 * Split-pane what-if sandbox.
 *
 * The left pane is the application as submitted and is frozen. The right pane is
 * a live copy you can mutate; both are scored through the real decision endpoint
 * on a debounce, so the comparison is against the actual model and policy rather
 * than a curated table.
 */
export function WhatIfSandbox({
  base,
  options,
}: {
  base: Applicant;
  options?: Options;
}) {
  const [variant, setVariant] = useState<Applicant>(base);
  const [resultA, setResultA] = useState<DecisionResponse | null>(null);
  const [resultB, setResultB] = useState<DecisionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const initial = useRef(base);

  // Re-seed the variant whenever a new application is submitted.
  useEffect(() => {
    setVariant(base);
    initial.current = base;
  }, [base]);

  const key = useMemo(() => JSON.stringify(variant), [variant]);

  useEffect(() => {
    let cancelled = false;
    const handle = setTimeout(async () => {
      setLoading(true);
      try {
        const opts = {
          model: options?.model ?? null,
          apply_fairness: options?.applyFairness ?? false,
          mitigation_attribute: options?.mitigationAttribute ?? null,
        };
        const [a, b] = await Promise.all([
          api.decision(base, opts),
          api.decision(variant, opts),
        ]);
        if (!cancelled) {
          setResultA(a);
          setResultB(b);
        }
      } catch {
        if (!cancelled) {
          setResultA(null);
          setResultB(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, JSON.stringify(base), options?.model, options?.applyFairness, options?.mitigationAttribute]);

  const set = <K extends keyof Applicant>(k: K, v: Applicant[K]) =>
    setVariant((a) => ({ ...a, [k]: v }));

  const bandChanged =
    resultA && resultB ? resultA.decision !== resultB.decision : false;
  const pdDelta =
    resultA && resultB
      ? resultB.probability_of_default - resultA.probability_of_default
      : null;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 lg:grid-cols-2">
        <Pane
          title="As submitted"
          subtitle="Frozen for comparison"
          result={resultA}
          loading={loading && !resultA}
        />

        <Pane
          title="What if…"
          subtitle="Adjust and watch it re-score"
          result={resultB}
          loading={loading && !resultB}
        >
          <div className="space-y-3 border-t border-slate-100 pt-3">
            <div>
              <Label>Requested amount</Label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={500}
                  max={40000}
                  step={500}
                  value={variant.loan_amnt}
                  onChange={(e) => set("loan_amnt", Number(e.target.value))}
                  className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-brand-600"
                />
                <span className="mono w-20 shrink-0 text-right text-xs text-slate-700">
                  {formatMoney(variant.loan_amnt)}
                </span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Loan purpose</Label>
                <Select
                  value={variant.loan_intent}
                  onChange={(e) =>
                    set("loan_intent", e.target.value as Applicant["loan_intent"])
                  }
                >
                  {INTENTS.map((o) => (
                    <option key={o} value={o}>
                      {o.replaceAll("_", " ")}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <Label>Loan grade</Label>
                <Select
                  value={variant.loan_grade}
                  onChange={(e) =>
                    set("loan_grade", e.target.value as Applicant["loan_grade"])
                  }
                >
                  {GRADES.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </Select>
              </div>
            </div>
            <div className="flex justify-end">
              <Button
                variant="ghost"
                size="sm"
                type="button"
                onClick={() => setVariant(initial.current)}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reset
              </Button>
            </div>
          </div>
        </Pane>
      </div>

      {resultA && resultB ? (
        <div
          className={cn(
            "flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2 text-xs",
            bandChanged
              ? "border-brand-200 bg-brand-50 text-brand-900"
              : "border-slate-200 bg-slate-50 text-slate-600",
          )}
        >
          <span className="flex items-center gap-2 font-medium">
            {BAND_LABEL_TEXT[resultA.band_label]}
            <ArrowRight className="h-3.5 w-3.5" />
            {BAND_LABEL_TEXT[resultB.band_label]}
          </span>
          <span className="mono">
            Δ PD {pdDelta !== null ? `${(pdDelta * 100).toFixed(2)} pts` : "—"}
          </span>
          <span className="mono">
            Δ expected cost{" "}
            {formatMoney(resultB.expected_cost - resultA.expected_cost)}
          </span>
          <span className="ml-auto text-[11px] opacity-70">
            Simulated against the live policy — not an offer.
          </span>
        </div>
      ) : null}
    </div>
  );
}
