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

export const BAND_STYLES: Record<Band, { chip: string; text: string; ring: string }> = {
  approve: {
    chip: "bg-emerald-100 text-emerald-800 border-emerald-200",
    text: "text-emerald-700",
    ring: "stroke-emerald-500",
  },
  refer: {
    chip: "bg-amber-100 text-amber-800 border-amber-200",
    text: "text-amber-700",
    ring: "stroke-amber-500",
  },
  decline: {
    chip: "bg-rose-100 text-rose-800 border-rose-200",
    text: "text-rose-700",
    ring: "stroke-rose-500",
  },
};

export const BAND_LABEL_TEXT: Record<BandLabel, string> = {
  low: "Low risk",
  medium: "Medium risk",
  high: "High risk",
};
