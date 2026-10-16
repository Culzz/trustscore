import { BAND_STYLES, cn } from "@/lib/utils";
import type { Band } from "@/lib/types";

export function RiskGauge({
  probability,
  band,
  label,
}: {
  probability: number;
  band: Band;
  label: string;
}) {
  const pct = Math.max(0, Math.min(1, probability));
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const dash = circumference * pct;
  const color = BAND_STYLES[band].ring.replace("stroke-", "text-");

  return (
    <div className="flex flex-col items-center">
      <div className="relative h-36 w-36">
        <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90">
          <circle
            cx="70"
            cy="70"
            r={radius}
            className="fill-none stroke-slate-200"
            strokeWidth="12"
          />
          <circle
            cx="70"
            cy="70"
            r={radius}
            className={cn("fill-none", color)}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference - dash}`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-semibold tabular-nums text-slate-900">
            {(pct * 100).toFixed(1)}%
          </span>
          <span className="text-[11px] uppercase tracking-wide text-slate-500">
            est. risk
          </span>
        </div>
      </div>
      <span className={cn("mt-3 text-sm font-semibold", BAND_STYLES[band].text)}>
        {label}
      </span>
    </div>
  );
}
