import { cn, BAND_STYLES } from "@/lib/utils";
import type { Band } from "@/lib/types";

export function Badge({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em]",
        "border-slate-300 bg-slate-100 text-slate-600",
        className,
      )}
      {...props}
    />
  );
}

export function BandBadge({ band, label }: { band: Band; label: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-sm border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em]",
        BAND_STYLES[band].chip,
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {label}
    </span>
  );
}
