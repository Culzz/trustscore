import type { Metadata } from "next";
import "./globals.css";
import { SiteHeader } from "@/components/site-header";
import { DisclaimerBanner } from "@/components/disclaimer-banner";

export const metadata: Metadata = {
  title: "TrustScore — Explainable Credit Decisioning",
  description:
    "An explainable, fairness-aware credit decision simulation. Demo only — not a loan offer.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <SiteHeader />
        <DisclaimerBanner />
        <main className="container-page py-8">{children}</main>
        <footer className="border-t border-slate-200 bg-white">
          <div className="container-page flex flex-col gap-2 py-6 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
            <p>
              TrustScore is a demonstration of responsible-AI credit decisioning.
              It is not a real lending tool and not financial advice.
            </p>
            <p>
              Trained on public data (Kaggle Credit Risk Dataset). Decisions are
              simulated.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
