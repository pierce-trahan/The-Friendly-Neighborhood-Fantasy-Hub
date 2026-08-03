import type { PostDraftReport } from "../../api/client";

export function humanize(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function SafeValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="report-muted">Not available</span>;
  }
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  if (typeof value === "string" || typeof value === "number") {
    return <span>{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="report-muted">None recorded</span>;
    return (
      <ul className="report-value-list">
        {value.map((item, index) => (
          <li key={index}>
            <SafeValue value={item} />
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) {
      return <span className="report-muted">None recorded</span>;
    }
    return (
      <table className="report-value-table">
        <caption>Saved observations</caption>
        <tbody>
          {entries.map(([key, item]) => (
            <tr key={key}>
              <th scope="row">{humanize(key)}</th>
              <td>
                <SafeValue value={item} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  return <span className="report-muted">Unsupported saved value</span>;
}

type ReportSectionValue = PostDraftReport["sections"][number];

export function ReportSection({ section }: { section: ReportSectionValue }) {
  return (
    <article className="report-section-card" data-section={section.section_key}>
      <div className="report-section-heading">
        <div>
          <h3>{section.title}</h3>
          <p>{section.explanation}</p>
        </div>
        <div className="report-status-pair" aria-label="Section status">
          <span>Availability: {humanize(section.availability)}</span>
          <span>Confidence: {humanize(section.confidence)}</span>
        </div>
      </div>
      <details>
        <summary>Inspect saved observations and limits</summary>
        <div className="report-detail-grid">
          <div>
            <h4>Observations</h4>
            <SafeValue value={section.metrics} />
          </div>
          <div>
            <h4>Reasons and limitations</h4>
            <SafeValue
              value={{
                reason_codes: section.reason_codes,
                limitation_codes: section.limitation_codes,
              }}
            />
            {Object.keys(section.safe_provenance).length > 0 && (
              <>
                <h4>Safe provenance</h4>
                <SafeValue value={section.safe_provenance} />
              </>
            )}
          </div>
        </div>
      </details>
    </article>
  );
}
