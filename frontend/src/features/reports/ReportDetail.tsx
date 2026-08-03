import {
  type PostDraftReport,
  getPostDraftReportExportUrl,
} from "../../api/client";
import { ReportMoments } from "./ReportMoments";
import { ReportSection, humanize } from "./ReportSection";

const sectionOrder = [
  "draft_summary",
  "position_inventory",
  "starter_coverage",
  "roster_concentration",
  "year_one_production_context",
  "dynasty_market_context",
  "age_risk_profile",
  "long_term_value",
  "liquidity",
  "player_fragility",
  "strategy_story",
  "personal_board_choice_moments",
  "recorded_alert_moments",
  "evidence_limits",
];

function timestamp(value: string) {
  return `${value.replace("T", " ").replace("Z", "").slice(0, 16)} UTC`;
}

export function ReportDetail({ report }: { report: PostDraftReport }) {
  const orderedSections = sectionOrder
    .map((key) => report.sections.find((section) => section.section_key === key))
    .filter((section): section is PostDraftReport["sections"][number] => Boolean(section));

  return (
    <section className="report-detail" aria-labelledby="report-detail-heading">
      <header className="report-detail-hero">
        <div>
          <p className="eyebrow">Saved post-draft report</p>
          <h2 id="report-detail-heading">{report.draft_name}</h2>
          <p>
            {humanize(report.draft_mode)} draft · completed {timestamp(report.completed_at)}
          </p>
        </div>
        {report.export_available && (
          <a
            className="secondary-button report-export-link"
            href={getPostDraftReportExportUrl(report.id)}
            download
          >
            Export HTML
          </a>
        )}
      </header>

      <dl className="report-identity-grid">
        <div><dt>Frozen revision</dt><dd>{report.draft_revision}</dd></div>
        <div><dt>Engine</dt><dd>{report.report_engine_version}</dd></div>
        <div><dt>Rules</dt><dd>{report.report_rules_version}</dd></div>
        <div><dt>Generated</dt><dd>{timestamp(report.generated_at)}</dd></div>
      </dl>
      <p className="report-local-note">
        Export creates one local standalone file. It does not upload or publish this report.
      </p>

      <section className="report-roster" aria-labelledby="report-roster-heading">
        <div className="report-subheading">
          <p className="eyebrow">Frozen roster</p>
          <h2 id="report-roster-heading">Roster inventory</h2>
        </div>
        <div className="report-table-scroll">
          <table>
            <caption>Drafted players in pick order</caption>
            <thead>
              <tr>
                <th scope="col">Pick</th><th scope="col">Player</th>
                <th scope="col">Position</th><th scope="col">Assignment</th>
                <th scope="col">Saved rank</th><th scope="col">Saved tier</th>
                <th scope="col">Favorite</th>
              </tr>
            </thead>
            <tbody>
              {report.roster.map((player) => (
                <tr key={`${player.overall_pick}-${player.player_id}`}>
                  <td>{player.overall_pick}</td><td>{player.display_name}</td>
                  <td>{player.primary_position}</td>
                  <td>{player.starter_assignment ?? "Depth"}</td>
                  <td>{player.saved_personal_rank ?? "—"}</td>
                  <td>{player.saved_tier_order ?? "—"}</td>
                  <td>{player.saved_favorite ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="report-sections" aria-label="Report sections">
        {orderedSections.map((section) => (
          <ReportSection key={section.section_key} section={section} />
        ))}
      </section>
      <ReportMoments moments={report.moments} />
    </section>
  );
}
