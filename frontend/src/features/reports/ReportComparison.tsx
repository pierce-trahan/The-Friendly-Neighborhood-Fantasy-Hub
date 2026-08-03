import type {
  PostDraftReportComparison,
  PostDraftReportSummary,
} from "../../api/client";
import { SafeValue, humanize } from "./ReportSection";

function shortDate(value: string) {
  return value.slice(0, 10);
}

export function ReportComparison({
  reports,
  selectedIds,
  result,
  busy,
  onToggle,
  onPreview,
}: {
  reports: PostDraftReportSummary[];
  selectedIds: string[];
  result: PostDraftReportComparison | null;
  busy: boolean;
  onToggle: (reportId: string) => void;
  onPreview: () => void;
}) {
  const baseline = reports.find((report) => report.id === selectedIds[0]);
  const identityById = new Map(result?.reports.map((report) => [report.report_id, report]));

  return (
    <section className="report-comparison" aria-labelledby="report-comparison-heading">
      <div className="report-subheading">
        <p className="eyebrow">Side-by-side preview</p>
        <h2 id="report-comparison-heading">Compare saved construction</h2>
        <p>
          Choose two to four compatible reports. The preview aligns exact saved
          observations without a composite judgment.
        </p>
      </div>
      <fieldset className="report-comparison-picker">
        <legend>Compatible reports</legend>
        {reports.map((report) => {
          const checked = selectedIds.includes(report.id);
          const compatible =
            !baseline ||
            (report.league_shape_fingerprint === baseline.league_shape_fingerprint &&
              report.report_rules_version === baseline.report_rules_version);
          const disabled = !checked && (!compatible || selectedIds.length >= 4);
          return (
            <label key={report.id} className={disabled ? "is-disabled" : undefined}>
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={() => onToggle(report.id)}
              />
              <span>
                <strong>{report.draft_name}</strong>
                <small>
                  {humanize(report.draft_mode)} · {humanize(report.draft_format)} ·{" "}
                  {report.team_count} teams · {report.round_count} rounds ·{" "}
                  {shortDate(report.completed_at)}
                  {report.final_strategy && ` · ${humanize(report.final_strategy)}`}
                </small>
              </span>
            </label>
          );
        })}
      </fieldset>
      <button
        type="button"
        className="secondary-button"
        disabled={selectedIds.length < 2 || selectedIds.length > 4 || busy}
        onClick={onPreview}
      >
        {busy ? "Building local preview…" : "Preview comparison"}
      </button>

      {result && (
        <div className="report-comparison-results" aria-live="polite">
          <p>{result.explanation}</p>
          {result.sections.map((section) => (
            <article key={section.section_key}>
              <div className="report-section-heading">
                <div>
                  <h3>{section.title}</h3>
                  <p>{section.explanation}</p>
                </div>
                <span className="report-comparison-state">
                  {humanize(section.comparison_state)}
                </span>
              </div>
              <div className="report-comparison-columns">
                {section.values.map((value) => {
                  const identity = identityById.get(value.report_id);
                  return (
                    <section key={value.report_id}>
                      <h4>{identity?.draft_name ?? "Saved report"}</h4>
                      <p>
                        Availability: {humanize(value.availability)} · Confidence:{" "}
                        {humanize(value.confidence)}
                      </p>
                      <SafeValue value={value.metrics} />
                      {Object.keys(value.delta_from_first).length > 0 && (
                        <>
                          <h5>Exact change from first report</h5>
                          <SafeValue value={value.delta_from_first} />
                        </>
                      )}
                    </section>
                  );
                })}
              </div>
              {section.limitation_codes.length > 0 && (
                <SafeValue value={{ limitations: section.limitation_codes }} />
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
