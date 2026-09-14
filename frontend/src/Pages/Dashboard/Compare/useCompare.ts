import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
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
  // With nothing chosen, pre-select two graded runs of different targets under the same conditions (the
  // bundled tuned and slow-endpointing agents), higher score as the baseline.
  useEffect(() => {
    if (a || b || !runs.data) return;
    const graded = runs.data.items.filter((r) => r.grade && r.overall != null);
    for (const x of graded) {
      const y = graded.find((z) => z.target_id !== x.target_id && z.condition_profile_key === x.condition_profile_key && z.suite_version_hash === x.suite_version_hash);
      if (y) {
        const [base, cand] = (x.overall ?? 0) >= (y.overall ?? 0) ? [x, y] : [y, x];
        setParams(new URLSearchParams({ a: base.id, b: cand.id }), { replace: true });
        return;
      }
    }
  }, [a, b, runs.data, setParams]);

  const pick = (side: "a" | "b", id: string) => {
    const next = new URLSearchParams(params);
    next.set(side, id);
    setParams(next);
  };
  const swap = () => setParams(new URLSearchParams({ a: b, b: a }));
  return { a, b, runs, result, pick, swap };
}
