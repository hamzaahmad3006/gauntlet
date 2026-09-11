import { useSession } from "./Session";
import { Badge } from "./ui";

const LABELS: Record<string, string> = {
  caller_llm: "Caller LLM",
  caller_tts: "Caller voice",
  referee_stt: "Referee STT",
  livekit: "LiveKit",
  object_storage: "Storage",
  github_oauth: "GitHub sign-in",
};

/** Which providers this deployment actually has. An integration is named as used only if configured. */
export function SystemBadge({ detailed = false }: { detailed?: boolean }) {
  const { system } = useSession();
  if (!system) return null;
  if (!detailed) {
    return <Badge tone={system.environment === "production" ? "pass" : "warn"}>{system.environment}</Badge>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(system.providers).map(([k, on]) => (
        <Badge key={k} tone={on ? "pass" : "muted"} title={on ? "configured" : "not configured — documented fallback in use"}>
          {LABELS[k] ?? k}: {on ? "on" : "fallback"}
        </Badge>
      ))}
    </div>
  );
}
