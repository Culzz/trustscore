"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  FileText,
  Gauge,
  ShieldCheck,
  TriangleAlert,
  UserRound,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useMode, type PersonaMode } from "./mode-provider";
import { SimulationWatermark } from "./simulation-watermark";

const NAV = [
  { href: "/", label: "Applicant", mode: "applicant" as PersonaMode, icon: UserRound },
  { href: "/auditor", label: "Auditor", mode: "auditor" as PersonaMode, icon: Gauge },
  { href: "/model-card", label: "Model card", mode: null, icon: FileText },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { mode, setMode } = useMode();
  const pathname = usePathname();
  const router = useRouter();
  const dark = mode === "auditor";

  const chooseMode = (next: PersonaMode) => {
    setMode(next);
    router.push(next === "auditor" ? "/auditor" : "/");
  };

  return (
    <div
      className={cn(
        "relative flex min-h-screen flex-col",
        dark ? "bg-slate-950 text-slate-100" : "bg-slate-50 text-slate-900",
      )}
    >
      <SimulationWatermark tone={dark ? "dark" : "light"} />

      <header
        className={cn(
          "sticky top-0 z-30 border-b backdrop-blur",
          dark
            ? "border-slate-800 bg-slate-950/85"
            : "border-slate-200 bg-white/90",
        )}
      >
        <div className="container-page flex h-16 items-center justify-between gap-3">
          <Link href={dark ? "/auditor" : "/"} className="flex items-center gap-2">
            <span
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg text-white",
                dark ? "bg-slate-700" : "bg-brand-600",
              )}
            >
              <ShieldCheck className="h-5 w-5" />
            </span>
            <span className="flex flex-col leading-tight">
              <span className={cn("text-base font-semibold", dark && "text-white")}>
                TrustScore
              </span>
              <span
                className={cn(
                  "text-[11px]",
                  dark ? "text-slate-400" : "text-slate-500",
                )}
              >
                {dark ? "Audit & governance console" : "Explainable credit decisioning"}
              </span>
            </span>
          </Link>

          <div className="flex items-center gap-2">
            <nav className="hidden items-center gap-1 sm:flex">
              {NAV.map((item) => {
                const active =
                  item.href === "/"
                    ? pathname === "/"
                    : pathname?.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition",
                      dark
                        ? active
                          ? "bg-slate-800 text-white"
                          : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
                        : active
                          ? "bg-brand-50 text-brand-700"
                          : "text-slate-600 hover:bg-slate-100",
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {item.label}
                  </Link>
                );
              })}
            </nav>

            <div
              className={cn(
                "flex items-center rounded-lg border p-0.5",
                dark ? "border-slate-700 bg-slate-900" : "border-slate-200 bg-slate-100",
              )}
              role="group"
              aria-label="Persona"
            >
              {(["applicant", "auditor"] as PersonaMode[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => chooseMode(option)}
                  aria-pressed={mode === option}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-[11px] font-semibold capitalize transition",
                    mode === option
                      ? dark
                        ? "bg-slate-700 text-white"
                        : "bg-white text-slate-900 shadow-sm"
                      : dark
                        ? "text-slate-400 hover:text-slate-200"
                        : "text-slate-500 hover:text-slate-700",
                  )}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <div
        className={cn(
          "relative z-10 border-b",
          dark
            ? "border-amber-900/40 bg-amber-950/40 text-amber-200"
            : "border-amber-200 bg-amber-50 text-amber-900",
        )}
      >
        <div className="container-page flex items-start gap-2 py-2 text-[11px]">
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <p>
            <span className="font-semibold">SIMULATION ENVIRONMENT.</span>{" "}
            TrustScore is a demonstration of responsible-AI credit decisioning.
            Every score, decision and policy here is simulated. It is not a loan
            offer, not financial advice, and not a real credit decision.
          </p>
        </div>
      </div>

      <main className="container-page relative z-10 flex-1 py-8">{children}</main>

      <footer
        className={cn(
          "relative z-10 border-t",
          dark ? "border-slate-800 bg-slate-950" : "border-slate-200 bg-white",
        )}
      >
        <div
          className={cn(
            "container-page flex flex-col gap-2 py-6 text-xs sm:flex-row sm:items-center sm:justify-between",
            dark ? "text-slate-500" : "text-slate-500",
          )}
        >
          <p>
            TrustScore is a demonstration of responsible-AI credit decisioning. It
            is not a real lending tool and not financial advice.
          </p>
          <p>
            Model <span className="font-mono">trustscore-1.0.0</span> · fairness-
            tuned <span className="font-mono">trustscore-1.1.0</span>
          </p>
        </div>
      </footer>
    </div>
  );
}
