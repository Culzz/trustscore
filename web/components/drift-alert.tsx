"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, Bell, Loader2, RefreshCw, Waves } from "lucide-react";
import { api } from "@/lib/api";
import type { DriftResult } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  DarkBadge,
  Panel,
  PanelBody,
  PanelDescription,
  PanelHeader,
  PanelTitle,
  Stat,
} from "@/components/ui/panel";

const SEVERITY_TONE: Record<string, "good" | "warn" | "bad"> = {
  ok: "good",
  warning: "warn",
  critical: "bad",
};

/**
 * Live drift & adversarial alerting panel.
 *
 * Compares the most recent submissions against the stored training reference
 * with PSI (and KS where a reference sample exists), then reports an
 * adversarial-validation proxy. When no storage is configured — the Vercel
 * default — it runs a clearly-labelled simulated window so the control can still
 * be demonstrated end to end.
 */
export function DriftAlert() {
  const [drift, setDrift] = useState<DriftResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [alertMessage, setAlertMessage] = useState<string | null>(null);

  const load = useCallback(async (shift = 0) => {
    setLoading(true);
    try {
      setDrift(await api.driftLive(shift));
    } catch {
      setDrift(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(0);
  }, [load]);

  const sendAlert = async () => {
    setLoading(true);
    try {
      const res = await api.alertTest({
        severity: drift?.severity === "critical" ? "critical" : "warning",
        message: "TrustScore drift check (test alert).",
        shift: 1.5,
        deliver: false,
      });
      setAlertMessage(
        res.webhook_configured
          ? "Alert payload dispatched to the configured webhook."
          : "Alert payload generated — set ALERT_WEBHOOK_URL to deliver it.",
      );
    } catch {
      setAlertMessage("Could not generate the alert payload.");
    } finally {
      setLoading(false);
    }
  };

  const features = drift?.features
    ? Object.entries(drift.features)
        .sort((a, b) => b[1].psi - a[1].psi)
        .slice(0, 8)
    : [];

  return (
    <Panel>
      <PanelHeader>
        <div>
          <PanelTitle>
            <Activity className="h-4 w-4 text-brand-400" />
            Live drift &amp; adversarial alerting
          </PanelTitle>
          <PanelDescription>
            PSI/KS of recent traffic against the training reference.
          </PanelDescription>
        </div>
        <div className="flex items-center gap-2">
          {loading ? <Loader2 className="h-4 w-4 animate-spin text-slate-500" /> : null}
          {drift ? (
            <DarkBadge tone={SEVERITY_TONE[drift.severity ?? "ok"] ?? "default"}>
              {drift.severity ?? "ok"}
            </DarkBadge>
          ) : null}
        </div>
      </PanelHeader>

      <PanelBody className="space-y-4">
        {drift && !drift.available ? (
          <p className="text-xs text-slate-500">
            {drift.note ?? "Reference distributions unavailable."}
          </p>
        ) : null}

        {drift?.available ? (
          <>
            <div className="grid gap-3 sm:grid-cols-4">
              <Stat
                label="Max PSI"
                value={drift.max_psi === undefined ? "—" : drift.max_psi.toFixed(3)}
                hint={`warn ≥ ${drift.thresholds?.psi_moderate ?? 0.2}`}
                tone={
                  (drift.max_psi ?? 0) >= (drift.thresholds?.psi_moderate ?? 0.2)
                    ? "warn"
                    : "good"
                }
              />
              <Stat
                label="Max KS"
                value={
                  drift.max_ks === null || drift.max_ks === undefined
                    ? "—"
                    : drift.max_ks.toFixed(3)
                }
                hint={`warn ≥ ${drift.thresholds?.ks_moderate ?? 0.1}`}
              />
              <Stat
                label="Adversarial proxy AUC"
                value={
                  drift.adversarial_validation
                    ? drift.adversarial_validation.proxy_auc.toFixed(3)
                    : "—"
                }
                tone={
                  (drift.adversarial_validation?.proxy_auc ?? 0.5) >= 0.6
                    ? "warn"
                    : "good"
                }
              />
              <Stat
                label="Window"
                value={String(drift.n ?? 0)}
                hint={drift.window}
              />
            </div>

            {drift.simulated ? (
              <p className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-[11px] text-slate-400">
                <Waves className="mr-1 inline h-3 w-3" />
                {drift.note}
                {drift.storage_enabled === false
                  ? " Storage is disabled, so no live stream exists."
                  : ""}
              </p>
            ) : null}

            {drift.alerts && drift.alerts.length > 0 ? (
              <div className="rounded-lg border border-amber-900 bg-amber-950/40 px-3 py-2">
                <p className="text-[11px] font-semibold text-amber-300">
                  {drift.alerts.length} feature(s) above the drift threshold
                </p>
                <ul className="mt-1 flex flex-wrap gap-1.5">
                  {drift.alerts.map((a) => (
                    <li key={`${a.feature}-${a.statistic}`}>
                      <DarkBadge tone="warn">
                        {a.feature} · {a.statistic} {a.value.toFixed(3)}
                      </DarkBadge>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="rounded-lg border border-emerald-900 bg-emerald-950/30 px-3 py-2 text-[11px] text-emerald-300">
                No feature has moved beyond the drift threshold.
              </p>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-left text-[11px]">
                <thead className="text-slate-500">
                  <tr>
                    <th className="py-1.5 pr-3 font-medium">Feature</th>
                    <th className="py-1.5 pr-3 font-medium">Type</th>
                    <th className="py-1.5 pr-3 font-medium">PSI</th>
                    <th className="py-1.5 pr-3 font-medium">Verdict</th>
                    <th className="py-1.5 pr-3 font-medium">KS</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  {features.map(([name, info]) => (
                    <tr key={name} className="border-t border-slate-800">
                      <td className="py-1.5 pr-3">{name}</td>
                      <td className="py-1.5 pr-3 text-slate-500">{info.type}</td>
                      <td className="mono py-1.5 pr-3">{info.psi.toFixed(3)}</td>
                      <td className="py-1.5 pr-3">
                        <span
                          className={cn(
                            "mono",
                            info.psi >= (drift.thresholds?.psi_moderate ?? 0.2)
                              ? "text-amber-400"
                              : "text-emerald-400",
                          )}
                        >
                          {info.psi_verdict ?? "—"}
                        </span>
                      </td>
                      <td className="mono py-1.5 pr-3">
                        {info.ks === null || info.ks === undefined
                          ? "—"
                          : info.ks.toFixed(3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="text-[11px] text-slate-500">
              {drift.adversarial_validation?.note}
            </p>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void load(0)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-800"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Refresh
              </button>
              <button
                type="button"
                onClick={() => void load(1.5)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-amber-800 bg-amber-950/50 px-3 py-1.5 text-xs font-medium text-amber-200 transition hover:bg-amber-900/50"
              >
                <Waves className="h-3.5 w-3.5" />
                Simulate drift (shift +1.5σ)
              </button>
              <button
                type="button"
                onClick={() => void sendAlert()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-800"
              >
                <Bell className="h-3.5 w-3.5" />
                Send test alert
              </button>
            </div>

            {alertMessage ? (
              <p className="rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-[11px] text-slate-400">
                {alertMessage}
              </p>
            ) : null}
          </>
        ) : null}
      </PanelBody>
    </Panel>
  );
}
