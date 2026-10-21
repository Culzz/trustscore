import { cn } from "@/lib/utils";

/** Dark-surface primitives for the auditor terminal. */

export function Panel({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "relative rounded-sm border border-slate-800 bg-slate-900/55 shadow-[3px_3px_0_0_rgba(0,0,0,0.28)]",
        className,
      )}
      {...props}
    />
  );
}

export function PanelHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 border-b border-slate-800 px-4 py-3",
        className,
      )}
      {...props}
    />
  );
}

export function PanelTitle({
  className,
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn(
        "flex items-center gap-2 font-display text-base font-medium tracking-tight text-slate-100",
        "before:h-px before:w-3 before:shrink-0 before:bg-amber-500 before:content-['']",
        className,
      )}
      {...props}
    />
  );
}

export function PanelDescription({
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("mt-0.5 text-[10px] leading-relaxed text-slate-500", className)}
      {...props}
    />
  );
}

export function PanelBody({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-4 py-4", className)} {...props} />;
}

export function Stat({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const toneClass =
    tone === "good"
      ? "text-emerald-400"
      : tone === "warn"
        ? "text-amber-400"
        : tone === "bad"
          ? "text-rose-400"
          : "text-slate-100";
  return (
    <div className="relative rounded-sm border border-slate-800 bg-slate-950/50 px-3 py-2.5">
      <span className="absolute left-0 top-0 h-px w-6 bg-slate-600" aria-hidden="true" />
      <p className="text-[9px] font-semibold uppercase tracking-[0.16em] text-slate-500">
        {label}
      </p>
      <p className={cn("mono mt-1.5 text-lg font-medium leading-none", toneClass)}>
        {value}
      </p>
      {hint ? <p className="mt-1 text-[9px] leading-snug text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function DarkBadge({
  children,
  tone = "default",
  className,
}: {
  children: React.ReactNode;
  tone?: "default" | "good" | "warn" | "bad" | "info";
  className?: string;
}) {
  const tones: Record<string, string> = {
    default: "border-slate-700 bg-slate-800 text-slate-300",
    good: "border-emerald-800 bg-emerald-950 text-emerald-300",
    warn: "border-amber-800 bg-amber-950 text-amber-300",
    bad: "border-rose-800 bg-rose-950 text-rose-300",
    info: "border-sky-800 bg-sky-950 text-sky-300",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.16em]",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export const darkInputClass =
  "h-9 w-full rounded-sm border border-slate-700 bg-slate-950 px-3 text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-brand-500 focus:ring-2 focus:ring-brand-900/40";

export function DarkLabel({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "mb-1 block text-[9px] font-semibold uppercase tracking-[0.16em] text-slate-400",
        className,
      )}
      {...props}
    />
  );
}
