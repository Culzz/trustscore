"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Loader2, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import type { AbCompareResult, MitigationAttribute } from "@/lib/types";
import { cn, formatMoney, formatPct } from "@/lib/utils";
import {
  DarkBadge,
  DarkLabel,
  Panel,
  PanelBody,
  PanelDescription,
  PanelHeader,
  PanelTitle,
  darkInputClass,
} from "@/components/ui/panel";

interface Props {
  defaults: { approve_max_pd: number; decline_min_pd: number };
  attributes: MitigationAttribute[];
  defaultAttribute: string;
  alphaLabel: string;
  betaLabel: string;
}

function CompareRow({
  label,
  alpha,
  beta,
  delta,
  higherIsBetter,
  format,
}: {
  label: string;
  alpha: string;
  beta: string;
  delta: number | null;
  higherIsBetter: boolean;
  format: (v: number) => string;
}) {
  const better = delta === null ? null : higherIsBetter ? delta > 0 : delta < 0;
  return (
    <tr className="border-t border-slate-800">
      <td className="py-2 pr-3 text-slate-400">{label}</td>
      <td className="mono py-2 pr-3 text-slate-200">{alpha}</td>
      <td className="mono py-2 pr-3 text-slate-200">{beta}</td>
      <td
        className={cn(
          "mono py-2 pr-3 font-semibold",
          better === null ? "text-slate-500" : better ? "text-emerald-400" : "text-rose-400",
        )}
      >
        {delta === null ? "—" : `${delta > 0 ? "+" : ""}${format(delta)}`}
      </td>
    </tr>
  );
}

/**
 * Alpha vs Beta model grid.
 *
 * Both models are scored on the same public portfolio slice (the full test
 * split) at the same policy, so the only difference between the columns is the
 * fairness post-processing. That is the whole point of an A/B here: not "which
 * model is better in the abstract", but "what does the mitigation cost, and what
 * does it buy".
 */
export function AbCompareGrid({
  defaults,
  attributes,
  defaultAttribute,
  alphaLabel,
  betaLabel,
}: Props) {
  const [attribute, setAttribute] = useState(defaultAttribute);
  const [result, setResult] = useState<AbCompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.abCompare({
        approve_max_pd: defaults.approve_max_pd,
        decline_min_pd: defaults.decline_min_pd,
        mitigation_attribute: attribute,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed.");
    } finally {
      setLoading(false);
    }
  }, [attribute, defaults.approve_max_pd, defaults.decline_min_pd]);

  useEffect(() => {
    void run();
  }, [run]);

  return (
    <Panel>
      <PanelHeader>
        <div>
          <PanelTitle>
            <Sparkles className="h-4 w-4 text-brand-400" />
            Model A/B — {alphaLabel} vs {betaLabel}
          </PanelTitle>
          <PanelDescription>
            Same booster, same portfolio, same policy. Beta adds equalized-odds
            post-processing on the selected attribute.
          </PanelDescription>
        </div>
        <div className="flex items-center gap-2">
          {loading ? <Loader2 className="h-4 w-4 animate-spin text-slate-500" /> : null}
          <select
            value={attribute}
            onChange={(e) => setAttribute(e.target.value)}
            className={cn(darkInputClass, "w-44")}
            aria-label="Mitigation attribute"
          >
            {attributes.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
        </div>
      </PanelHeader>

      <PanelBody className="space-y-4">
        {error ? (
          <p className="rounded-lg border border-rose-900 bg-rose-950/50 px-3 py-2 text-xs text-rose-300">
            {error}
          </p>
        ) : null}

        {result ? (
          <>
            <div className="grid gap-2 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
                <p className="text-[10px] uppercase tracking-wide text-slate-500">
                  {result.labels?.alpha ?? alphaLabel}
                </p>
                <p className="mono mt-1 text-sm text-slate-200">
                  DI{" "}
                  {result.alpha.disparate_impact_ratio === null
                    ? "—"
                    : result.alpha.disparate_impact_ratio.toFixed(3)}
                </p>
                <DarkBadge tone={result.alpha.guardrail.passed ? "good" : "bad"}>
                  {result.alpha.guardrail.n_breaches} breach
                  {result.alpha.guardrail.n_breaches === 1 ? "" : "es"}
                </DarkBadge>
              </div>
              <div className="flex items-center justify-center">
                <ArrowRight className="h-5 w-5 text-slate-600" />
              </div>
              <div className="rounded-lg border border-brand-900 bg-brand-950/30 px-3 py-2">
                <p className="text-[10px] uppercase tracking-wide text-brand-400">
                  {result.labels?.beta ?? betaLabel}
                </p>
                <p className="mono mt-1 text-sm text-slate-100">
                  DI{" "}
                  {result.beta.disparate_impact_ratio === null
                    ? "—"
                    : result.beta.disparate_impact_ratio.toFixed(3)}
                </p>
                <DarkBadge tone={result.beta.guardrail.passed ? "good" : "bad"}>
                  {result.beta.guardrail.n_breaches} breach
                  {result.beta.guardrail.n_breaches === 1 ? "" : "es"}
                </DarkBadge>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-[11px]">
                <thead className="text-slate-500">
                  <tr>
                    <th className="py-1.5 pr-3 font-medium">Metric</th>
                    <th className="py-1.5 pr-3 font-medium">
                      {result.labels?.alpha ?? alphaLabel}
                    </th>
                    <th className="py-1.5 pr-3 font-medium">
                      {result.labels?.beta ?? betaLabel}
                    </th>
                    <th className="py-1.5 pr-3 font-medium">Δ (Beta − Alpha)</th>
                  </tr>
                </thead>
                <tbody>
                  <CompareRow
                    label="Approval rate"
                    alpha={formatPct(result.alpha.approval_rate, 1)}
                    beta={formatPct(result.beta.approval_rate, 1)}
                    delta={result.delta.approval_rate ?? null}
                    higherIsBetter
                    format={(v) => `${(v * 100).toFixed(2)} pts`}
                  />
                  <CompareRow
                    label="Expected cost / loan"
                    alpha={formatMoney(result.alpha.expected_cost_per_loan)}
                    beta={formatMoney(result.beta.expected_cost_per_loan)}
                    delta={result.delta.expected_cost_per_loan ?? null}
                    higherIsBetter={false}
                    format={(v) => formatMoney(v)}
                  />
                  <CompareRow
                    label="Profit / loan"
                    alpha={formatMoney(result.alpha.profit_per_loan)}
                    beta={formatMoney(result.beta.profit_per_loan)}
                    delta={result.delta.profit_per_loan ?? null}
                    higherIsBetter
                    format={(v) => formatMoney(v)}
                  />
                  <CompareRow
                    label="Disparate impact ratio"
                    alpha={
                      result.alpha.disparate_impact_ratio === null
                        ? "—"
                        : result.alpha.disparate_impact_ratio.toFixed(3)
                    }
                    beta={
                      result.beta.disparate_impact_ratio === null
                        ? "—"
                        : result.beta.disparate_impact_ratio.toFixed(3)
                    }
                    delta={result.delta.disparate_impact_ratio ?? null}
                    higherIsBetter
                    format={(v) => v.toFixed(3)}
                  />
                  <CompareRow
                    label="Equalized odds gap"
                    alpha={
                      result.alpha.equalized_odds_difference === null
                        ? "—"
                        : result.alpha.equalized_odds_difference.toFixed(3)
                    }
                    beta={
                      result.beta.equalized_odds_difference === null
                        ? "—"
                        : result.beta.equalized_odds_difference.toFixed(3)
                    }
                    delta={result.delta.equalized_odds_difference ?? null}
                    higherIsBetter={false}
                    format={(v) => v.toFixed(3)}
                  />
                </tbody>
              </table>
            </div>

            <p className="text-[11px] text-slate-500">
              Equalized odds targets true/false-positive parity, not selection-rate
              parity: it can widen approval rates for a group without moving the
              four-fifths ratio all the way to 1.0, and other attributes may still
              breach independently.
            </p>
          </>
        ) : (
          <p className="text-xs text-slate-500">Comparing models…</p>
        )}

        <div className="sr-only">
          <DarkLabel>Comparison summary</DarkLabel>
        </div>
      </PanelBody>
    </Panel>
  );
}
