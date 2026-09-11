import { Link } from "react-router-dom";
import { PageHeader } from "../../../components/Layout";
import { ReportView } from "../../../components/ReportView";
import { Button, ErrorState, Panel, Skeleton, TextArea } from "../../../components/ui";
import { useReport } from "./useReport";

export default function Report() {
  const { id, report, md, share, revoke } = useReport();
  if (report.isLoading) return <Skeleton rows={8} />;
  if (report.isError) return <ErrorState error={report.error} retry={() => report.refetch()} />;
  return (
    <>
      <PageHeader title="Report" subtitle="The artefact that leaves the tool: methodology, configuration, evidence-labelled results, limitations."
        actions={<>
          <Link to={`/dashboard/runs/${id}`}><Button>Back to results</Button></Link>
          <Button busy={share.isPending} onClick={() => share.mutate()}>Create share link</Button>
          <Button variant="danger" busy={revoke.isPending} onClick={() => revoke.mutate()}>Revoke links</Button>
        </>} />
      {share.data && <div className="mb-4 rounded-md border border-pass/40 bg-pass/5 p-3 text-sm">Public, read-only, revocable: <a className="mono underline" href={share.data.url}>{share.data.url}</a></div>}
      {revoke.data && <div className="mb-4 text-sm text-muted">{revoke.data.revoked} link(s) revoked; they now return 404.</div>}
      <ReportView r={report.data!} />
      <div className="mt-4">
        <Panel title="Markdown export" actions={<Button onClick={() => navigator.clipboard?.writeText(md.data ?? "")}>Copy</Button>}>
          <TextArea rows={14} readOnly value={md.data ?? ""} />
        </Panel>
      </div>
    </>
  );
}
