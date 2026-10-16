import type { Applicant } from "./types";

// Pre-filled example applicants so a visitor can try the flow in one click.
// Values are plausible combinations, not real people.
export interface SampleApplicant {
  id: string;
  name: string;
  blurb: string;
  applicant: Applicant;
}

export const SAMPLES: SampleApplicant[] = [
  {
    id: "strong",
    name: "Established borrower",
    blurb: "Stable job, mortgage, long credit history.",
    applicant: {
      person_age: 38,
      person_income: 78000,
      person_home_ownership: "MORTGAGE",
      person_emp_length: 9,
      loan_intent: "PERSONAL",
      loan_grade: "A",
      loan_amnt: 8000,
      loan_int_rate: 7.5,
      cb_person_default_on_file: "N",
      cb_person_cred_hist_length: 14,
    },
  },
  {
    id: "thin",
    name: "Thin credit file",
    blurb: "Young renter, short history, education loan.",
    applicant: {
      person_age: 23,
      person_income: 33000,
      person_home_ownership: "RENT",
      person_emp_length: 1,
      loan_intent: "EDUCATION",
      loan_grade: "B",
      loan_amnt: 6000,
      loan_int_rate: 11.0,
      cb_person_default_on_file: "N",
      cb_person_cred_hist_length: 2,
    },
  },
  {
    id: "stretched",
    name: "Stretched applicant",
    blurb: "Large amount versus income, prior default on file.",
    applicant: {
      person_age: 25,
      person_income: 24000,
      person_home_ownership: "RENT",
      person_emp_length: 0,
      loan_intent: "VENTURE",
      loan_grade: "D",
      loan_amnt: 15000,
      loan_int_rate: 17.5,
      cb_person_default_on_file: "Y",
      cb_person_cred_hist_length: 3,
    },
  },
  {
    id: "mid",
    name: "Mid-market consolidator",
    blurb: "Older homeowner consolidating debt.",
    applicant: {
      person_age: 47,
      person_income: 56000,
      person_home_ownership: "OWN",
      person_emp_length: 16,
      loan_intent: "DEBTCONSOLIDATION",
      loan_grade: "C",
      loan_amnt: 12000,
      loan_int_rate: 13.5,
      cb_person_default_on_file: "N",
      cb_person_cred_hist_length: 20,
    },
  },
  {
    id: "missing",
    name: "Incomplete-rate applicant",
    blurb: "Interest rate not yet quoted (blank field).",
    applicant: {
      person_age: 31,
      person_income: 42000,
      person_home_ownership: "RENT",
      person_emp_length: 4,
      loan_intent: "MEDICAL",
      loan_grade: "E",
      loan_amnt: 10000,
      loan_int_rate: null,
      cb_person_default_on_file: "N",
      cb_person_cred_hist_length: 6,
    },
  },
];

export const DEFAULT_APPLICANT: Applicant = SAMPLES[3].applicant;
