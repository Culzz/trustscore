import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary:
    "border border-slate-900 bg-slate-900 text-slate-50 hover:border-brand-700 hover:bg-brand-700 focus-visible:outline-brand-600 disabled:border-slate-300 disabled:bg-slate-300 disabled:text-slate-500",
  secondary:
    "border border-slate-300 bg-paper text-slate-800 shadow-press hover:border-slate-900 hover:bg-slate-100 focus-visible:outline-slate-500",
  ghost:
    "border border-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-slate-400",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-[10px] tracking-[0.12em]",
  md: "h-11 px-5 text-[11px] tracking-[0.1em]",
};

export function Button({
  className,
  variant = "primary",
  size = "md",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-sm font-semibold uppercase transition-all duration-150 ease-editorial",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2",
        "active:translate-y-px active:shadow-none",
        "disabled:cursor-not-allowed disabled:opacity-60",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    />
  );
}
