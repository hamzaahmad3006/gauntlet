import type { ReactNode } from "react";
import { ApiError } from "../../api/client";
import { Button } from "./Button";

export function Skeleton({ rows = 3, className = "" }: { rows?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-9 rounded bg-panel2 animate-pulse" />
      ))}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line p-8 text-center">
      <div className="font-medium">{title}</div>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, retry }: { error: unknown; retry?: () => void }) {
  const e = error instanceof ApiError ? error : null;
  return (
    <div role="alert" className="rounded-lg border border-breach/40 bg-breach/5 p-4 text-sm">
      <div className="font-medium text-breach">{e ? e.message : "Something went wrong."}</div>
      {e?.correlationId && <div className="mt-1 text-xs text-muted mono">correlation id {e.correlationId}</div>}
      {retry && <Button className="mt-3" onClick={retry}>Retry</Button>}
    </div>
  );
}
