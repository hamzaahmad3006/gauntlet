import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { Run, Target } from "../../../api/types";

export function useRuns() {
  const [target, setTarget] = useState("");
  const [status, setStatus] = useState("");
  const targets = useQuery({ queryKey: ["targets"], queryFn: () => api.get<Target[]>(endpoints.targets()) });
  const runs = useInfiniteQuery({
    queryKey: ["runs", "history", target, status],
    initialPageParam: "",
    queryFn: ({ pageParam }) => {
      const q = new URLSearchParams({ limit: "25", ...(target ? { target_id: target } : {}), ...(status ? { status } : {}), ...(pageParam ? { cursor: pageParam } : {}) });
      return api.get<{ items: Run[]; next_cursor: string | null }>(endpoints.runs(`?${q}`));
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: 5000,
  });
  return { targets, runs, target, setTarget, status, setStatus, items: runs.data?.pages.flatMap((p) => p.items) ?? [] };
}
