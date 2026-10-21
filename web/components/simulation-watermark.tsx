import { cn } from "@/lib/utils";

/**
 * The persistent "SIMULATION ENVIRONMENT" watermark.
 *
 * Pinned to the viewport and repeated so it cannot be scrolled away or cropped
 * out of a screenshot: every screen in the platform is visibly a demo.
 */
export function SimulationWatermark({ tone = "light" }: { tone?: "light" | "dark" }) {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0 select-none overflow-hidden"
    >
      <div className="flex h-full w-full items-center justify-center">
        <span
          className={cn(
            "whitespace-nowrap font-display text-[8.5vw] font-medium uppercase italic leading-none tracking-[0.28em]",
            tone === "dark" ? "text-slate-100/[0.035]" : "text-slate-900/[0.04]",
          )}
          style={{ transform: "rotate(-24deg)" }}
        >
          Simulation environment
        </span>
      </div>
    </div>
  );
}
