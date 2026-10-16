import { cn, BAND_STYLES } from "@/lib/utils";
import type { Band } from "@/lib/types";

export function Badge({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        "border-slate-200 bg-slate-100 text-slate-700",
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
        "inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold",
        BAND_STYLES[band].chip,
      )}
    >
      {label}
    </span>
  );
}
