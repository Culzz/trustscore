"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { ModelMetadata, StatsResponse } from "@/lib/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { StatCard } from "@/components/stat-card";
import { CalibrationChart } from "@/components/calibration-chart";
import { ScoreDistributionChart } from "@/components/score-distribution-chart";
import { FairnessExplorer } from "@/components/fairness-explorer";
import { ThresholdSimulator } from "@/components/threshold-simulator";
import { formatMoney, formatNum, formatPct } from "@/lib/utils";

export default function LenderPage() {
  const [meta, setMeta] = useState<ModelMetadata | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.model(), api.stats().catch(() => null)])
      .then(([m, s]) => {
        setMeta(m);
        setStats(s);
      })
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : "Could not load model data."),
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading dashboard…
      </div>
    );
  }

  if (error || !meta) {
    return (
      <div className="mx-auto max-w-xl rounded-xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-800">
        <div className="mb-2 flex items-center gap-2 font-semibold">
          <AlertTriangle className="h-5 w-5" /> Model data unavailable
        </div>
        <p>{error ?? "No metadata found."}</p>
        <p className="mt-2 text-rose-700">
          Run <code className="rounded bg-white px-1">python -m training.src.train</code>{" "}
          then restart the API.
        </p>
      </div>
    );
  }

  const t = meta.thresholds;
  const bands = t.test_band_counts ?? {};

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold text-slate-900">Lender / auditor view</h1>
          <p className="text-sm text-slate-600">
            Portfolio, calibration, fairness and policy controls for model{" "}
            <span className="font-medium text-slate-800">{meta.version}</span>.
          </p>
        </div>
        <p className="text-xs text-slate-500">
          Trained {new Date(meta.trained_at).toLocaleString()}
        </p>
      </header>

      {/* live counters */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-700">Live counters (last 30 days)</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <StatCard
            label="Predictions logged"
            value={stats?.enabled ? stats.total_predictions.toLocaleString() : "—"}
            hint={stats?.enabled ? stats.window : stats?.note ?? "storage disabled"}
          />
          <StatCard
            label="Mean estimated risk"
            value={stats?.enabled ? formatPct(stats.mean_pd) : "—"}
            hint="Across logged predictions"
          />
          <StatCard
            label="High-risk share"
            value={stats?.enabled ? formatPct(stats.high_risk_share) : "—"}
            hint="Decline band as a share of volume"
          />
        </div>
      </section>

      {/* portfolio */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <StatCard
          label="Approval rate (test)"
          value={formatPct(t.test_approval_rate)}
          hint={`Approve ≤ ${formatPct(t.approve_max_pd, 0)}`}
        />
        <StatCard
          label="Expected cost / loan"
          value={formatNum(t.expected_cost_per_loan, 4)}
          hint="Exposure-weighted, validation-tuned"
        />
        <StatCard
          label="Test ROC-AUC"
          value={formatNum(meta.metrics.calibrated.roc_auc, 3)}
          hint={`Brier ${formatNum(meta.metrics.calibrated.brier, 4)}`}
        />
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* calibration */}
        <Card>
          <CardHeader>
            <CardTitle>Calibration</CardTitle>
            <CardDescription>
              Predicted risk vs observed default rate. ECE{" "}
              {formatNum(meta.calibration.ece, 4)} · Brier{" "}
              {formatNum(meta.calibration.brier, 4)}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {meta.calibration.curve ? (
              <CalibrationChart curve={meta.calibration.curve} />
            ) : (
              <p className="text-sm text-slate-500">Curve not available.</p>
            )}
          </CardContent>
        </Card>

        {/* distribution */}
        <Card>
          <CardHeader>
            <CardTitle>Score distribution</CardTitle>
            <CardDescription>
              Out-of-sample estimated risk across {meta.score_distribution?.n?.toLocaleString() ?? "—"}{" "}
              applicants.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {meta.score_distribution?.bins ? (
              <ScoreDistributionChart bins={meta.score_distribution.bins} />
            ) : (
              <p className="text-sm text-slate-500">Distribution not available.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* thresholds */}
      <Card>
        <CardHeader>
          <CardTitle>Decision policy</CardTitle>
          <CardDescription>
            Move the thresholds and watch the mix and expected cost update.
            Band counts currently: approve {bands.approve ?? 0}, refer{" "}
            {bands.refer ?? 0}, decline {bands.decline ?? 0}.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {meta.policy_simulation?.bins ? (
            <ThresholdSimulator
              bins={meta.policy_simulation.bins}
              initial={{
                approve_max_pd: t.approve_max_pd,
                decline_min_pd: t.decline_min_pd,
              }}
              costMatrix={{
                false_approve: Number(t.cost_matrix.false_approve),
                false_decline: Number(t.cost_matrix.false_decline),
                review: Number(t.cost_matrix.review),
              }}
            />
          ) : (
            <p className="text-sm text-slate-500">Simulation data not available.</p>
          )}
        </CardContent>
      </Card>

      {/* fairness */}
      <Card>
        <CardHeader>
          <CardTitle>Fairness audit</CardTitle>
          <CardDescription>
            Statistical disparities by group. Not a legal compliance verdict.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <FairnessExplorer fairness={meta.fairness} />
        </CardContent>
      </Card>

      {/* drift */}
      {meta.drift ? (
        <Card>
          <CardHeader>
            <CardTitle>Input drift (PSI)</CardTitle>
            <CardDescription>{meta.drift.note}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {Object.entries(meta.drift.features).map(([feature, d]) => (
                <div
                  key={feature}
                  className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
                >
                  <p className="truncate text-[11px] font-medium text-slate-600" title={feature}>
                    {feature}
                  </p>
                  <p className="text-sm font-semibold tabular-nums text-slate-900">
                    {d.psi.toFixed(3)}
                  </p>
                  <p className="text-[10px] text-slate-400">{d.verdict}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
