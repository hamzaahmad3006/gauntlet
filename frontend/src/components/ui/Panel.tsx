import type { ReactNode } from "react";

export function Panel({ title, actions, children, className = "", pad = true }:
  { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; pad?: boolean }) {
  return (
    <section className={`glass rounded-2xl ${className}`}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line/80 px-5 py-3">
          <h2 className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-gradient-to-r from-accent to-live" aria-hidden />
            {title}
          </h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={pad ? "p-5" : ""}>{children}</div>
    </section>
  );
}
