"use client";

import { useState } from "react";
import { Bug, Loader2, ShieldCheck, Zap } from "lucide-react";
import { api } from "@/lib/api";
import type { BiasInjectResult, MitigationAttribute } from "@/lib/types";
import { cn, formatPct } from "@/lib/utils";
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
  groupsByAttribute: Record<string, string[]>;
  attributes: MitigationAttribute[];
  defaultAttribute: string;
  defaults: { approve_max_pd: number; decline_min_pd: number };
  floor: number;
}

function DiBar({
  label,
  value,
  floor,
  tone,
}: {
  label: string;
  value: number | null;
  floor: number;
  tone: "clean" | "biased" | "recovered";
}) {
  const pct = value === null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  const colour =
    tone === "biased"
      ? "bg-rose-500"
      : tone === "recovered"
        ? "bg-emerald-500"
        : "bg-sky-500";
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
      <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mono mt-1 text-lg font-semibold text-slate-100">
        {value === null ? "—" : value.toFixed(3)}
      </p>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
        <div className={cn("h-full rounded-full", colour)} style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1 text-[10px] text-slate-500">
        floor {floor.toFixed(2)} ·{" "}
        {value !== null && value >= floor ? "pass" : "below floor"}
      </p>
    </div>
  );
}

/**
 * Bias injector.
 *
 * A deliberately adversarial tool: it multiplies one group's scores to simulate
 * a biased model, then shows the four-fifths guardrail firing and whether the
 * mitigation can recover it. Nothing here touches the real model — it is a
 * teaching aid for "what would our controls do if the model were unfair?".
 */
export function BiasInjector({
  groupsByAttribute,
  attributes,
  defaultAttribute,
  defaults,
  floor,
}: Props) {
  const [attribute, setAttribute] = useState(defaultAttribute);
  const [group, setGroup] = useState("");
  const [factor, setFactor] = useState(1.6);
  const [result, setResult] = useState<BiasInjectResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Groups belong to the selected attribute, and the portfolio slice arrives
  // asynchronously, so derive the effective selection during render rather than
  // syncing it into state: the chosen group is used only if it still belongs to
  // the current attribute, otherwise we fall back to the attribute's first group.
  const groups = groupsByAttribute[attribute] ?? [];
  const selectedGroup = groups.includes(group) ? group : (groups[0] ?? "");

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.biasInject({
        group: selectedGroup,
        factor,
        approve_max_pd: defaults.approve_max_pd,
        decline_min_pd: defaults.decline_min_pd,
        mitigation_attribute: attribute,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Injection failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Panel>
      <PanelHeader>
        <div>
          <PanelTitle>
            <Bug className="h-4 w-4 text-rose-400" />
            Bias injector
          </PanelTitle>
          <PanelDescription>
            Skew one group&apos;s scores, watch the guardrail fire, then see whether
            mitigation recovers it. Simulation only — the real model is untouched.
          </PanelDescription>
        </div>
        <DarkBadge tone="warn">adversarial</DarkBadge>
      </PanelHeader>

      <PanelBody className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <DarkLabel>Group to skew</DarkLabel>
            <select
              value={selectedGroup}
              onChange={(e) => setGroup(e.target.value)}
              className={darkInputClass}
            >
              {groups.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </div>
          <div>
            <DarkLabel>Score multiplier: ×{factor.toFixed(2)}</DarkLabel>
            <input
              type="range"
              min={1}
              max={4}
              step={0.1}
              value={factor}
              onChange={(e) => setFactor(Number(e.target.value))}
              className="mt-2 h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-rose-500"
            />
          </div>
          <div>
            <DarkLabel>Attribute under audit</DarkLabel>
            <select
              value={attribute}
              onChange={(e) => {
                setAttribute(e.target.value);
                setResult(null);
              }}
              className={darkInputClass}
            >
              {attributes.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          type="button"
          onClick={() => void run()}
          disabled={loading || !selectedGroup}
          className="inline-flex items-center gap-2 rounded-lg bg-rose-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-rose-500 disabled:opacity-60"
        >
          {loading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Zap className="h-3.5 w-3.5" />
          )}
          Inject bias and evaluate
        </button>

        {error ? (
          <p className="rounded-lg border border-rose-900 bg-rose-950/50 px-3 py-2 text-xs text-rose-300">
            {error}
          </p>
        ) : null}

        {result ? (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <DiBar
                label="Clean portfolio"
                value={result.clean.disparate_impact_ratio}
                floor={floor}
                tone="clean"
              />
              <DiBar
                label="After injection"
                value={result.biased.disparate_impact_ratio}
                floor={floor}
                tone="biased"
              />
              <DiBar
                label="After mitigation"
                value={result.recovered.disparate_impact_ratio}
                floor={floor}
                tone="recovered"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2 text-[11px]">
              <DarkBadge tone={result.biased.guardrail.passed ? "good" : "bad"}>
                biased: {result.biased.guardrail.passed ? "pass" : "breach"}
              </DarkBadge>
              <DarkBadge tone={result.recovered.guardrail.passed ? "good" : "bad"}>
                mitigated: {result.recovered.guardrail.passed ? "pass" : "breach"}
              </DarkBadge>
              <span className="mono text-slate-400">
                EO gap {result.biased.equalized_odds_difference === null
                  ? "—"
                  : result.biased.equalized_odds_difference.toFixed(3)}{" "}
                →{" "}
                {result.recovered.equalized_odds_difference === null
                  ? "—"
                  : result.recovered.equalized_odds_difference.toFixed(3)}
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-[11px]">
                <thead className="text-slate-500">
                  <tr>
                    <th className="py-1.5 pr-3 font-medium">Group</th>
                    <th className="py-1.5 pr-3 font-medium">n</th>
                    <th className="py-1.5 pr-3 font-medium">Selection rate</th>
                    <th className="py-1.5 pr-3 font-medium">Biased</th>
                    <th className="py-1.5 pr-3 font-medium">Mitigated</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  {result.biased.fairness_table.map((row, index) => {
                    const recoveredRow = result.recovered.fairness_table[index];
                    return (
                      <tr key={row.group} className="border-t border-slate-800">
                        <td className="py-1.5 pr-3">{row.group}</td>
                        <td className="mono py-1.5 pr-3">{row.n}</td>
                        <td className="mono py-1.5 pr-3">
                          {formatPct(row.selection_rate, 1)}
                        </td>
                        <td className="mono py-1.5 pr-3 text-rose-300">
                          {formatPct(row.selection_rate, 1)}
                        </td>
                        <td className="mono py-1.5 pr-3 text-emerald-300">
                          {recoveredRow
                            ? formatPct(recoveredRow.selection_rate, 1)
                            : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <p className="flex items-start gap-1.5 text-[11px] text-slate-500">
              <ShieldCheck className="mt-0.5 h-3 w-3 shrink-0" />
              {result.injection.note}
            </p>
          </>
        ) : (
          <p className="text-xs text-slate-500">
            Choose a group and inject a skew to see the controls respond.
          </p>
        )}
      </PanelBody>
    </Panel>
  );
}
