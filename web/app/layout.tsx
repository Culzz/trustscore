import type { Metadata } from "next";
import "./globals.css";
import { ModeProvider } from "@/components/mode-provider";
import { AppShell } from "@/components/app-shell";

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
      <body>
        <ModeProvider>
          <AppShell>{children}</AppShell>
        </ModeProvider>
      </body>
    </html>
  );
}
