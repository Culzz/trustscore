"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export type PersonaMode = "applicant" | "auditor";

interface ModeContextValue {
  mode: PersonaMode;
  setMode: (mode: PersonaMode) => void;
  toggle: () => void;
}

const ModeContext = createContext<ModeContextValue | null>(null);
const STORAGE_KEY = "trustscore:mode";

/**
 * The global persona shell.
 *
 * One toggle swaps the whole platform between the light, plain-language
 * applicant experience and the dark, high-density auditor terminal. The mode
 * drives the shell chrome (header, banner, background) and is persisted so a
 * reload keeps you where you were.
 */
export function ModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<PersonaMode>("applicant");

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored === "auditor" || stored === "applicant") setModeState(stored);
    } catch {
      /* storage unavailable */
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.mode = mode;
  }, [mode]);

  const setMode = useCallback((next: PersonaMode) => {
    setModeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable */
    }
  }, []);

  const value = useMemo<ModeContextValue>(
    () => ({
      mode,
      setMode,
      toggle: () => setMode(mode === "applicant" ? "auditor" : "applicant"),
    }),
    [mode, setMode],
  );

  return <ModeContext.Provider value={value}>{children}</ModeContext.Provider>;
}

export function useMode(): ModeContextValue {
  const ctx = useContext(ModeContext);
  if (!ctx) throw new Error("useMode must be used inside <ModeProvider>");
  return ctx;
}
