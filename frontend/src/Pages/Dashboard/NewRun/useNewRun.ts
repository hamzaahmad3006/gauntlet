import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../../../api/client";
import { endpoints } from "../../../api/endpoints";
import type { ConditionProfile, Estimate, Run, Suite, Target, ThresholdProfile } from "../../../api/types";

export interface RunForm {
  target_id: string;
  suite_id: string;
  condition_profile_key: string;
  threshold_profile_key: string;
  concurrency: number;
  repeats: number;
  spend_cap_usd: string;
  seed: string;
  label: string;
  scenario_keys: string[];
  persona_keys: string[];
}

export function useNewRun() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const targets = useQuery({ queryKey: ["targets"], queryFn: () => api.get<Target[]>(endpoints.targets()) });
  const suites = useQuery({ queryKey: ["suites"], queryFn: () => api.get<Suite[]>(endpoints.suites()) });
  const conditions = useQuery({ queryKey: ["conditions"], queryFn: () => api.get<ConditionProfile[]>(endpoints.conditionProfiles()) });
  const thresholds = useQuery({ queryKey: ["thresholds"], queryFn: () => api.get<ThresholdProfile[]>(endpoints.thresholdProfiles()) });
  const [form, setForm] = useState<RunForm>({
    target_id: params.get("target") ?? "", suite_id: "", condition_profile_key: params.get("conditions") ?? "clean",
    threshold_profile_key: "default", concurrency: 2, repeats: 1, spend_cap_usd: "", seed: params.get("seed") ?? "",
    label: "", scenario_keys: [], persona_keys: [],
  });
  useEffect(() => {
    setForm((f) => ({
      ...f,
      target_id: f.target_id || targets.data?.find((t) => t.verified_at)?.id || "",
      suite_id: f.suite_id || suites.data?.[0]?.id || "",
    }));
  }, [targets.data, suites.data]);

  const suite = suites.data?.find((s) => s.id === form.suite_id);
  const body = useMemo(() => ({
    target_id: form.target_id, suite_id: form.suite_id, condition_profile_key: form.condition_profile_key,
    threshold_profile_key: form.threshold_profile_key, concurrency: form.concurrency, repeats: form.repeats,
    spend_cap_usd: form.spend_cap_usd ? Number(form.spend_cap_usd) : undefined,
    seed: form.seed ? Number(form.seed) : undefined, label: form.label || undefined,
    scenario_keys: form.scenario_keys.length ? form.scenario_keys : undefined,
    persona_keys: form.persona_keys.length ? form.persona_keys : undefined,
  }), [form]);

  const estimate = useQuery({
    queryKey: ["estimate", body],
    queryFn: () => api.post<Estimate>(endpoints.estimate(), body),
    enabled: !!form.target_id && !!form.suite_id,
    placeholderData: (prev) => prev,
  });

  const start = useMutation({
    mutationFn: () => api.post<{ run: Run }>(endpoints.runs(), body, { "Idempotency-Key": crypto.randomUUID() }),
    onSuccess: (r) => nav(`/dashboard/runs/${r.run.id}/live`),
  });

  // One call, the tuned bundled agent, the simplest scenario, no impairment: the fastest way to see a conversation.
  const quick = useMutation({
    mutationFn: () => {
      const tuned = targets.data?.find((t) => t.verified_at && /tuned/i.test(t.name)) ?? targets.data?.find((t) => t.verified_at);
      const s = suites.data?.[0];
      if (!tuned || !s) throw new Error("No verified target or suite yet");
      return api.post<{ run: Run }>(endpoints.runs(), {
        target_id: tuned.id, suite_id: s.id, condition_profile_key: "clean", concurrency: 1, repeats: 1,
        scenario_keys: [s.scenarios[0].key], persona_keys: [s.personas[0].key], label: "quick demo",
      }, { "Idempotency-Key": crypto.randomUUID() });
    },
    onSuccess: (r) => nav(`/dashboard/runs/${r.run.id}/live`),
  });

  const set = <K extends keyof RunForm>(k: K, v: RunForm[K]) => setForm((f) => ({ ...f, [k]: v }));
  const toggle = (k: "scenario_keys" | "persona_keys", key: string) =>
    setForm((f) => ({ ...f, [k]: f[k].includes(key) ? f[k].filter((x) => x !== key) : [...f[k], key] }));

  return { targets, suites, conditions, thresholds, suite, form, set, toggle, estimate, start, quick };
}
