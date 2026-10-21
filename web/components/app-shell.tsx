"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ArrowUpRight,
  FileText,
  Gauge,
  TriangleAlert,
  UserRound,
} from "lucide-react";
import { API_BASE } from "@/lib/api";
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
        dark ? "bg-slate-950 text-slate-100" : "bg-transparent text-slate-900",
      )}
    >
      <SimulationWatermark tone={dark ? "dark" : "light"} />

      <header
        className={cn(
          "sticky top-0 z-30 border-b backdrop-blur-md",
          dark
            ? "border-slate-800 bg-slate-950/85"
            : "border-slate-200 bg-slate-50/85",
        )}
      >
        <div className="container-page flex h-[72px] items-center justify-between gap-4">
          <Link
            href={dark ? "/auditor" : "/"}
            className="group flex items-center gap-3"
            aria-label="TrustScore home"
          >
            <span
              className={cn(
                "relative flex h-10 w-10 items-center justify-center border",
                dark
                  ? "border-slate-700 bg-slate-900 text-slate-50"
                  : "border-slate-900 bg-slate-900 text-slate-50",
              )}
            >
              <span className="font-display text-xl leading-none">T</span>
              <span className="absolute -right-1 -top-1 h-2 w-2 bg-brand-600" />
            </span>
            <span className="flex flex-col leading-none">
              <span
                className={cn(
                  "font-display text-[22px] font-medium tracking-tight",
                  dark ? "text-slate-50" : "text-slate-900",
                )}
              >
                TrustScore
              </span>
              <span className="mt-1 text-[9px] font-semibold uppercase tracking-[0.22em] text-slate-500">
                {dark ? "Audit & governance" : "Credit decisioning, explained"}
              </span>
            </span>
          </Link>

          <div className="flex items-center gap-4">
            <nav className="hidden items-center gap-6 sm:flex" aria-label="Primary">
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
                      "group relative flex h-[72px] items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] transition",
                      active
                        ? dark
                          ? "text-slate-50"
                          : "text-slate-900"
                        : dark
                          ? "text-slate-500 hover:text-slate-300"
                          : "text-slate-500 hover:text-slate-900",
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" strokeWidth={1.5} />
                    {item.label}
                    <span
                      className={cn(
                        "absolute inset-x-0 bottom-0 h-[2px] transition",
                        active
                          ? "bg-brand-600"
                          : "bg-transparent group-hover:bg-slate-300",
                      )}
                    />
                  </Link>
                );
              })}
            </nav>

            <div
              className={cn(
                "flex items-center border p-0.5",
                dark
                  ? "border-slate-700 bg-slate-900"
                  : "border-slate-300 bg-slate-100/70",
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
                    "px-3 py-1.5 text-[9px] font-semibold uppercase tracking-[0.14em] transition",
                    mode === option
                      ? dark
                        ? "bg-slate-100 text-slate-950"
                        : "bg-slate-900 text-slate-50"
                      : dark
                        ? "text-slate-500 hover:text-slate-200"
                        : "text-slate-500 hover:text-slate-800",
                  )}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Mobile: the primary nav becomes a ledger tab strip. */}
        <div
          className={cn(
            "border-t sm:hidden",
            dark ? "border-slate-800" : "border-slate-200",
          )}
        >
          <nav className="container-page flex" aria-label="Primary mobile">
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
                    "flex flex-1 items-center justify-center gap-1.5 border-b-2 py-3 text-[9px] font-semibold uppercase tracking-[0.14em] transition",
                    active
                      ? dark
                        ? "border-brand-600 text-slate-50"
                        : "border-brand-600 text-slate-900"
                      : dark
                        ? "border-transparent text-slate-500"
                        : "border-transparent text-slate-500",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" strokeWidth={1.5} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      </header>

      <div
        className={cn(
          "relative z-10 border-b",
          dark
            ? "border-amber-900/40 bg-amber-950/30 text-amber-200"
            : "border-amber-300/70 bg-amber-50 text-amber-950",
        )}
      >
        <div className="container-page flex items-start gap-2.5 py-2.5 text-[10px] leading-relaxed">
          <TriangleAlert
            className="mt-0.5 h-3.5 w-3.5 shrink-0"
            strokeWidth={1.5}
          />
          <p className="tracking-wide">
            <span className="font-bold uppercase tracking-[0.18em]">
              Simulation environment.
            </span>{" "}
            TrustScore is a demonstration of responsible-AI credit decisioning.
            Every score, decision and policy here is simulated. It is not a loan
            offer, not financial advice, and not a real credit decision.
          </p>
        </div>
      </div>

      <main className="container-page relative z-10 flex-1 py-8 sm:py-12">
        {children}
      </main>

      <footer
        className={cn(
          "relative z-10 border-t",
          dark
            ? "border-slate-800 bg-slate-950/80"
            : "border-slate-200 bg-slate-100/40",
        )}
      >
        <div className="container-page py-8">
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            <div className="lg:col-span-2">
              <div className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 bg-brand-600" />
                <span
                  className={cn(
                    "font-display text-lg",
                    dark ? "text-slate-100" : "text-slate-900",
                  )}
                >
                  TrustScore
                </span>
              </div>
              <p className="mt-2 max-w-sm text-xs leading-relaxed text-slate-500">
                An explainable, fairness-aware credit decision simulation. Built
                as a portfolio-grade demonstration of responsible AI — not a
                lending product.
              </p>
              <p className="mt-3 text-[10px] uppercase tracking-[0.16em] text-slate-400">
                Model{" "}
                <span className="mono normal-case tracking-normal">
                  trustscore-1.0.0
                </span>{" "}
                · Fair{" "}
                <span className="mono normal-case tracking-normal">
                  1.1.0
                </span>
              </p>
            </div>

            <div>
              <p className="eyebrow">Explore</p>
              <div className="mt-3 space-y-2 text-xs">
                <FooterLink href="/" dark={dark}>
                  Applicant view
                </FooterLink>
                <FooterLink href="/auditor" dark={dark}>
                  Auditor console
                </FooterLink>
                <FooterLink href="/model-card" dark={dark}>
                  Model card
                </FooterLink>
              </div>
            </div>

            <div>
              <p className="eyebrow">Project</p>
              <div className="mt-3 space-y-2 text-xs">
                <ExternalLink href="https://trustscore-sigma.vercel.app" dark={dark}>
                  Live demo
                </ExternalLink>
                <ExternalLink
                  href="https://github.com/Culzz/trustscore"
                  dark={dark}
                >
                  Source code
                </ExternalLink>
                <ExternalLink href={`${API_BASE}/report.pdf`} dark={dark}>
                  Evaluation report
                </ExternalLink>
              </div>
            </div>
          </div>

          <div
            className={cn(
              "mt-8 flex flex-col gap-2 border-t pt-4 text-[9px] uppercase tracking-[0.14em] sm:flex-row sm:items-center sm:justify-between",
              dark ? "border-slate-800 text-slate-500" : "border-slate-200 text-slate-400",
            )}
          >
            <p>Simulation only · not a loan offer · not financial advice</p>
            <p>
              © 2026 · Built by{" "}
              <a
                href="https://github.com/Culzz"
                className="link-editorial text-slate-500"
                target="_blank"
                rel="noreferrer"
              >
                Culzz
              </a>
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}

function FooterLink({
  href,
  dark,
  children,
}: {
  href: string;
  dark: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "block w-fit transition",
        dark
          ? "text-slate-400 hover:text-slate-100"
          : "text-slate-600 hover:text-slate-900",
      )}
    >
      {children}
    </Link>
  );
}

function ExternalLink({
  href,
  dark,
  children,
}: {
  href: string;
  dark: boolean;
  children: React.ReactNode;
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={cn(
        "group flex w-fit items-center gap-1 transition",
        dark
          ? "text-slate-400 hover:text-slate-100"
          : "text-slate-600 hover:text-slate-900",
      )}
    >
      {children}
      <ArrowUpRight
        className="h-3 w-3 opacity-50 transition group-hover:opacity-100"
        strokeWidth={1.5}
      />
    </a>
  );
}
