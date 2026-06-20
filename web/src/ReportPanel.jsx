import { useEffect, useRef } from "react";
import "../../shared/report-view.js";

const RV = globalThis.JobLensReportView;

/** Same layout as extension: company head → H-1B → fit analysis. */
export default function ReportPanel({ report, status }) {
  const ref = useRef(null);

  useEffect(() => {
    if (ref.current) RV.wireMetricTips(ref.current);
  }, [report]);

  if (!report) return null;

  const html =
    RV.renderUnifiedReport(report) +
    (status ? `<p class="meta flow-status">${RV.escapeHtml(status)}</p>` : "");

  return (
    <section className="result-flow" ref={ref} dangerouslySetInnerHTML={{ __html: html }} />
  );
}
