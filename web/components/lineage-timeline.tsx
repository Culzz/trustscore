"use client";

import { GitBranch, GitCommitHorizontal, History } from "lucide-react";
import type { ModelsResponse } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  DarkBadge,
  Panel,
  PanelBody,
  PanelDescription,
  PanelHeader,
  PanelTitle,
} from "@/components/ui/panel";

/**
 * Model-version lineage timeline.
 *
 * Lineage is tracked in the internal `registry.json` the training pipeline
 * writes, deliberately avoiding an MLflow dependency: each entry records its
 * parent, when it was trained, what changed, and the measured metrics and
 * fairness numbers for that version.
 */
export function LineageTimeline({ data }: { data: ModelsResponse }) {
  const parentOf = new Map(data.lineage.map((l) => [l.version, l.parent]));
  const noteOf = new Map(data.lineage.map((l) => [l.version, l.note]));

  return (
    <Panel>
      <PanelHeader>
        <div>
          <PanelTitle>
            <History className="h-4 w-4 text-brand-400" />
            Model lineage
          </PanelTitle>
          <PanelDescription>
            Version history, parents and the measured effect of each change.
          </PanelDescription>
        </div>
        <DarkBadge tone="info">
          {data.models.length} version{data.models.length === 1 ? "" : "s"}
        </DarkBadge>
      </PanelHeader>

      <PanelBody>
        <ol className="relative space-y-4 border-l border-slate-800 pl-5">
          {data.models.map((model) => {
            const isFair = model.role === "fair";
            return (
              <li key={model.version} className="relative">
                <span
                  className={cn(
                    "absolute -left-[26px] top-1 flex h-3 w-3 items-center justify-center rounded-full border-2",
                    isFair
                      ? "border-brand-400 bg-brand-500"
                      : "border-slate-600 bg-slate-700",
                  )}
                />
                <div className="flex flex-wrap items-center gap-2">
                  <span className="mono text-sm font-semibold text-slate-100">
                    {model.version}
                  </span>
                  <DarkBadge tone={isFair ? "info" : "default"}>
                    {model.role}
                  </DarkBadge>
                  {parentOf.get(model.version) ? (
                    <span className="flex items-center gap-1 text-[10px] text-slate-500">
                      <GitBranch className="h-3 w-3" />
                      parent {parentOf.get(model.version)}
                    </span>
                  ) : null}
                  <span className="ml-auto text-[10px] text-slate-500">
                    {model.trained_at ?? "—"}
                  </span>
                </div>

                <p className="mt-1 text-xs text-slate-400">
                  {model.label}
                  {noteOf.get(model.version) ? ` — ${noteOf.get(model.version)}` : ""}
                </p>

                <div className="mt-2 grid gap-2 sm:grid-cols-4">
                  <Metric label="ROC-AUC" value={model.metrics?.roc_auc} digits={4} />
                  <Metric label="Brier" value={model.metrics?.brier} digits={4} />
                  <Metric label="ECE" value={model.metrics?.ece} digits={4} />
                  <Metric
                    label="DI ratio"
                    value={model.fairness?.disparate_impact_ratio}
                    digits={3}
                  />
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
                  <span className="flex items-center gap-1">
                    <GitCommitHorizontal className="h-3 w-3" />
                    {model.artifact}
                  </span>
                  <span>·</span>
                  <span>{model.metadata}</span>
                  {model.fairness ? (
                    <>
                      <span>·</span>
                      <DarkBadge
                        tone={model.fairness.guardrail_passed ? "good" : "bad"}
                      >
                        {model.fairness.n_breaches ?? 0} breach
                        {(model.fairness.n_breaches ?? 0) === 1 ? "" : "es"}
                      </DarkBadge>
                      {model.fairness.attribute ? (
                        <span>mitigation on {model.fairness.attribute}</span>
                      ) : null}
                    </>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>

        <p className="mt-4 text-[11px] text-slate-500">
          Lineage is recorded in the bundled <span className="mono">registry.json</span>{" "}
          written by the training pipeline — no external tracking server required.
        </p>
      </PanelBody>
    </Panel>
  );
}

function Metric({
  label,
  value,
  digits,
}: {
  label: string;
  value: number | null | undefined;
  digits: number;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mono mt-0.5 text-sm text-slate-200">
        {value === null || value === undefined ? "—" : value.toFixed(digits)}
      </p>
    </div>
  );
}
