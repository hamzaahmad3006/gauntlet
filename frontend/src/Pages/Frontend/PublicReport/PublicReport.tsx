import { Link } from "react-router-dom";
import { Footer } from "../../../components/Footer";
import { Logo } from "../../../components/Nav";
import { ReportView } from "../../../components/ReportView";
import { EmptyState, Skeleton } from "../../../components/ui";
import { usePublicReport } from "./usePublicReport";

export default function PublicReport() {
  const report = usePublicReport();
  return (
    <div className="min-h-full">
      <header className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
        <Link to="/" className="no-underline"><Logo /></Link>
        <span className="text-xs text-muted">Shared read-only report</span>
      </header>
      <main className="mx-auto max-w-5xl px-4">
        {report.isLoading ? <Skeleton rows={8} />
          : report.isError ? <EmptyState title="Report not found">This link does not exist, has expired, or was revoked.</EmptyState>
          : <ReportView r={report.data!} />}
      </main>
      <Footer />
    </div>
  );
}
