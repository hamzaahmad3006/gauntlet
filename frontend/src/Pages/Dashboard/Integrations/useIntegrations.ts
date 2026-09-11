import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { ApiKey, Gate, Target } from "../../../api/types";

export function useIntegrations() {
  const qc = useQueryClient();
  const keys = useQuery({ queryKey: ["keys"], queryFn: () => api.get<ApiKey[]>(endpoints.apiKeys()) });
  const gates = useQuery({ queryKey: ["gates"], queryFn: () => api.get<Gate[]>(endpoints.gates()) });
  const targets = useQuery({ queryKey: ["targets"], queryFn: () => api.get<Target[]>(endpoints.targets()) });
  const [name, setName] = useState("github-actions");
  const [fresh, setFresh] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () => api.post<{ key: string }>(endpoints.apiKeys(), { name, scopes: ["run:create", "run:read", "gate:execute"] }),
    onSuccess: (r) => {
      setFresh(r.key);
      void qc.invalidateQueries({ queryKey: ["keys"] });
    },
  });
  const revoke = useMutation({ mutationFn: (id: string) => api.del(endpoints.apiKey(id)), onSuccess: () => void qc.invalidateQueries({ queryKey: ["keys"] }) });
  return { keys, gates, targets, name, setName, fresh, dismiss: () => setFresh(null), create, revoke };
}
