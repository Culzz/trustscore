import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { ReasonItem } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ReasonList({ reasons }: { reasons: ReasonItem[] }) {
  if (!reasons.length) {
    return (
      <p className="text-sm text-slate-500">
        No strong factors stood out for this applicant.
      </p>
    );
  }
  return (
    <ul className="space-y-2">
      {reasons.map((reason, i) => {
        const increases = reason.direction === "increases";
        return (
          <li
            key={`${reason.factor}-${i}`}
            className="flex items-start gap-3 rounded-sm border border-slate-200 bg-paper px-3 py-2"
          >
            <span
              className={cn(
                "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-sm",
                increases
                  ? "bg-rose-100 text-rose-700"
                  : "bg-emerald-100 text-emerald-700",
              )}
              aria-hidden
            >
              {increases ? (
                <ArrowUpRight className="h-4 w-4" strokeWidth={1.5} />
              ) : (
                <ArrowDownRight className="h-4 w-4" strokeWidth={1.5} />
              )}
            </span>
            <div className="min-w-0">
              <p className="text-sm text-slate-800">{reason.text}</p>
              <p className="text-[11px] text-slate-500">
                {reason.factor}
                {reason.detail ? ` · ${reason.detail}` : ""}
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
