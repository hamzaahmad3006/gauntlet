import type { Run } from "../api/types";
import { Badge } from "./ui";

export function RunStatus({ run }: { run: Pick<Run, "status"> }) {
  const inflight = run.status === "queued" || run.status === "running";
  const tone = inflight ? "live" : run.status === "completed" ? "pass" : "breach";
  return (
    <Badge tone={tone}>
      {inflight && <span className="pulse h-1.5 w-1.5 rounded-full bg-live" />}
      {run.status === "completed" && <span aria-hidden>✓</span>}
      {run.status.replace("_", " ")}
    </Badge>
  );
}
