import { useQuery } from "@tanstack/react-query";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { Run, Target } from "../../../api/types";

export function useTargets() {
  const targets = useQuery({ queryKey: ["targets"], queryFn: () => api.get<Target[]>(endpoints.targets()), refetchInterval: 10_000 });
  const recent = useQuery({
    queryKey: ["runs", "recent"],
    queryFn: () => api.get<{ items: Run[] }>(endpoints.runs("?limit=6")),
    refetchInterval: 5_000,
  });
  return { targets, recent };
}
