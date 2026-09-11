import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { ReportData } from "../../../api/types";

export function usePublicReport() {
  const { token } = useParams();
  return useQuery({ queryKey: ["public-report", token], queryFn: () => api.get<ReportData>(endpoints.publicReport(token!)), retry: false });
}
