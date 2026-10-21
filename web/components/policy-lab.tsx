"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Loader2, Lock, Save, ShieldAlert, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { MitigationAttribute, SimulationResult } from "@/lib/types";
import { cn, formatMoney, formatPct } from "@/lib/utils";
import {
  DarkBadge,
  DarkLabel,
  Panel,
  PanelBody,
  PanelDescription,
  PanelHeader,
  PanelTitle,
  Stat,
  darkInputClass,
} from "@/components/ui/panel";

interface Props {
  defaults: { approve_max_pd: number; decline_min_pd: number };
  attributes: MitigationAttribute[];
  defaultAttribute: string;
  floor: number;
}

/**
 * Cost figures in the simulator are per unit of loan exposure, so they are small
 * fractions (e.g. 0.024). Rendering them as money shows "$0"; render them as
 * cents per $1 of exposure instead, which is what they actually are.
 */
function centsOfExposure(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(2)}¢`;
}

function signedCents(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${(Math.abs(value) * 100).toFixed(2)}¢`;
}

export function PolicyLab({ defaults, attributes, defaultAttribute, floor }: Props) {
  const [approve, setApprove] = useState(defaults.approve_max_pd);
  const [decline, setDecline] = useState(defaults.decline_min_pd);
  const [falseApprove, setFalseApprove] = useState(1);
  const [falseDecline, setFalseDecline] = useState(0.2);
  const [review, setReview] = useState(0.05);
  const [margin, setMargin] = useState(0.12);
  const [applyFairness, setApplyFairness] = useState(false);
  const [attribute, setAttribute] = useState(defaultAttribute);

  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState(false);
  const lastPass = useRef<boolean | null>(null);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.policySimulate({
        approve_max_pd: approve,
        decline_min_pd: decline,
        costs: { false_approve: falseApprove, false_decline: falseDecline, review },
        margin_rate: margin,
        apply_fairness: applyFairness,
        mitigation_attribute: attribute,
        include_sweep: true,
      });
      setResult(res);
      const passed = res.guardrail.passed;
      if (!passed && (lastPass.current === null || lastPass.current)) {
        setFlash(true);
        setTimeout(() => setFlash(false), 900);
      }
      lastPass.current = passed;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed.");
    } finally {
      setLoading(false);
    }
  }, [approve, decline, falseApprove, falseDecline, review, margin, applyFairness, attribute]);

  useEffect(() => {
    const handle = setTimeout(() => void run(), 250);
    return () => clearTimeout(handle);
  }, [run]);

  const sweepData = useMemo(() => result?.sweep?.points ?? [], [result]);
  const guardrailPassed = result?.guardrail.passed ?? false;
  const saveAllowed = result?.intercept?.save_policy_allowed ?? false;
  const auditedLabel =
    attributes.find((a) => a.id === result?.group_attribute)?.label ??
    result?.group_attribute ??
    "";

  return (
    <Panel className={cn("transition", flash && "ring-2 ring-amber-500/70")}>
      <PanelHeader>
        <div>
          <PanelTitle>
            <ShieldCheck className="h-4 w-4 text-brand-400" />
            Policy cutoff simulator
          </PanelTitle>
          <PanelDescription>
            Move the cut-offs and watch approval rate, cost, profitability and the
            fairness guardrail for the selected attribute move together. This runs on
            the <span className="text-slate-300">policy tuning set (validation)</span>;
            the model card reports the separate, held-out test split — tuning-set
            figures are not the published test figures.
          </PanelDescription>
        </div>
        <div className="flex items-center gap-2">
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin text-slate-500" />
          ) : null}
          {guardrailPassed ? (
            <DarkBadge tone="good">
              <ShieldCheck className="h-3 w-3" /> guardrail ok
            </DarkBadge>
          ) : (
            <DarkBadge tone="bad">
              <ShieldAlert className="h-3 w-3" /> breach
            </DarkBadge>
          )}
        </div>
      </PanelHeader>

      <PanelBody className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <DarkLabel>Approve if PD ≤ {formatPct(approve, 1)}</DarkLabel>
            <input
              type="range"
              min={0.005}
              max={0.4}
              step={0.005}
              value={approve}
              onChange={(e) => setApprove(Number(e.target.value))}
              className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-brand-500"
            />
          </div>
          <div>
            <DarkLabel>Decline if PD ≥ {formatPct(decline, 1)}</DarkLabel>
            <input
              type="range"
              min={Math.max(approve + 0.01, 0.05)}
              max={0.98}
              step={0.01}
              value={decline}
              onChange={(e) => setDecline(Number(e.target.value))}
              className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-brand-500"
            />
          </div>
          <div>
            <DarkLabel>Margin on repaid loans</DarkLabel>
            <input
              type="number"
              step={0.01}
              min={0}
              max={1}
              value={margin}
              onChange={(e) => setMargin(Number(e.target.value))}
              className={darkInputClass}
            />
          </div>
          <div>
            <DarkLabel>Cost of false approve / decline</DarkLabel>
            <div className="flex gap-2">
              <input
                type="number"
                step={0.05}
                min={0}
                value={falseApprove}
                onChange={(e) => setFalseApprove(Number(e.target.value))}
                className={darkInputClass}
              />
              <input
                type="number"
                step={0.05}
                min={0}
                value={falseDecline}
                onChange={(e) => setFalseDecline(Number(e.target.value))}
                className={darkInputClass}
              />
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
          <label className="flex items-center gap-2 text-xs text-slate-300">
            <span className="relative inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center">
              <input
                type="checkbox"
                checked={applyFairness}
                onChange={(e) => setApplyFairness(e.target.checked)}
                className="peer h-3.5 w-3.5 appearance-none rounded-[2px] border border-slate-600 bg-slate-950 transition checked:border-brand-500 checked:bg-brand-500"
              />
              <svg
                aria-hidden
                viewBox="0 0 10 10"
                className="pointer-events-none absolute h-2.5 w-2.5 text-slate-950 opacity-0 transition peer-checked:opacity-100"
              >
                <path
                  d="M1.5 5.5 4 8l4.5-6"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="square"
                />
              </svg>
            </span>
            Apply fairness mitigation (equalized odds)
          </label>
          <div className="min-w-[180px]">
            <DarkLabel>Attribute under audit</DarkLabel>
            <select
              value={attribute}
              onChange={(e) => setAttribute(e.target.value)}
              className={darkInputClass}
            >
              {attributes.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <DarkLabel>Review cost</DarkLabel>
            <input
              type="number"
              step={0.01}
              min={0}
              value={review}
              onChange={(e) => setReview(Number(e.target.value))}
              className={cn(darkInputClass, "w-24")}
            />
          </div>
        </div>

        {error ? (
          <p className="rounded-lg border border-rose-900 bg-rose-950/50 px-3 py-2 text-xs text-rose-300">
            {error}
          </p>
        ) : null}

        {result ? (
          <>
            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <Stat label="Approval rate" value={formatPct(result.approval_rate, 1)} />
              <Stat
                label="Expected cost / loan"
                value={centsOfExposure(result.expected_cost_per_loan)}
                hint="per $1 of exposure"
              />
              <Stat
                label="Realized cost / loan"
                value={centsOfExposure(result.realized_cost_per_loan)}
                hint="per $1 of exposure"
              />
              <Stat
                label="Profit / loan"
                value={formatMoney(result.profit_per_loan)}
                tone={result.profit_per_loan >= 0 ? "good" : "bad"}
              />
              <Stat
                label="Disparate impact"
                value={result.disparate_impact_ratio === null ? "—" : result.disparate_impact_ratio.toFixed(3)}
                hint={`floor ${floor.toFixed(2)}`}
                tone={
                  result.disparate_impact_ratio !== null &&
                  result.disparate_impact_ratio >= floor
                    ? "good"
                    : "bad"
                }
              />
              <Stat
                label="Equalized odds gap"
                value={
                  result.equalized_odds_difference === null
                    ? "—"
                    : result.equalized_odds_difference.toFixed(3)
                }
                tone="default"
              />
            </div>

            {result.uncertainty ? (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400">
                <span>
                  DI 95% CI:{" "}
                  <span className="mono text-slate-300">
                    {result.uncertainty.disparate_impact_ratio_ci
                      ? `[${result.uncertainty.disparate_impact_ratio_ci[0].toFixed(3)}, ${result.uncertainty.disparate_impact_ratio_ci[1].toFixed(3)}]`
                      : "n/a"}
                  </span>
                </span>
                <span className="text-slate-600">·</span>
                <span>
                  EO gap 95% CI:{" "}
                  <span className="mono text-slate-300">
                    {result.uncertainty.equalized_odds_difference_ci
                      ? `[${result.uncertainty.equalized_odds_difference_ci[0].toFixed(3)}, ${result.uncertainty.equalized_odds_difference_ci[1].toFixed(3)}]`
                      : "n/a"}
                  </span>
                </span>
                <span className="text-slate-600">·</span>
                <span>{result.uncertainty.n_boot} bootstrap resamples</span>
                <span className="text-slate-600">·</span>
                <span>sampling uncertainty only</span>
              </div>
            ) : null}

            {result.mitigation_cost ? (
              <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-[11px] text-slate-300">
                <div className="mb-1 font-medium text-slate-200">
                  Cost of this mitigation (tuning set)
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  <span>
                    Realized cost / $1 exposure{" "}
                    <span
                      className={cn(
                        "mono",
                        result.mitigation_cost.cost_per_loan_delta > 0
                          ? "text-amber-300"
                          : "text-emerald-300",
                      )}
                    >
                      {signedCents(result.mitigation_cost.cost_per_loan_delta)}
                    </span>
                  </span>
                  <span>
                    Approval rate{" "}
                    <span className="mono">
                      {result.mitigation_cost.approval_rate_delta >= 0 ? "+" : ""}
                      {formatPct(result.mitigation_cost.approval_rate_delta, 1)}
                    </span>
                  </span>
                  <span>
                    Attributes breaching{" "}
                    <span className="mono">
                      {result.mitigation_cost.breaches_base} →{" "}
                      {result.mitigation_cost.breaches_mitigated}
                    </span>
                  </span>
                </div>
                <p className="mt-1 text-slate-500">{result.mitigation_cost.note}</p>
              </div>
            ) : null}

            <div
              className={cn(
                "flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2 text-xs",
                saveAllowed
                  ? "border-emerald-900 bg-emerald-950/40 text-emerald-300"
                  : "border-amber-900 bg-amber-950/40 text-amber-200",
              )}
            >
              {saveAllowed ? (
                <ShieldCheck className="h-4 w-4" />
              ) : (
                <Lock className="h-4 w-4" />
              )}
              <span>{result.intercept?.reason}</span>
              {!saveAllowed
                ? result.guardrail.breaches.map((b) => (
                    <DarkBadge key={b.attribute} tone="bad">
                      {b.label} · {b.lowest_group}
                      {b.lowest_group_n ? ` (n=${b.lowest_group_n})` : ""} ·{" "}
                      {b.lowest_selection_rate === null
                        ? "—"
                        : formatPct(b.lowest_selection_rate, 1)}
                    </DarkBadge>
                  ))
                : null}
              <button
                type="button"
                disabled={!saveAllowed}
                className={cn(
                  "ml-auto inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition",
                  saveAllowed
                    ? "bg-brand-600 text-white hover:bg-brand-500"
                    : "cursor-not-allowed bg-slate-800 text-slate-500",
                )}
                title={
                  saveAllowed
                    ? "Save this policy"
                    : "Blocked: the fairness guardrail is breached"
                }
              >
                <Save className="h-3.5 w-3.5" />
                Save policy
              </button>
            </div>

            {result.mitigation_note ? (
              <p className="text-[11px] text-slate-500">{result.mitigation_note}</p>
            ) : null}

            {sweepData.length > 1 ? (
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={sweepData} margin={{ top: 8, right: 12, bottom: 4, left: -18 }}>
                    <CartesianGrid stroke="#362F25" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="approve_max_pd"
                      stroke="#857560"
                      fontSize={10}
                      tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                    />
                    <YAxis yAxisId="left" stroke="#857560" fontSize={10} domain={[0, 1]} />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      stroke="#857560"
                      fontSize={10}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#15110C",
                        border: "1px solid #362F25",
                        borderRadius: 3,
                        fontSize: 11,
                        color: "#F0E8D8",
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 10, color: "#A8977C" }} />
                    <ReferenceLine
                      yAxisId="left"
                      y={floor}
                      stroke="#CD9837"
                      strokeDasharray="4 4"
                      label={{ value: "DI floor", fill: "#CD9837", fontSize: 10 }}
                    />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="disparate_impact_ratio"
                      name="Disparate impact"
                      stroke="#6D99A2"
                      dot={false}
                      strokeWidth={1.75}
                    />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="approval_rate"
                      name="Approval rate"
                      stroke="#7F9E60"
                      dot={false}
                      strokeWidth={1.75}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="expected_cost_per_loan"
                      name="Expected cost / loan"
                      stroke="#C66A53"
                      dot={false}
                      strokeWidth={1.75}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : null}

            <div className="overflow-x-auto">
              <table className="w-full text-left text-[11px]">
                <thead className="text-slate-500">
                  <tr>
                    <th className="py-1.5 pr-3 font-medium">{auditedLabel}</th>
                    <th className="py-1.5 pr-3 font-medium">n</th>
                    <th className="py-1.5 pr-3 font-medium">Selection rate</th>
                    <th className="py-1.5 pr-3 font-medium">TPR</th>
                    <th className="py-1.5 pr-3 font-medium">FPR</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  {result.fairness_table.map((row) => (
                    <tr key={row.group} className="border-t border-slate-800">
                      <td className="py-1.5 pr-3">
                        {row.group}
                        {row.low_sample ? (
                          <span className="ml-1 text-amber-400">*</span>
                        ) : null}
                      </td>
                      <td className="mono py-1.5 pr-3">{row.n}</td>
                      <td className="mono py-1.5 pr-3">
                        {formatPct(row.selection_rate, 1)}
                        {row.selection_rate_ci ? (
                          <span className="ml-1 text-slate-500">
                            [{formatPct(row.selection_rate_ci[0], 0)},{" "}
                            {formatPct(row.selection_rate_ci[1], 0)}]
                          </span>
                        ) : null}
                      </td>
                      <td className="mono py-1.5 pr-3">
                        {row.tpr === null ? "—" : formatPct(row.tpr, 1)}
                      </td>
                      <td className="mono py-1.5 pr-3">
                        {row.fpr === null ? "—" : formatPct(row.fpr, 1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="text-xs text-slate-500">Running the simulation…</p>
        )}
      </PanelBody>
    </Panel>
  );
}
