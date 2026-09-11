import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { CompareResult, Run } from "../../../api/types";

export function useCompare() {
  const [params, setParams] = useSearchParams();
  const a = params.get("a") ?? "";
  const b = params.get("b") ?? "";
  const runs = useQuery({ queryKey: ["runs", "completed"], queryFn: () => api.get<{ items: Run[] }>(endpoints.runs("?status=completed&limit=100")) });
  const result = useQuery({
    queryKey: ["compare", a, b],
    queryFn: () => api.get<CompareResult>(endpoints.compare(a, b)),
    enabled: !!a && !!b && a !== b,
    retry: false,
  });
  const pick = (side: "a" | "b", id: string) => {
    const next = new URLSearchParams(params);
    next.set(side, id);
    setParams(next);
  };
  const swap = () => setParams(new URLSearchParams({ a: b, b: a }));
  return { a, b, runs, result, pick, swap };
}
