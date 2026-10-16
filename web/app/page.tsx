"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, Wand2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { DEFAULT_APPLICANT, SAMPLES, type SampleApplicant } from "@/lib/samples";
import type {
  Applicant,
  CounterfactualResponse,
  DecisionResponse,
  ExplainResponse,
  PredictResponse,
} from "@/lib/types";
import { BAND_LABEL_TEXT, cn, formatMoney, formatPct } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/field";
import { BandBadge } from "@/components/ui/badge";
import { RiskGauge } from "@/components/risk-gauge";
import { ReasonList } from "@/components/reason-list";

interface Results {
  predict: PredictResponse;
  explain: ExplainResponse;
  decision: DecisionResponse;
  counterfactual: CounterfactualResponse;
}

export default function ApplicantPage() {
  const [applicant, setApplicant] = useState<Applicant>(DEFAULT_APPLICANT);
  const [results, setResults] = useState<Results | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // What-if: a lightweight live re-score when the requested amount changes.
  const [whatIfAmount, setWhatIfAmount] = useState<number>(DEFAULT_APPLICANT.loan_amnt);
  const [whatIfBand, setWhatIfBand] = useState<PredictResponse | null>(null);

  const set = <K extends keyof Applicant>(key: K, value: Applicant[K]) =>
    setApplicant((a) => ({ ...a, [key]: value }));

  const loadSample = (sample: SampleApplicant) => {
    setApplicant(sample.applicant);
    setWhatIfAmount(sample.applicant.loan_amnt);
    setResults(null);
    setWhatIfBand(null);
    setError(null);
  };

  const submit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [predict, explain, decision, counterfactual] = await Promise.all([
        api.predict(applicant),
        api.explain(applicant),
        api.decision(applicant),
        api.counterfactual(applicant),
      ]);
      setResults({ predict, explain, decision, counterfactual });
      setWhatIfAmount(applicant.loan_amnt);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unexpected error.");
      setResults(null);
    } finally {
      setLoading(false);
    }
  }, [applicant]);

  // Debounced what-if scoring.
  useEffect(() => {
    if (!results) return;
    if (whatIfAmount === applicant.loan_amnt) {
      setWhatIfBand(null);
      return;
    }
    const handle = setTimeout(() => {
      api
        .predict({ ...applicant, loan_amnt: whatIfAmount })
        .then(setWhatIfBand)
        .catch(() => setWhatIfBand(null));
    }, 350);
    return () => clearTimeout(handle);
  }, [whatIfAmount, applicant, results]);

  const active = whatIfBand ?? results?.predict ?? null;
  const topReasons = results?.explain.reasons ?? [];
  const scenarios = results?.counterfactual.scenarios ?? [];

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-slate-900">Applicant view</h1>
        <p className="text-sm text-slate-600">
          Enter an application, or start from an example, and see an estimated
          risk, plain-language reasons, a simulated decision and feasible
          alternatives.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ---------------------------------------------------------- form */}
        <Card>
          <CardHeader>
            <CardTitle>Application details</CardTitle>
            <CardDescription>
              Eleven fields. Nothing is stored that identifies a person.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {SAMPLES.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => loadSample(s)}
                  title={s.blurb}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600 transition hover:border-brand-300 hover:text-brand-700"
                >
                  {s.name}
                </button>
              ))}
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
                onChange={(v) => set("person_home_ownership", v as Applicant["person_home_ownership"])}
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
                  set("cb_person_default_on_file", v as Applicant["cb_person_default_on_file"])
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

            <Button onClick={submit} disabled={loading} className="w-full">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
              {loading ? "Scoring…" : "Get estimated risk"}
            </Button>

            {error ? (
              <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error}</span>
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* ------------------------------------------------------- results */}
        <Card>
          <CardHeader>
            <CardTitle>Result</CardTitle>
            <CardDescription>
              Estimated risk and a simulated decision — not an offer.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {!active ? (
              <div className="flex h-64 flex-col items-center justify-center text-center text-sm text-slate-500">
                <RefreshCw className="mb-3 h-6 w-6 text-slate-300" />
                Score an application to see the result here.
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between gap-4">
                  <RiskGauge
                    probability={active.probability_of_default}
                    band={active.band}
                    label={BAND_LABEL_TEXT[active.band_label]}
                  />
                  <div className="flex-1 space-y-3">
                    <div>
                      <p className="text-xs uppercase tracking-wide text-slate-500">
                        Simulated decision
                      </p>
                      <div className="mt-1 flex items-center gap-2">
                        <BandBadge
                          band={active.band}
                          label={
                            results ? results.decision.decision.toUpperCase() : active.band.toUpperCase()
                          }
                        />
                        <span className="text-xs text-slate-500">labelled simulated</span>
                      </div>
                    </div>
                    <p className="text-xs text-slate-500">
                      Approve ≤ {formatPct(active.thresholds.approve_max_pd, 0)} · Decline ≥{" "}
                      {formatPct(active.thresholds.decline_min_pd, 0)}
                    </p>
                    <p className="text-[11px] text-slate-400">
                      Model {active.model_version}
                    </p>
                  </div>
                </div>

                {whatIfBand ? (
                  <p className="rounded-lg bg-brand-50 px-3 py-2 text-xs text-brand-800">
                    What-if: at {formatMoney(whatIfAmount)} the estimated risk becomes{" "}
                    {formatPct(whatIfBand.probability_of_default)} ({BAND_LABEL_TEXT[whatIfBand.band_label]}).
                  </p>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ------------------------------------------------------- reasons + CF */}
      {results ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Why this estimate</CardTitle>
              <CardDescription>Key factors, in plain language.</CardDescription>
            </CardHeader>
            <CardContent>
              <ReasonList reasons={topReasons} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>What could change</CardTitle>
              <CardDescription>
                Feasible changes only. Protected attributes are never suggested.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {scenarios.length === 0 ? (
                <p className="text-sm text-slate-500">
                  This applicant is already in the best band — nothing to suggest.
                </p>
              ) : (
                <ul className="space-y-2">
                  {scenarios.map((s, i) => (
                    <li
                      key={i}
                      className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
                    >
                      <p className="text-sm text-slate-800">{s.description}</p>
                      <p className="mt-1 text-[11px] text-slate-500">
                        New estimated risk {formatPct(s.new_pd)} ·{" "}
                        <span className="capitalize">{s.changeability.replaceAll("_", " ")}</span>
                      </p>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-[11px] text-slate-400">
                Counterfactuals are model-generated scenarios, not guaranteed
                approval conditions.
              </p>
            </CardContent>
          </Card>

          {/* ------------------------------------------------ what-if slider */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>What-if: adjust the requested amount</CardTitle>
              <CardDescription>
                Move the amount and watch the estimated risk update live.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min={500}
                  max={40000}
                  step={500}
                  value={whatIfAmount}
                  onChange={(e) => setWhatIfAmount(Number(e.target.value))}
                  className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-brand-600"
                />
                <span className="w-24 shrink-0 text-right text-sm font-medium tabular-nums text-slate-800">
                  {formatMoney(whatIfAmount)}
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <span>Current estimate</span>
                <span className="font-medium text-slate-700">
                  {formatPct(
                    (whatIfBand ?? results.predict).probability_of_default,
                  )}
                </span>
                <span>·</span>
                <span className="capitalize">
                  {BAND_LABEL_TEXT[(whatIfBand ?? results.predict).band_label]}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : null}
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
      <Label>{label}</Label>
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
      {allowBlank ? (
        <p className="mt-1 text-[10px] text-slate-400">Leave blank if not reported.</p>
      ) : null}
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
