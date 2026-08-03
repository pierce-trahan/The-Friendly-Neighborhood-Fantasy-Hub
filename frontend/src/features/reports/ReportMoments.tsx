import type { PostDraftReport } from "../../api/client";
import { SafeValue, humanize } from "./ReportSection";

export function ReportMoments({ moments }: { moments: PostDraftReport["moments"] }) {
  return (
    <section className="report-moments" aria-labelledby="report-moments-heading">
      <div className="report-subheading">
        <p className="eyebrow">Saved context</p>
        <h2 id="report-moments-heading">Decision moments</h2>
      </div>
      {moments.length === 0 ? (
        <p className="report-muted">No bounded decision moments were recorded.</p>
      ) : (
        <ol>
          {moments.map((moment) => (
            <li key={moment.moment_key}>
              <strong>{humanize(moment.moment_kind)}</strong>
              {moment.overall_pick && <span>Pick {moment.overall_pick}</span>}
              <SafeValue value={moment.safe_summary} />
              {moment.limitation_codes.length > 0 && (
                <SafeValue value={{ limitations: moment.limitation_codes }} />
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
