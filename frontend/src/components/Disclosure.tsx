/** The mandatory impairment disclosure (SRS-FR-056). It cannot be dismissed, collapsed or hidden. */
export function Disclosure({ text, calibration }: { text: string; calibration?: { bound_ms: number; scope: string } | null }) {
  return (
    <aside className="rounded-lg border border-line bg-panel2 p-3 text-xs leading-relaxed text-muted" aria-label="Measurement limitations">
      <div className="mb-1 font-semibold uppercase tracking-wider text-[10px]">Limitations — always shown</div>
      <p>{text}</p>
      {calibration && (
        <p className="mt-1.5">
          Measurement error bound <span className="num font-semibold text-fg">{calibration.bound_ms} ms</span> (MEASURED, loopback).{" "}
          {calibration.scope}{" "}
          <a className="underline" href="/dashboard/calibration">Calibration report</a>
        </p>
      )}
    </aside>
  );
}
