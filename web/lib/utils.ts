import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Band, BandLabel } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatNum(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined) return "—";
  return value.toFixed(digits);
}

export function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `$${Math.round(value).toLocaleString()}`;
}

export const BAND_STYLES: Record<
  Band,
  { chip: string; text: string; ring: string; bar: string }
> = {
  approve: {
    chip: "bg-emerald-50 text-emerald-800 border-emerald-300",
    text: "text-emerald-700",
    ring: "stroke-emerald-600",
    bar: "bg-emerald-500",
  },
  refer: {
    chip: "bg-amber-50 text-amber-800 border-amber-300",
    text: "text-amber-700",
    ring: "stroke-amber-600",
    bar: "bg-amber-500",
  },
  decline: {
    chip: "bg-rose-50 text-rose-800 border-rose-300",
    text: "text-rose-700",
    ring: "stroke-rose-600",
    bar: "bg-rose-500",
  },
};

export const BAND_LABEL_TEXT: Record<BandLabel, string> = {
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};

export const BAND_TO_BAND_LABEL: Record<Band, BandLabel> = {
  approve: "low",
  refer: "medium",
  decline: "high",
};

/** Human-readable risk wording for a band, when only the band is known. */
export function bandText(band: Band): string {
  return BAND_LABEL_TEXT[BAND_TO_BAND_LABEL[band]];
}
