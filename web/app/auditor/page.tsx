"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, ShieldAlert, ShieldCheck, Terminal } from "lucide-react";
import { api } from "@/lib/api";
import type {
  FairnessAttribute,
  MitigationInfo,
  ModelMetadata,
  ModelsResponse,
} from "@/lib/types";
import { cn, formatNum, formatPct } from "@/lib/utils";
import { useMode } from "@/components/mode-provider";
import {
  DarkBadge,
  Panel,
  PanelBody,
  PanelDescription,
  PanelHeader,
  PanelTitle,
  Stat,
} from "@/components/ui/panel";
import { PolicyLab } from "@/components/policy-lab";
import { AbCompareGrid } from "@/components/ab-compare-grid";
import { BiasInjector } from "@/components/bias-injector";
import { DriftAlert } from "@/components/drift-alert";
import { LineageTimeline } from "@/components/lineage-timeline";
import { ComplianceReportButton } from "@/components/compliance-report-button";
import { CalibrationChart } from "@/components/calibration-chart";
import { ScoreDistributionChart } from "@/components/score-distribution-chart";

export default function AuditorPage() {
  const { setMode } = useMode();
  const [meta, setMeta] = useState<ModelMetadata | null>(null);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [mitigation, setMitigation] = useState<MitigationInfo | null>(null);
  const [portfolio, setPortfolio] = useState<{
    n: number;
    group_attribute: string;
    attributes: string[];
    group_values: Record<string, string[]>;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setMode("auditor");
  }, [setMode]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [modelRes, modelsRes, mitigationRes, portfolioRes] =
        await Promise.allSettled([
          api.model(),
          api.models(),
          api.mitigation(),
          api.portfolio(),
        ]);
      if (cancelled) return;
      if (modelRes.status === "fulfilled") {
        setMeta(modelRes.value);
      } else {
        setError(
          "Could not load model metadata. Is the backend running and has training been run?",
        );
      }
      if (modelsRes.status === "fulfilled") setModels(modelsRes.value);
      if (mitigationRes.status === "fulfilled") setMitigation(mitigationRes.value);
      if (portfolioRes.status === "fulfilled") setPortfolio(portfolioRes.value);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const defaults = useMemo(
    () => ({
      approve_max_pd: meta?.thresholds.approve_max_pd ?? 0.055,
      decline_min_pd: meta?.thresholds.decline_min_pd ?? 0.676,
    }),
    [meta],
  );

  const floor =
    mitigation?.disparate_impact_floor ?? meta?.fairness.disparate_impact_floor ?? 0.8;
  const attributes =
    mitigation?.attributes ??
    (meta ? [{ id: meta.fairness.guardrail?.mitigation_attribute ?? "age_band", label: "Age band" }] : []);
  const defaultAttribute =
    mitigation?.default_attribute ??
    meta?.fairness.guardrail?.mitigation_attribute ??
    "age_band";

  const calibrated = meta?.metrics?.calibrated;
  const guardrail = meta?.fairness.guardrail;
  const alphaLabel = models?.models.find((m) => m.role === "baseline")?.label ?? "Alpha";
  const betaLabel = models?.models.find((m) => m.role === "fair")?.label ?? "Beta";

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center gap-2 text-sm text-slate-400">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading the audit console…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <div className="flex items-center gap-2">
          <Terminal className="h-5 w-5 text-brand-400" />
          <h1 className="text-2xl font-semibold text-white">Auditor console</h1>
          <DarkBadge tone="warn">simulation</DarkBadge>
        </div>
        <p className="max-w-3xl text-sm text-slate-400">
          Governance view: policy simulation with the disparate-impact guardrail,
          Alpha/Beta model comparison, a bias injector, live drift and adversarial
          alerting, model lineage, and a one-click compliance report. Every figure
          is computed from the committed artifacts and the public portfolio slice.
        </p>
      </header>

      {error ? (
        <p className="rounded-lg border border-rose-900 bg-rose-950/50 px-3 py-2 text-xs text-rose-300">
          {error}
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <Stat
          label="ROC-AUC (calibrated)"
          value={calibrated?.roc_auc === undefined ? "—" : formatNum(calibrated.roc_auc, 4)}
        />
        <Stat
          label="PR-AUC"
          value={calibrated?.pr_auc === undefined ? "—" : formatNum(calibrated.pr_auc, 4)}
        />
        <Stat
          label="Brier"
          value={meta?.calibration.brier === null || meta?.calibration.brier === undefined ? "—" : formatNum(meta.calibration.brier, 4)}
        />
        <Stat
          label="ECE"
          value={meta?.calibration.ece === null || meta?.calibration.ece === undefined ? "—" : formatNum(meta.calibration.ece, 4)}
        />
        <Stat
          label="Guardrail (all attributes)"
          value={guardrail?.passed ? "PASS" : "BREACH"}
          tone={guardrail?.passed ? "good" : "bad"}
          hint={`${guardrail?.n_breaches ?? 0} breach(es) · floor ${floor.toFixed(2)}`}
        />
        <Stat
          label="Portfolio rows"
          value={portfolio ? portfolio.n.toLocaleString() : "—"}
          hint={`${Object.keys(portfolio?.group_values ?? {}).length} audited attributes`}
        />
      </div>

      <PolicyLab
        defaults={defaults}
        attributes={attributes}
        defaultAttribute={defaultAttribute}
        floor={floor}
      />

      <AbCompareGrid
        defaults={defaults}
        attributes={attributes}
        defaultAttribute={defaultAttribute}
        alphaLabel={alphaLabel}
        betaLabel={betaLabel}
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <BiasInjector
          groupsByAttribute={portfolio?.group_values ?? {}}
          attributes={attributes}
          defaultAttribute={defaultAttribute}
          defaults={defaults}
          floor={floor}
        />
        <DriftAlert />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel>
          <PanelHeader>
            <div>
              <PanelTitle>
                <ShieldAlert className="h-4 w-4 text-brand-400" />
                Fairness audit
              </PanelTitle>
              <PanelDescription>
                Per-attribute four-fifths guardrail and equalized-odds gap.
              </PanelDescription>
            </div>
          </PanelHeader>
          <PanelBody className="space-y-4">
            {meta ? (
              Object.entries(meta.fairness.attributes).map(([key, block]) => (
                <FairnessAuditTable key={key} name={key} block={block} floor={floor} />
              ))
            ) : null}
            <p className="text-[11px] text-slate-500">{meta?.fairness.disclaimer}</p>
            {meta?.fairness.unavailable_attributes?.length ? (
              <p className="text-[11px] text-slate-500">
                Not available in this dataset:{" "}
                {meta.fairness.unavailable_attributes.join(", ")}.
              </p>
            ) : null}
          </PanelBody>
        </Panel>

        <Panel>
          <PanelHeader>
            <div>
              <PanelTitle>
                <ShieldCheck className="h-4 w-4 text-brand-400" />
                Calibration &amp; score distribution
              </PanelTitle>
              <PanelDescription>
                Reliability of the probabilities and the PD distribution on test.
              </PanelDescription>
            </div>
          </PanelHeader>
          <PanelBody className="space-y-4">
            <CalibrationChart curve={meta?.calibration.curve ?? []} variant="dark" />
            <ScoreDistributionChart
              bins={meta?.score_distribution?.bins ?? []}
              variant="dark"
            />
            <p className="text-[11px] text-slate-500">
              Brier {formatNum(meta?.calibration.brier, 4)} · ECE{" "}
              {formatNum(meta?.calibration.ece, 4)}. Isotonic calibration is fitted
              with cross-validation on the training split only.
            </p>
          </PanelBody>
        </Panel>
      </div>

      {models ? <LineageTimeline data={models} /> : null}

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <Panel>
            <PanelHeader>
              <div>
                <PanelTitle>Known limitations</PanelTitle>
                <PanelDescription>
                  Stated honestly rather than estimated away.
                </PanelDescription>
              </div>
            </PanelHeader>
            <PanelBody>
              <ul className="space-y-2 text-xs text-slate-400">
                {(meta?.limitations ?? []).map((item) => (
                  <li key={item} className="flex gap-2">
                    <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-slate-600" />
                    {item}
                  </li>
                ))}
              </ul>
            </PanelBody>
          </Panel>
        </div>
        <ComplianceReportButton />
      </div>
    </div>
  );
}

function FairnessAuditTable({
  name,
  block,
  floor,
}: {
  name: string;
  block: FairnessAttribute;
  floor: number;
}) {
  const di = block.summary.disparate_impact_ratio;
  const passes = di === null || di === undefined ? true : di >= floor;
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40">
      <div className="flex items-center justify-between gap-2 border-b border-slate-800 px-3 py-2">
        <span className="text-xs font-semibold text-slate-200">{block.label}</span>
        <div className="flex items-center gap-2">
          <span className="mono text-[11px] text-slate-400">
            DI {di === null || di === undefined ? "—" : di.toFixed(3)}
          </span>
          <DarkBadge tone={passes ? "good" : "bad"}>
            {passes ? "pass" : "breach"}
          </DarkBadge>
        </div>
      </div>
      <div className="overflow-x-auto px-3 py-2">
        <table className="w-full text-left text-[11px]">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-3 font-medium">Group</th>
              <th className="py-1 pr-3 font-medium">n</th>
              <th className="py-1 pr-3 font-medium">Approval</th>
              <th className="py-1 pr-3 font-medium">TPR</th>
              <th className="py-1 pr-3 font-medium">FPR</th>
            </tr>
          </thead>
          <tbody className="text-slate-300">
            {block.groups.map((g) => (
              <tr key={`${name}-${g.group}`} className="border-t border-slate-800">
                <td className="py-1 pr-3">
                  {g.group}
                  {g.low_sample ? <span className="ml-1 text-amber-400">*</span> : null}
                </td>
                <td className="mono py-1 pr-3">{g.n.toLocaleString()}</td>
                <td className="mono py-1 pr-3">{formatPct(g.selection_rate)}</td>
                <td className="mono py-1 pr-3">{formatPct(g.tpr)}</td>
                <td className="mono py-1 pr-3">{formatPct(g.fpr)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-2 border-t border-slate-800 px-3 py-2 text-[10px] text-slate-500">
        <span className="mono">
          DP gap{" "}
          <span className={cn("text-slate-300")}>
            {formatNum(block.summary.demographic_parity_difference, 3)}
          </span>
        </span>
        <span className="mono">
          EO gap{" "}
          <span className="text-slate-300">
            {formatNum(block.summary.equalized_odds_difference ?? block.summary.equal_opportunity_difference, 3)}
          </span>
        </span>
        <span className="mono">
          min/max selection{" "}
          <span className="text-slate-300">
            {formatNum(block.summary.selection_rate_ratio, 3)}
          </span>
        </span>
      </div>
    </div>
  );
}
