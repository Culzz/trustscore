"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Download, Loader2 } from "lucide-react";
import { api, ApiError, API_BASE } from "@/lib/api";
import type { ModelMetadata } from "@/lib/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FairnessExplorer } from "@/components/fairness-explorer";
import { formatNum, formatPct } from "@/lib/utils";

export default function ModelCardPage() {
  const [meta, setMeta] = useState<ModelMetadata | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .model()
      .then(setMeta)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not load the model card."),
      );
  }, []);

  if (error) {
    return (
      <div className="mx-auto max-w-xl rounded-xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
        <div className="mb-2 flex items-center gap-2 font-semibold">
          <AlertTriangle className="h-5 w-5" /> {error}
        </div>
        <p>
          Run <code className="rounded bg-white px-1">python -m training.src.train</code>{" "}
          first.
        </p>
      </div>
    );
  }

  if (!meta) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading model card…
      </div>
    );
  }

  const ds = meta.dataset;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold text-slate-900">Model Card</h1>
          <p className="text-sm text-slate-600">
            Version <span className="font-medium text-slate-800">{meta.version}</span> ·
            generated {new Date(meta.trained_at).toLocaleString()}
          </p>
        </div>
        <a
          href={`${API_BASE}/model`}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          <Download className="h-4 w-4" /> Raw JSON
        </a>
      </header>

      <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
        {meta.disclaimer}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm text-slate-700">
            <p>
              TrustScore estimates the probability that a loan applicant defaults,
              turns it into a simulated approve/refer/decline decision under an
              explicit cost matrix, explains the estimate in plain language, and
              audits group-level disparities.
            </p>
            <p className="text-slate-500">
              Intended for demonstration and study. Not for real lending, credit
              scoring of real people, or financial advice.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Data</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-slate-700">
            <Row label="Source" value={ds.name} />
            <Row label="Rows (clean)" value={ds.rows.toLocaleString()} />
            <Row label="Default rate" value={formatPct(ds.target_rate)} />
            <Row
              label="Splits"
              value={`${ds.split_sizes.train.toLocaleString()} / ${ds.split_sizes.validation.toLocaleString()} / ${ds.split_sizes.test.toLocaleString()}`}
            />
            <Row label="Seed" value={String(ds.seed)} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Performance (test split)</CardTitle>
          <CardDescription>Default is the positive class.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="py-2 pr-4">Model</th>
                  <th className="py-2 pr-4 text-right">ROC-AUC</th>
                  <th className="py-2 pr-4 text-right">PR-AUC</th>
                  <th className="py-2 pr-4 text-right">Brier</th>
                  <th className="py-2 pr-4 text-right">F1 @ 0.5</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ["Logistic regression (baseline)", "baseline_lr"],
                    ["LightGBM (uncalibrated)", "lightgbm"],
                    ["LightGBM (calibrated)", "calibrated"],
                  ] as const
                ).map(([label, key]) => (
                  <tr key={key} className="border-b border-slate-100">
                    <td className="py-2 pr-4 text-slate-700">{label}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {formatNum(meta.metrics[key]?.roc_auc, 4)}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {formatNum(meta.metrics[key]?.pr_auc, 4)}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {formatNum(meta.metrics[key]?.brier, 4)}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {formatNum(meta.metrics[key]?.f1, 3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Decision policy and cost</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm text-slate-700">
            <Row label="Approve when risk ≤" value={formatPct(meta.thresholds.approve_max_pd)} />
            <Row label="Decline when risk ≥" value={formatPct(meta.thresholds.decline_min_pd)} />
            <Row
              label="Expected cost / loan"
              value={formatNum(meta.thresholds.expected_cost_per_loan, 4)}
            />
            <Row
              label="False approve cost"
              value={String(meta.thresholds.cost_matrix.false_approve)}
            />
            <Row
              label="False decline cost"
              value={String(meta.thresholds.cost_matrix.false_decline)}
            />
            <Row label="Review cost" value={String(meta.thresholds.cost_matrix.review)} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Most influential features</CardTitle>
            <CardDescription>Mean absolute contribution (offline analysis).</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {meta.top_features.slice(0, 8).map((f) => (
                <li key={f.feature} className="flex items-center justify-between gap-4">
                  <span className="truncate text-slate-700">{f.feature}</span>
                  <span className="tabular-nums text-slate-500">
                    {formatNum(f.mean_abs_contribution, 4)}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Fairness</CardTitle>
        </CardHeader>
        <CardContent>
          <FairnessExplorer fairness={meta.fairness} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Limitations</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
            {meta.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-slate-100 py-1.5 last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-medium text-slate-800">{value}</span>
    </div>
  );
}
