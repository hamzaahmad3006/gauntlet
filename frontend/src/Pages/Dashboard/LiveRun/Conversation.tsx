import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Panel } from "../../../components/ui";
import { fmt } from "../../../components/ui/format";
import type { Line, Tile } from "./useLiveRun";

const ACTIVE = new Set(["dialling", "connected", "in_call"]);
const DONE = new Set(["completed", "failed", "needs_review", "errored", "scoring"]);

/** The conversation of one call as it happens: what GAUNTLET's caller said, what the referee heard the agent
 * say, and how long the agent took to start answering. Audio is not streamed to the browser; the recording
 * plays on the call page once the call ends. */
export function Conversation({ tiles, lines, threshold, live }: { tiles: Tile[]; lines: Record<string, Line[]>; threshold: number; live: boolean }) {
  const [picked, setPicked] = useState<string | null>(null);
  const withLines = tiles.filter((t) => (lines[t.id]?.length ?? 0) > 0 || ACTIVE.has(t.status));
  const auto = tiles.find((t) => ACTIVE.has(t.status))?.id ?? withLines.at(-1)?.id ?? tiles[0]?.id ?? null;
  const callId = picked && tiles.some((t) => t.id === picked) ? picked : auto;
  const tile = tiles.find((t) => t.id === callId);
  const feed = callId ? lines[callId] ?? [] : [];
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { const box = end.current?.parentElement; if (box) box.scrollTo({ top: box.scrollHeight, behavior: "smooth" }); }, [feed.length]);

  return (
    <Panel title="Live conversation" actions={withLines.length > 1 && (
      <div className="flex flex-wrap gap-1">
        {withLines.map((t, i) => (
          <button key={t.id} onClick={() => setPicked(t.id)}
            className={`rounded border px-2 py-0.5 text-[11px] ${t.id === callId ? "border-info text-info" : "border-line text-muted"}`}>
            call {i + 1}{ACTIVE.has(t.status) ? " ●" : ""}
          </button>
        ))}
      </div>
    )}>
      <p className="mb-3 text-xs text-muted">
        GAUNTLET's AI <span className="font-semibold text-info">caller</span> is phoning the <span className="font-semibold text-pass">agent under test</span> over
        real audio. Each agent reply shows how long the agent took to start answering; anything over {threshold} ms feels slow on a phone.
        {tile && <> This call: <span className="mono">{tile.scenario}</span> as <span className="mono">{tile.persona}</span>.</>}
      </p>
      <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
        {feed.length === 0 && (
          <div className="rounded-md border border-dashed border-line p-4 text-center text-sm text-muted">
            {live ? "Dialling the agent… the first words appear here in a few seconds." : "No conversation was recorded live for this run. Open a finished call to read and hear it."}
          </div>
        )}
        {feed.map((l, i) => (
          <div key={i} className={`flex ${l.speaker === "caller" ? "justify-start" : "justify-end"}`}>
            <div className={`max-w-[80%] rounded-lg border px-3 py-2 text-sm ${l.speaker === "caller" ? "border-info/40 bg-info/10" : "border-pass/40 bg-pass/10"}`}>
              <div className="mb-0.5 flex items-center justify-between gap-3 text-[11px] text-muted">
                <span className="font-semibold">{l.speaker === "caller" ? "Caller (GAUNTLET)" : "Agent under test"}</span>
                {l.speaker === "agent" && l.latency != null && (
                  <span className={`num ${l.latency > threshold ? "text-breach" : "text-pass"}`}>answered after {fmt(l.latency, "ms", 0)}</span>
                )}
              </div>
              {l.text ? l.text : <span className="italic text-muted">{l.referee ? "(spoke, but the words were not recognised)" : "(spoke — add a Speechmatics key to see the words)"}</span>}
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>
      {tile && DONE.has(tile.status) && (
        <div className="mt-3 text-right text-sm">
          <Link className="underline" to={`/dashboard/calls/${tile.id}`}>▶ Listen to this call and see the verdict</Link>
        </div>
      )}
    </Panel>
  );
}
