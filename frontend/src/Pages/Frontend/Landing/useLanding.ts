import { useQuery } from "@tanstack/react-query";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { Calibration } from "../../../api/types";
import { useSession } from "../../../components/Session";

export function useLanding() {
  const { system, token } = useSession();
  const calibration = useQuery({ queryKey: ["calibration"], queryFn: () => api.get<Calibration>(endpoints.calibration()) });
  return { system, signedIn: !!token, calibration: calibration.data };
}
