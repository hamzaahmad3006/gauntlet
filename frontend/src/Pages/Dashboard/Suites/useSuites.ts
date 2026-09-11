import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { ConditionProfile, Suite, ThresholdProfile } from "../../../api/types";

export function useSuites() {
  const qc = useQueryClient();
  const suites = useQuery({ queryKey: ["suites"], queryFn: () => api.get<Suite[]>(endpoints.suites()) });
  const conditions = useQuery({ queryKey: ["conditions"], queryFn: () => api.get<ConditionProfile[]>(endpoints.conditionProfiles()) });
  const thresholds = useQuery({ queryKey: ["thresholds"], queryFn: () => api.get<ThresholdProfile[]>(endpoints.thresholdProfiles()) });
  const [selected, setSelected] = useState<string | null>(null);
  const [yaml, setYaml] = useState("");
  const upload = useMutation({
    mutationFn: () => api.post<{ version_hash: string }>(endpoints.suites(), { yaml }),
    onSuccess: () => {
      setYaml("");
      void qc.invalidateQueries({ queryKey: ["suites"] });
    },
  });
  return { suites, conditions, thresholds, selected, setSelected, yaml, setYaml, upload };
}
