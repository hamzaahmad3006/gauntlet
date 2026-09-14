import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { Footer } from "./Footer";
import { Nav } from "./Nav";
import { useSession } from "./Session";
import { Skeleton } from "./ui";

/** Dashboard shell. Unauthenticated visitors are sent to sign in and brought back afterwards. */
export function Layout() {
  const { token, ready } = useSession();
  const loc = useLocation();
  if (!ready) return <div className="mx-auto max-w-7xl p-6"><Skeleton rows={6} /></div>;
  if (!token) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  return (
    <div className="flex min-h-screen flex-col">
      <Nav />
      <main key={loc.pathname} className="float-in mx-auto w-full max-w-7xl flex-1 px-4 py-8">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-live">{eyebrow}</div>}
        <h1 className="text-2xl font-bold tracking-tight sm:text-[28px]">{title}</h1>
        <div className="bg-gradient-brand mt-2 h-1 w-14 rounded-full" aria-hidden />
        {subtitle && <div className="mt-2 max-w-3xl text-sm text-muted">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
