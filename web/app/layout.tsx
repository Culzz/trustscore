import type { Metadata } from "next";
import "@fontsource-variable/newsreader";
import "@fontsource-variable/newsreader/wght-italic.css";
import "@fontsource-variable/public-sans";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-mono/latin-600.css";
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
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          // Set the material before first paint so a reload never flashes the
          // wrong theme. The route decides: the auditor is a dark surface.
          dangerouslySetInnerHTML={{
            __html:
              "try{document.documentElement.dataset.mode=location.pathname.indexOf('/auditor')===0?'auditor':'applicant'}catch(e){}",
          }}
        />
      </head>
      <body>
        <ModeProvider>
          <AppShell>{children}</AppShell>
        </ModeProvider>
      </body>
    </html>
  );
}
