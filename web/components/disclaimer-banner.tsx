import { Info } from "lucide-react";

export function DisclaimerBanner() {
  return (
    <div className="border-b border-amber-200 bg-amber-50">
      <div className="container-page flex items-center gap-2 py-2 text-xs text-amber-900">
        <Info className="h-4 w-4 shrink-0" />
        <p>
          Demonstration only. Decisions are <strong>simulated</strong> and are
          not a loan offer, approval, or financial advice.
        </p>
      </div>
    </div>
  );
}
