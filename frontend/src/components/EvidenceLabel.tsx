import { Badge } from "./ui";

/** PRD 0.1 evidence labels, visible on every metric surface. */
export function EvidenceLabel({ kind }: { kind: "MEASURED" | "THRESHOLD" | "TARGET" | "ESTIMATED" | "REPLAY" | "LIVE" | string }) {
  const tone = kind === "MEASURED" ? "info" : kind === "ESTIMATED" ? "warn" : kind === "LIVE" ? "live" : "muted";
  const title: Record<string, string> = {
    MEASURED: "Produced by this executed run; raw rows are stored.",
    THRESHOLD: "A configured pass/fail boundary — a policy decision, not a result.",
    TARGET: "An aim, not evidence.",
    ESTIMATED: "A model over declared prices, not a measurement.",
    REPLAY: "A stored real run played back; not happening now.",
    LIVE: "Happening now.",
  };
  return <Badge tone={tone} title={title[kind]}>{kind}</Badge>;
}
