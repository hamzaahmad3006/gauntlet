import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  align?: "left" | "right";
  className?: string;
}

export function DataTable<T>({ columns, rows, rowKey, onRowClick, rowClass, empty }:
  { columns: Column<T>[]; rows: T[]; rowKey: (r: T) => string; onRowClick?: (r: T) => void; rowClass?: (r: T) => string; empty?: ReactNode }) {
  if (!rows.length && empty) return <>{empty}</>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm num">
        <thead>
          <tr className="border-b border-line text-left text-[11px] uppercase tracking-wider text-muted">
            {columns.map((c) => (
              <th key={c.key} className={`px-3 py-2 font-medium ${c.align === "right" ? "text-right" : ""}`}>{c.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={rowKey(r)}
              onClick={onRowClick ? () => onRowClick(r) : undefined}
              className={`border-b border-line/60 ${onRowClick ? "cursor-pointer hover:bg-panel2" : ""} ${rowClass?.(r) ?? ""}`}
            >
              {columns.map((c) => (
                <td key={c.key} className={`px-3 py-2 align-middle ${c.align === "right" ? "text-right" : ""} ${c.className ?? ""}`}>{c.render(r)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
