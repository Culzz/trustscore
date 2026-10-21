"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { usePathname } from "next/navigation";

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
 * The route owns the material: `/auditor` is the dark governance terminal,
 * every other page is warm paper. Deriving the mode from the pathname (instead
 * of localStorage) means a reload lands on the right surface immediately,
 * with no light-to-dark flash.
 */
export function ModeProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const routeMode: PersonaMode = pathname?.startsWith("/auditor")
    ? "auditor"
    : "applicant";
  const [mode, setModeState] = useState<PersonaMode>(routeMode);

  useEffect(() => {
    setModeState(routeMode);
  }, [routeMode]);

  useEffect(() => {
    document.documentElement.dataset.mode = mode;
    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* storage unavailable */
    }
  }, [mode]);

  const setMode = useCallback((next: PersonaMode) => {
    setModeState(next);
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
