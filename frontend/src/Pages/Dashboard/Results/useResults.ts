import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { RunSummary } from "../../../api/types";

export function useResults() {
  const { id } = useParams();
  const qc = useQueryClient();
  const summary = useQuery({
    queryKey: ["run", id],
    queryFn: () => api.get<RunSummary>(endpoints.run(id!)),
    refetchInterval: (q) => (q.state.data && ["queued", "running"].includes(q.state.data.run.status) ? 3000 : false),
  });
  const promote = useMutation({
    mutationFn: () => api.post(endpoints.baseline(summary.data!.run.target_id), { run_id: id }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["run", id] });
      void qc.invalidateQueries({ queryKey: ["targets"] });
    },
  });
  const share = useMutation({ mutationFn: () => api.post<{ url: string; html_url: string }>(endpoints.share(id!), { expires_in_days: 30 }) });
  const markdown = useMutation({
    mutationFn: async () => {
      const md = await api.text(endpoints.reportMd(id!));
      await navigator.clipboard?.writeText(md).catch(() => undefined);
      return md;
    },
  });
  return { id: id!, summary, promote, share, markdown };
}
