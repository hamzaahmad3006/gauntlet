const REPO = (import.meta.env.VITE_REPO_URL as string | undefined) ?? "https://github.com/hamzaahmad3006/gauntlet";

export function Footer() {
  return (
    <footer className="mt-12 border-t border-line">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-4 text-xs text-muted">
        <span>GAUNTLET — measures, never hosts or builds agents. MIT licensed.</span>
        <span className="flex gap-4">
          <a href={REPO} target="_blank" rel="noreferrer">Repository</a>
          <a href="/dashboard/calibration">Calibration</a>
          <a href={`${REPO}/blob/main/docs/LIMITATIONS.md`} target="_blank" rel="noreferrer">Limitations</a>
        </span>
      </div>
    </footer>
  );
}
