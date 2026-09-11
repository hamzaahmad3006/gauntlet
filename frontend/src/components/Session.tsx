import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { configureAuth, currentToken, onAuthChange } from "../api/auth";
import { api } from "../api/client";
import { endpoints } from "../api/endpoints";
import type { SystemInfo } from "../api/types";

interface SessionState {
  system: SystemInfo | undefined;
  token: string | null;
  ready: boolean;
  refresh: () => void;
}

const Ctx = createContext<SessionState>({ system: undefined, token: null, ready: false, refresh: () => undefined });

export function SessionProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const system = useQuery({ queryKey: ["system"], queryFn: () => api.get<SystemInfo>(endpoints.system()), staleTime: 60_000 });
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (system.data) configureAuth(system.data.auth.supabase_url, system.data.auth.supabase_anon_key);
    if (!system.data && !system.isError) return;
    let alive = true;
    currentToken().then((t) => {
      if (alive) {
        setToken(t);
        setReady(true);
      }
    });
    const off = onAuthChange(() => setTick((x) => x + 1));
    return () => {
      alive = false;
      off();
    };
  }, [system.data, system.isError, tick]);

  const refresh = () => {
    setTick((x) => x + 1);
    void qc.invalidateQueries();
  };
  return <Ctx.Provider value={{ system: system.data, token, ready, refresh }}>{children}</Ctx.Provider>;
}

export const useSession = () => useContext(Ctx);
