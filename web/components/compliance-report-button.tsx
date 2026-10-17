"use client";

import { FileDown, ShieldCheck } from "lucide-react";
import { reportPdfUrl } from "@/lib/api";
import { Panel, PanelBody, PanelDescription, PanelHeader, PanelTitle } from "@/components/ui/panel";

/**
 * One-click compliance PDF.
 *
 * The report is generated server-side with ReportLab (charts drawn from its own
 * primitives) and streamed straight to the browser, so there is no heavyweight
 * charting dependency in the runtime and no client-side rendering step.
 */
export function ComplianceReportButton() {
  return (
    <Panel>
      <PanelHeader>
        <div>
          <PanelTitle>
            <ShieldCheck className="h-4 w-4 text-brand-400" />
            Compliance report
          </PanelTitle>
          <PanelDescription>
            Compliance Alignment &amp; Fair Lending report, generated on the server.
          </PanelDescription>
        </div>
      </PanelHeader>
      <PanelBody className="space-y-3">
        <p className="text-xs text-slate-400">
          Bundles the model overview, discrimination and calibration metrics with a
          reliability curve, the cost policy, the per-attribute fairness audit, the
          mitigation before/after and the model lineage into a single PDF.
        </p>
        <a
          href={reportPdfUrl()}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-brand-500"
        >
          <FileDown className="h-3.5 w-3.5" />
          Download compliance PDF
        </a>
        <p className="text-[10px] text-slate-500">
          Generated server-side with ReportLab — no matplotlib in the runtime bundle.
        </p>
      </PanelBody>
    </Panel>
  );
}
