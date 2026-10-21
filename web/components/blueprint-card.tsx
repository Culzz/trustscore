"use client";

import {
  ArrowRight,
  BadgeCheck,
  GitCompareArrows,
  Lightbulb,
  Milestone,
  ShieldQuestion,
} from "lucide-react";
import type { Blueprint, BlueprintRoute } from "@/lib/types";
import { cn, formatMoney, formatPct, bandText } from "@/lib/utils";
import { BandBadge } from "@/components/ui/badge";

const CONFIDENCE_STYLE: Record<string, string> = {
  comfortable: "bg-emerald-50 text-emerald-700 border-emerald-200",
  moderate: "bg-sky-50 text-sky-700 border-sky-200",
  borderline: "bg-amber-50 text-amber-700 border-amber-200",
  none: "bg-slate-100 text-slate-600 border-slate-200",
};

const KIND_ICON: Record<string, typeof Lightbulb> = {
  changeable_by_applicant: Lightbulb,
  potentially_changeable: ShieldQuestion,
  milestone: Milestone,
};

const ACTIONABILITY_STYLE: Record<string, string> = {
  actionable: "bg-emerald-50 text-emerald-700 border-emerald-200",
  potentially_actionable: "bg-amber-50 text-amber-700 border-amber-200",
  immutable: "bg-slate-100 text-slate-600 border-slate-200",
};

const ACTIONABILITY_LABEL: Record<string, string> = {
  actionable: "actionable now",
  potentially_actionable: "potentially actionable",
  immutable: "immutable",
};

function RouteRow({ route }: { route: BlueprintRoute }) {
  const Icon = KIND_ICON[route.kind] ?? Lightbulb;
  const actionability = route.actionability ?? "actionable";
  return (
    <li className="rounded-sm border border-slate-200 bg-paper p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <Icon className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" strokeWidth={1.5} />
          <div>
            <p className="text-sm font-medium text-slate-900">{route.headline}</p>
            <p className="mt-0.5 text-sm text-slate-600">{route.detail}</p>
            <span
              className={cn(
                "mt-2 inline-block rounded-sm border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em]",
                ACTIONABILITY_STYLE[actionability] ?? ACTIONABILITY_STYLE.actionable,
              )}
            >
              {ACTIONABILITY_LABEL[actionability] ?? actionability}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <BandBadge
            band={route.metrics.new_band}
            label={bandText(route.metrics.new_band)}
          />
          <span
            className={cn(
              "rounded-sm border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em]",
              CONFIDENCE_STYLE[route.metrics.confidence] ?? CONFIDENCE_STYLE.none,
            )}
          >
            {route.metrics.confidence}
          </span>
        </div>
      </div>
      <p className="mono mt-2 text-[11px] text-slate-500">
        New estimated PD {formatPct(route.metrics.new_pd, 2)}
        {route.metrics.reduction !== undefined
          ? ` · reduction ${formatMoney(route.metrics.reduction)}`
          : ""}
        {route.metrics.intent ? ` · purpose ${route.metrics.intent.replaceAll("_", " ")}` : ""}
      </p>
    </li>
  );
}

/**
 * The "How to get approved" roadmap.
 *
 * Contrastive recourse: instead of a bare list of counterfactuals, this shows
 * independent routes to a better band, each with the exact change and the
 * resulting estimate, plus a dual-target framing — two different applicants can
 * reach the same band by different means. Income is surfaced only as an
 * explicitly-labelled, outside-your-control option, never as the headline.
 */
export function BlueprintCard({ blueprint }: { blueprint: Blueprint }) {
  if (blueprint.status === "already_approved") {
    return (
      <div className="flex items-start gap-3 rounded-sm border border-emerald-200 border-l-2 border-l-emerald-500 bg-emerald-50 p-4">
        <BadgeCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
        <div>
          <p className="text-sm font-semibold text-emerald-900">
            No changes needed under today&apos;s criteria
          </p>
          <p className="mt-1 text-sm text-emerald-800">{blueprint.summary}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">{blueprint.summary}</p>

      {blueprint.routes.length > 0 ? (
        <ul className="space-y-2">
          {blueprint.routes.map((route) => (
            <RouteRow key={route.id} route={route} />
          ))}
        </ul>
      ) : (
        <p className="rounded-sm border border-slate-200 bg-slate-100/40 p-3 text-sm text-slate-500">
          {blueprint.no_route_reason ??
            "No feasible change was found in the applicant-controlled fields under the current policy."}
        </p>
      )}

      {blueprint.dual_target ? (
        <div className="rounded-sm border border-brand-200 bg-brand-50 p-3">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-brand-900">
            <GitCompareArrows className="h-3.5 w-3.5" />
            {blueprint.dual_target.headline}
          </p>
          <ul className="mt-2 space-y-1.5">
            {blueprint.dual_target.options.map((option) => (
              <li
                key={option.change}
                className="flex items-center justify-between gap-2 text-xs text-brand-900"
              >
                <span className="flex items-center gap-1.5">
                  <ArrowRight className="h-3 w-3 shrink-0 opacity-60" />
                  {option.change}
                  {!option.within_control ? (
                    <span className="rounded-sm border border-brand-200 bg-paper px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-brand-700">
                      outside your control
                    </span>
                  ) : null}
                </span>
                <span className="shrink-0 font-medium capitalize">
                  {option.new_band} · {option.confidence}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-brand-800/80">
            {blueprint.dual_target.note}
          </p>
        </div>
      ) : null}

      {blueprint.immutable_fields && blueprint.immutable_fields.length > 0 ? (
        <details className="rounded-sm border border-slate-200 bg-paper p-3">
          <summary className="cursor-pointer text-xs font-medium text-slate-600">
            Factors never suggested as changes ({blueprint.immutable_fields.length})
          </summary>
          <ul className="mt-2 space-y-1 text-[11px] text-slate-500">
            {blueprint.immutable_fields.map((f) => (
              <li key={f.field}>
                <span className="mono text-slate-600">{f.field}</span> — {f.reason}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <p className="text-[11px] text-slate-400">
        {blueprint.disclaimer ??
          "Scenarios are model-generated estimates, not promises, and they do not guarantee an approval."}
      </p>
    </div>
  );
}
