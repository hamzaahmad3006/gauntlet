import { Logo } from "./Nav";

const REPO = (import.meta.env.VITE_REPO_URL as string | undefined) ?? "https://github.com/hamzaahmad3006/gauntlet";

export function Footer() {
  return (
    <footer className="mt-16 border-t border-line/80 bg-white/60 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-xs text-muted">
        <div className="flex items-center gap-3">
          <Logo />
          <span className="hidden sm:inline">The crash-test rig for real-time voice AI · measures, never hosts agents · MIT licensed</span>
        </div>
        <span className="flex gap-5">
          <a className="no-underline hover:text-fg" href={REPO} target="_blank" rel="noreferrer">GitHub</a>
          <a className="no-underline hover:text-fg" href="/dashboard/calibration">Calibration</a>
          <a className="no-underline hover:text-fg" href={`${REPO}/blob/main/docs/LIMITATIONS.md`} target="_blank" rel="noreferrer">Limitations</a>
        </span>
      </div>
    </footer>
  );
}
