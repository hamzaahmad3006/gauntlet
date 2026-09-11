import { useQuery } from "@tanstack/react-query";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { Calibration } from "../../../api/types";

export function useCalibration() {
  return useQuery({ queryKey: ["calibration"], queryFn: () => api.get<Calibration & { scope_statement?: string; evidence?: string }>(endpoints.calibration()) });
}
