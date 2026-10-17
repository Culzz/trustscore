"use client";

import { CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";
import type { JobEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

const ORDER = ["validated", "scored", "explained", "recourse", "complete"] as const;

const LABELS: Record<string, string> = {
  validated: "Application validated",
  scored: "Risk estimate computed",
  explained: "Reasons and notice prepared",
  recourse: "Recourse plan ready",
  complete: "Decision ready",
};

/**
 * Streaming milestone list for the asynchronous apply flow.
 *
 * Shows the pipeline states (validated → scored → explained → recourse →
 * complete) as they arrive over the WebSocket, or from polling when sockets are
 * unavailable. The skeleton rows make the wait feel like progress, not a hang.
 */
export function ProgressSteps({
  events,
  running,
}: {
  events: JobEvent[];
  running: boolean;
}) {
  const byStep = new Map<string, JobEvent>();
  for (const event of events) {
    if (!byStep.has(event.step)) byStep.set(event.step, event);
  }
  const failure = events.find((e) => e.step === "error");
  const done = byStep.has("complete");

  return (
    <ol className="space-y-2.5" aria-live="polite">
      {ORDER.map((step, index) => {
        const event = byStep.get(step);
        const previousDone =
          index === 0 || ORDER.slice(0, index).some((s) => byStep.has(s));
        const isActive = running && !event && previousDone && !done && !failure;
        const state: "done" | "active" | "pending" | "cached" | "error" = failure
          ? step === "complete"
            ? "pending"
            : event
              ? "done"
              : "pending"
          : event
            ? event.status === "cached"
              ? "cached"
              : "done"
            : isActive
              ? "active"
              : "pending";

        return (
          <li key={step} className="flex items-start gap-3">
            <span className="mt-0.5">
              {state === "done" ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              ) : state === "active" ? (
                <Loader2 className="h-4 w-4 animate-spin text-brand-500" />
              ) : state === "cached" ? (
                <CheckCircle2 className="h-4 w-4 text-sky-500" />
              ) : (
                <CircleDashed className="h-4 w-4 text-slate-300" />
              )}
            </span>
            <div className="flex-1">
              <p
                className={cn(
                  "text-sm",
                  state === "pending" ? "text-slate-400" : "text-slate-800",
                )}
              >
                {event?.label ?? LABELS[step]}
                {state === "cached" ? (
                  <span className="ml-2 rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-medium text-sky-700">
                    cached
                  </span>
                ) : null}
              </p>
              {step === "scored" && event?.probability_of_default !== undefined ? (
                <p className="mono mt-0.5 text-[11px] text-slate-500">
                  PD {(event.probability_of_default * 100).toFixed(2)}% · band{" "}
                  {event.band}
                </p>
              ) : null}
            </div>
          </li>
        );
      })}

      {failure ? (
        <li className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-500" />
          <p className="text-xs text-rose-800">
            {failure.error ?? "The application job failed."}
          </p>
        </li>
      ) : null}
    </ol>
  );
}
