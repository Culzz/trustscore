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
            "whitespace-nowrap text-[9vw] font-black uppercase leading-none tracking-[0.2em]",
            tone === "dark" ? "text-white/[0.03]" : "text-slate-900/[0.035]",
          )}
          style={{ transform: "rotate(-24deg)" }}
        >
          Simulation environment
        </span>
      </div>
    </div>
  );
}
