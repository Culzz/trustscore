import type { Config } from "tailwindcss";

/**
 * "Editorial ledger" design system.
 *
 * Warm paper instead of clinical slate, ink instead of black, terracotta as the
 * single accent, and moss / ochre / brick for the three risk bands. Corners are
 * near-square and shadows are hard offset blocks, so surfaces read like printed
 * stationery rather than floating app cards.
 *
 * The `slate` scale is intentionally re-mapped: every existing `slate-*` class
 * in the app now resolves to warm paper/ink, which keeps the auditor terminal
 * and the applicant view on the same material.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: "#FCFAF3",
          50: "#FDFCF8",
          100: "#F8F3E8",
          200: "#F0E8D8",
        },
        ink: "#241F18",
        brand: {
          50: "#FBF0E9",
          100: "#F6DFD0",
          200: "#EDC0A6",
          300: "#E09B75",
          400: "#D07448",
          500: "#BF582C",
          600: "#A64420",
          700: "#86361A",
          800: "#682B16",
          900: "#4E2112",
          950: "#2C1108",
        },
        slate: {
          50: "#F8F3E8",
          100: "#F0E8D8",
          200: "#E2D6C0",
          300: "#CBBBA0",
          400: "#A8977C",
          500: "#857560",
          600: "#6A5C48",
          700: "#514636",
          800: "#362F25",
          900: "#241F18",
          950: "#15110C",
        },
        emerald: {
          50: "#EFF3EA",
          100: "#DFE8D4",
          200: "#C3D3AE",
          300: "#A2BB86",
          400: "#7F9E60",
          500: "#5F7F43",
          600: "#486532",
          700: "#3A5029",
          800: "#2F4023",
          900: "#26341D",
          950: "#131C0E",
        },
        amber: {
          50: "#FBF4E2",
          100: "#F7E8C4",
          200: "#EED39A",
          300: "#E0B763",
          400: "#CD9837",
          500: "#B37C24",
          600: "#92601D",
          700: "#744B1B",
          800: "#5C3D1B",
          900: "#4A3218",
          950: "#281A0B",
        },
        rose: {
          50: "#FAEDEA",
          100: "#F4DAD3",
          200: "#E8B9AC",
          300: "#D9917E",
          400: "#C66A53",
          500: "#AE4B35",
          600: "#913827",
          700: "#752C20",
          800: "#5D261D",
          900: "#4A211A",
          950: "#280F0B",
        },
        sky: {
          50: "#EDF2F3",
          100: "#D9E5E7",
          200: "#B7CDD1",
          300: "#8CADB4",
          400: "#6D99A2",
          500: "#4E7A83",
          600: "#3F646C",
          700: "#365158",
          800: "#30444A",
          900: "#2C3C40",
          950: "#152023",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-sans)",
          "Public Sans Variable",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        display: [
          "var(--font-display)",
          "Newsreader Variable",
          "Iowan Old Style",
          "Georgia",
          "serif",
        ],
        mono: [
          "var(--font-mono)",
          "IBM Plex Mono",
          "ui-monospace",
          "SFMono-Regular",
          "monospace",
        ],
      },
      borderRadius: {
        DEFAULT: "3px",
        sm: "2px",
        md: "3px",
        lg: "4px",
        xl: "6px",
        "2xl": "8px",
        "3xl": "12px",
      },
      boxShadow: {
        sm: "2px 2px 0 0 rgba(36, 31, 24, 0.05)",
        DEFAULT: "3px 3px 0 0 rgba(36, 31, 24, 0.07)",
        md: "4px 4px 0 0 rgba(36, 31, 24, 0.08)",
        lg: "6px 6px 0 0 rgba(36, 31, 24, 0.10)",
        lift: "4px 4px 0 0 rgba(36, 31, 24, 0.16)",
        press: "1px 1px 0 0 rgba(36, 31, 24, 0.12)",
      },
      letterSpacing: {
        label: "0.16em",
        stamp: "0.22em",
      },
      transitionTimingFunction: {
        editorial: "cubic-bezier(0.2, 0.8, 0.2, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
