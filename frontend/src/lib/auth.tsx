import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

interface AuthState {
  token: string | null;
  setToken: (t: string | null) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);
const STORAGE_KEY = "docintel_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  });

  const value = useMemo<AuthState>(() => {
    const setToken = (t: string | null) => {
      setTokenState(t);
      try {
        if (t) localStorage.setItem(STORAGE_KEY, t);
        else localStorage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore storage failures */
      }
    };
    return { token, setToken, logout: () => setToken(null) };
  }, [token]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
