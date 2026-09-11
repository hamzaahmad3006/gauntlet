import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { ReportData } from "../../../api/types";

export function useReport() {
  const { id } = useParams();
  const report = useQuery({ queryKey: ["report", id], queryFn: () => api.get<ReportData>(endpoints.report(id!)) });
  const md = useQuery({ queryKey: ["report-md", id], queryFn: () => api.text(endpoints.reportMd(id!)) });
  const share = useMutation({ mutationFn: () => api.post<{ url: string }>(endpoints.share(id!), { expires_in_days: 30 }) });
  const revoke = useMutation({ mutationFn: () => api.del<{ revoked: number }>(endpoints.share(id!)) });
  return { id: id!, report, md, share, revoke };
}
