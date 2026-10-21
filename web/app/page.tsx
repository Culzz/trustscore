"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  Info,
  Loader2,
  ScanLine,
  Sparkles,
} from "lucide-react";
import { api, ApiError, watchJob } from "@/lib/api";
import { DEFAULT_APPLICANT, SAMPLES, type SampleApplicant } from "@/lib/samples";
import type {
  Applicant,
  ApplicationResult,
  JobEvent,
  MacroContext,
  RegistryModel,
} from "@/lib/types";
import { cn, formatPct } from "@/lib/utils";
import { useMode } from "@/components/mode-provider";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/field";
import { RiskDisclosure } from "@/components/risk-disclosure";
import { ProgressSteps } from "@/components/progress-steps";
import { BlueprintCard } from "@/components/blueprint-card";
import { NoticeCard } from "@/components/notice-card";
import { ReasonList } from "@/components/reason-list";
import { WhatIfSandbox } from "@/components/whatif-sandbox";

export default function ApplicantPage() {
  const { setMode } = useMode();
  const [applicant, setApplicant] = useState<Applicant>(DEFAULT_APPLICANT);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [result, setResult] = useState<ApplicationResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [transport, setTransport] = useState<"websocket" | "polling" | "inline" | null>(null);

  // Policy controls.
  const [model, setModel] = useState<string>("");
  const [models, setModels] = useState<RegistryModel[]>([]);
  const [applyFairness, setApplyFairness] = useState(false);
  const [region, setRegion] = useState("national");
  const [regions, setRegions] = useState<{ id: string; label: string }[]>([]);
  const [context, setContext] = useState<MacroContext | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const stopRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    setMode("applicant");
  }, [setMode]);

  useEffect(() => {
    api
      .models()
      .then((data) => setModels(data.models))
      .catch(() => setModels([]));
  }, []);

  useEffect(() => {
    api
      .context(region)
      .then((data) => {
        setRegions(data.regions);
        setContext(data.context);
      })
      .catch(() => undefined);
  }, [region]);

  useEffect(() => () => stopRef.current?.(), []);

  const set = <K extends keyof Applicant>(key: K, value: Applicant[K]) =>
    setApplicant((a) => ({ ...a, [key]: value }));

  const loadSample = (sample: SampleApplicant) => {
    stopRef.current?.();
    setApplicant(sample.applicant);
    setResult(null);
    setEvents([]);
    setError(null);
    setRunning(false);
  };

  const submit = useCallback(async () => {
    stopRef.current?.();
    setRunning(true);
    setError(null);
    setResult(null);
    setEvents([]);
    try {
      const job = await api.submitApplication(applicant, {
        model: model || null,
        apply_fairness: applyFairness,
        region,
        use_macro_tilt: false,
      });
      // Without a durable job store the API runs the flow inside the request
      // and returns the finished job. Render it directly: polling could land on
      // a different serverless instance that never saw the job.
      if (job.result || job.status === "complete") {
        setEvents(job.events ?? []);
        setResult(job.result ?? null);
        setTransport("inline");
        setRunning(false);
        return;
      }
      if (job.status === "error") {
        setRunning(false);
        setError(job.error ?? "The application could not be scored.");
        return;
      }
      stopRef.current = watchJob(job.job_id, {
        onEvent: (event) =>
          setEvents((prev) => {
            if (prev.some((e) => e.step === event.step && e.at === event.at)) {
              return prev;
            }
            return [...prev, event];
          }),
        onTransport: setTransport,
        onDone: (finished) => {
          setRunning(false);
          if (finished?.result) setResult(finished.result);
        },
        onError: (message) => {
          setRunning(false);
          setError(message);
        },
      });
    } catch (err) {
      setRunning(false);
      setError(err instanceof ApiError ? err.message : "Unexpected error.");
    }
  }, [applicant, model, applyFairness, region]);

  const fairnessNote = result?.scoring.mitigation.applied
    ? `Fairness mitigation moved this decision from ${result.scoring.band} to ${result.scoring.final_band} for the ${result.scoring.mitigation.attribute} group.`
    : result?.scoring.mitigation.requested && result?.scoring.mitigation.method === "none"
      ? "Fairness mitigation was requested but no mitigation parameters are available."
      : result?.scoring.mitigation.requested
        ? "Fairness mitigation was applied; the band is unchanged for this applicant."
        : null;

  return (
    <div className="space-y-6">
      <header className="relative">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-2xl">
            <p className="eyebrow">Consumer credit · demonstration</p>
            <h1 className="mt-3 text-balance font-display text-4xl font-medium leading-[1.02] tracking-tight text-slate-900 sm:text-5xl">
              See the decision,{" "}
              <span className="italic text-brand-700">not just the score.</span>
            </h1>
            <p className="mt-4 max-w-xl text-sm leading-6 text-slate-600">
              Enter an application to get an estimated risk category, the reasons
              in plain language, a simulated decision, and a concrete plan to
              improve it.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="stamp">Calibrated</span>
            <span className="stamp">Fairness-audited</span>
            <span className="stamp">Recourse-ready</span>
          </div>
        </div>
        <div className="mt-8 flex items-center gap-3" aria-hidden="true">
          <span className="h-px flex-1 bg-slate-200" />
          <span className="text-[8px] font-semibold uppercase tracking-[0.24em] text-slate-400">
            Estimate · explain · improve
          </span>
          <span className="h-px flex-1 bg-slate-200" />
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Application details</CardTitle>
            <CardDescription>
              Ten fields. Nothing is stored that identifies a person.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="eyebrow mb-2">Or start from a sample</p>
              <div className="flex flex-wrap gap-2">
                {SAMPLES.map((s, index) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => loadSample(s)}
                    title={s.blurb}
                    className="group inline-flex items-center gap-2 border border-slate-300 bg-paper px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-600 shadow-press transition hover:border-brand-600 hover:text-brand-700"
                  >
                    <span className="mono text-[9px] font-normal text-slate-400 group-hover:text-brand-500">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    {s.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <NumberField
                label="Age"
                value={applicant.person_age}
                onChange={(v) => set("person_age", v)}
                min={18}
                max={100}
              />
              <NumberField
                label="Annual income"
                value={applicant.person_income}
                onChange={(v) => set("person_income", v)}
                min={1000}
                step={1000}
                prefix="$"
              />
              <SelectField
                label="Home ownership"
                value={applicant.person_home_ownership}
                onChange={(v) =>
                  set("person_home_ownership", v as Applicant["person_home_ownership"])
                }
                options={["RENT", "OWN", "MORTGAGE", "OTHER"]}
              />
              <NumberField
                label="Employment length (years)"
                value={applicant.person_emp_length ?? 0}
                onChange={(v) => set("person_emp_length", v)}
                min={0}
                max={60}
                step={0.5}
                allowBlank
                onBlank={() => set("person_emp_length", null)}
              />
              <SelectField
                label="Loan purpose"
                value={applicant.loan_intent}
                onChange={(v) => set("loan_intent", v as Applicant["loan_intent"])}
                options={[
                  "DEBTCONSOLIDATION",
                  "EDUCATION",
                  "HOMEIMPROVEMENT",
                  "MEDICAL",
                  "PERSONAL",
                  "VENTURE",
                ]}
              />
              <SelectField
                label="Loan grade"
                value={applicant.loan_grade}
                onChange={(v) => set("loan_grade", v as Applicant["loan_grade"])}
                options={["A", "B", "C", "D", "E", "F", "G"]}
              />
              <NumberField
                label="Requested amount"
                value={applicant.loan_amnt}
                onChange={(v) => set("loan_amnt", v)}
                min={500}
                max={40000}
                step={500}
                prefix="$"
              />
              <NumberField
                label="Interest rate (%)"
                value={applicant.loan_int_rate ?? 0}
                onChange={(v) => set("loan_int_rate", v)}
                min={0}
                max={40}
                step={0.1}
                allowBlank
                onBlank={() => set("loan_int_rate", null)}
              />
              <SelectField
                label="Prior default on file"
                value={applicant.cb_person_default_on_file}
                onChange={(v) =>
                  set(
                    "cb_person_default_on_file",
                    v as Applicant["cb_person_default_on_file"],
                  )
                }
                options={["N", "Y"]}
                renderOption={(v) => (v === "Y" ? "Yes" : "No")}
              />
              <NumberField
                label="Credit history (years)"
                value={applicant.cb_person_cred_hist_length}
                onChange={(v) => set("cb_person_cred_hist_length", v)}
                min={0}
                max={60}
              />
            </div>

            <div className="space-y-3 border border-slate-200 bg-slate-100/40 p-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <Label>Model version</Label>
                  <Select value={model} onChange={(e) => setModel(e.target.value)}>
                    <option value="">Default (Alpha)</option>
                    {models.map((m) => (
                      <option key={m.version} value={m.version}>
                        {m.label}
                      </option>
                    ))}
                  </Select>
                </div>
                <div>
                  <Label>Macro region (context)</Label>
                  <Select value={region} onChange={(e) => setRegion(e.target.value)}>
                    {(regions.length > 0
                      ? regions
                      : [{ id: "national", label: "National" }]
                    ).map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.label}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>
              <label className="flex items-start gap-2 border-t border-slate-200 pt-3 text-[11px] text-slate-600">
                <input
                  type="checkbox"
                  checked={applyFairness}
                  onChange={(e) => setApplyFairness(e.target.checked)}
                  className="mt-0.5 h-3.5 w-3.5 accent-brand-600"
                />
                <span>
                  Apply fairness mitigation{" "}
                  <span className="text-slate-400">(Beta)</span>
                </span>
              </label>
            </div>

            <Button onClick={submit} disabled={running} className="w-full">
              {running ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowRight className="h-4 w-4" strokeWidth={1.5} />
              )}
              {running ? "Working through the application…" : "Get my estimated risk"}
            </Button>

            {error ? (
              <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Your estimate</CardTitle>
              <CardDescription>
                The category first; the numbers only if you want them.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!result && !running ? (
                <div className="flex h-52 flex-col items-center justify-center border border-dashed border-slate-300 bg-slate-100/30 px-6 text-center">
                  <span className="flex h-11 w-11 items-center justify-center border border-slate-300 bg-paper">
                    <ScanLine
                      className="h-5 w-5 text-slate-400"
                      strokeWidth={1.5}
                    />
                  </span>
                  <p className="mt-4 max-w-[250px] text-xs leading-relaxed text-slate-500">
                    Submit an application to see your estimated category, the
                    reasons, and a recourse plan here.
                  </p>
                </div>
              ) : null}

              {running ? (
                <ProgressSteps events={events} running={running} />
              ) : null}

              {result ? (
                <>
                  <RiskDisclosure
                    band={result.scoring.final_band}
                    probability={result.scoring.probability_of_default}
                    thresholds={result.scoring.thresholds}
                    modelVersion={result.scoring.model_version}
                    group={result.scoring.group}
                  />

                  {fairnessNote ? (
                    <p className="flex items-start gap-1.5 rounded-lg border border-brand-100 bg-brand-50 px-3 py-2 text-[11px] text-brand-900">
                      <Sparkles className="mt-0.5 h-3 w-3 shrink-0" />
                      {fairnessNote}
                    </p>
                  ) : null}

                  {transport ? (
                    <p className="text-[10px] text-slate-400">
                      {transport === "websocket"
                        ? "Milestones streamed over WebSocket."
                        : transport === "polling"
                          ? "Milestones streamed over polling."
                          : "Scored synchronously in this request (no durable job store configured)."}
                    </p>
                  ) : null}

                  {context ? <ContextStrip context={context} /> : null}
                </>
              ) : null}
            </CardContent>
          </Card>

          {result ? (
            <Card>
              <CardHeader>
                <CardTitle>How to get approved</CardTitle>
                <CardDescription>
                  Concrete, independent routes to a better category — dual-target
                  where two paths exist.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <BlueprintCard blueprint={result.blueprint} />
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>

      {result ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Your notice</CardTitle>
              <CardDescription>
                ECOA-style reason codes with a language guardrail applied.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <NoticeCard narrative={result.narrative} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>What-if sandbox</CardTitle>
              <CardDescription>
                Change the amount or purpose on the right and compare against what
                you submitted.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <WhatIfSandbox
                base={applicant}
                options={{
                  model: model || null,
                  applyFairness,
                  mitigationAttribute: result.scoring.mitigation.attribute,
                }}
              />
            </CardContent>
          </Card>

          <Card className="lg:col-span-2">
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Why this estimate (technical detail)</CardTitle>
                <CardDescription>
                  The model contributions behind the notice, for transparency.
                </CardDescription>
              </div>
              <button
                type="button"
                onClick={() => setDetailOpen((v) => !v)}
                className="inline-flex items-center gap-1.5 rounded-sm border border-slate-300 bg-paper px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-600 transition hover:border-slate-900 hover:text-slate-900"
                aria-expanded={detailOpen}
              >
                {detailOpen ? "Hide" : "Show"}
                <ChevronDown
                  className={cn("h-3.5 w-3.5 transition", detailOpen && "rotate-180")}
                />
              </button>
            </CardHeader>
            {detailOpen ? (
              <CardContent>
                <ReasonList reasons={result.reasons} />
                <p className="mt-3 flex items-start gap-1.5 text-[11px] text-slate-400">
                  <Info className="mt-0.5 h-3 w-3 shrink-0" />
                  Contributions describe how the model reached its estimate. They are
                  not the same as adverse-action reason codes, which is why the
                  notice above uses its own reviewed wording.
                </p>
              </CardContent>
            ) : null}
          </Card>
        </div>
      ) : null}
    </div>
  );
}

function ContextStrip({ context }: { context: MacroContext }) {
  return (
    <div className="grid grid-cols-2 gap-3 border border-slate-200 bg-slate-100/40 p-3 text-[11px] sm:grid-cols-4">
      <div>
        <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          Prime rate
        </p>
        <p className="mono mt-1 font-medium text-slate-900">{context.prime_rate}%</p>
      </div>
      <div>
        <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          Unemployment
        </p>
        <p className="mono mt-1 font-medium text-slate-900">
          {context.unemployment_rate}%
        </p>
      </div>
      <div>
        <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          CPI (YoY)
        </p>
        <p className="mono mt-1 font-medium text-slate-900">{context.cpi_yoy}%</p>
      </div>
      <div>
        <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          Cycle tilt
        </p>
        <p className="mono mt-1 font-medium text-slate-900">
          {formatPct(context.cycle_tilt, 0)}
        </p>
      </div>
      <p className="col-span-2 border-t border-slate-200 pt-2 text-[9px] text-slate-400 sm:col-span-4">
        {context.region_label} · {context.note}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ fields */

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  prefix,
  allowBlank = false,
  onBlank,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  prefix?: string;
  allowBlank?: boolean;
  onBlank?: () => void;
}) {
  const [blank, setBlank] = useState(false);
  return (
    <div>
      <Label>
        {label}
        {allowBlank ? (
          <span className="ml-1 font-normal normal-case tracking-normal text-slate-400">
            {" "}(optional)
          </span>
        ) : null}
      </Label>
      <div className="relative">
        {prefix ? (
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-400">
            {prefix}
          </span>
        ) : null}
        <Input
          type="number"
          value={blank ? "" : value}
          min={min}
          max={max}
          step={step}
          className={prefix ? "pl-7" : undefined}
          onChange={(e) => {
            if (e.target.value === "" && allowBlank) {
              setBlank(true);
              onBlank?.();
              return;
            }
            setBlank(false);
            const n = Number(e.target.value);
            if (!Number.isNaN(n)) onChange(n);
          }}
        />
      </div>
    </div>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
  renderOption,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  renderOption?: (v: string) => string;
}) {
  return (
    <div>
      <Label>{label}</Label>
      <Select value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o} value={o}>
            {renderOption ? renderOption(o) : o.charAt(0) + o.slice(1).toLowerCase()}
          </option>
        ))}
      </Select>
    </div>
  );
}
