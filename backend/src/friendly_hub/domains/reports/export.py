from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from typing import Any

from friendly_hub.domains.reports.schemas import (
    PostDraftReportMomentRead,
    PostDraftReportRead,
)

MAXIMUM_EXPORT_BYTES = 2 * 1024 * 1024

_UNSAFE_KEYS = {
    "id",
    "report_id",
    "draft_session_id",
    "player_id",
    "primary_player_id",
    "secondary_player_id",
    "snapshot_id",
    "configuration_id",
    "input_fingerprint",
}
_UNSAFE_KEY_PARTS = (
    "private",
    "provider",
    "raw_",
    "source_player",
    "random_audit",
    "alternatives",
    "manager_reference",
)


@dataclass(frozen=True)
class ReportHtmlExport:
    filename: str
    html: str
    byte_count: int


def _label(value: str) -> str:
    return value.replace("_", " ").strip().capitalize()


def _safe_document(value: Any) -> Any:
    if value is None or isinstance(value, str | bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, list):
        if len(value) > 2_000:
            raise ValueError("export list exceeds the safe rendering limit")
        return [_safe_document(item) for item in value]
    if isinstance(value, dict):
        if len(value) > 2_000:
            raise ValueError("export mapping exceeds the safe rendering limit")
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("export mapping keys must be non-empty strings")
            folded = key.casefold()
            if (
                folded in _UNSAFE_KEYS
                or any(part in folded for part in _UNSAFE_KEY_PARTS)
                or folded.endswith("_id")
                or folded.endswith("_ids")
            ):
                continue
            result[key] = _safe_document(item)
        return dict(sorted(result.items()))
    raise ValueError("export value type is not supported")


def _render_value(value: Any) -> str:
    if value is None:
        return '<span class="muted">Not available</span>'
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return escape(value)
    if isinstance(value, list):
        if not value:
            return '<span class="muted">None recorded</span>'
        return "<ul>" + "".join(f"<li>{_render_value(item)}</li>" for item in value) + "</ul>"
    if isinstance(value, dict):
        if not value:
            return '<span class="muted">None recorded</span>'
        rows = "".join(
            "<tr>"
            f'<th scope="row">{escape(_label(key))}</th>'
            f"<td>{_render_value(item)}</td>"
            "</tr>"
            for key, item in value.items()
        )
        return '<table class="nested"><tbody>' + rows + "</tbody></table>"
    raise ValueError("export value was not normalized")


def _section_html(section) -> str:
    metrics = _safe_document(section.metrics)
    provenance = _safe_document(section.safe_provenance)
    limitations = _safe_document(section.limitation_codes)
    reasons = _safe_document(section.reason_codes)
    return (
        f'<section class="report-section" data-section="{escape(section.section_key, quote=True)}">'
        f"<h2>{escape(section.title)}</h2>"
        '<dl class="status-grid">'
        f"<div><dt>Availability</dt><dd>{escape(section.availability)}</dd></div>"
        f"<div><dt>Confidence</dt><dd>{escape(section.confidence)}</dd></div>"
        "</dl>"
        f'<p class="explanation">{escape(section.explanation)}</p>'
        "<h3>Saved observations</h3>"
        f"{_render_value(metrics)}"
        "<h3>Reasons and limits</h3>"
        f"{_render_value({'reason_codes': reasons, 'limitation_codes': limitations})}"
        + (
            "<h3>Safe provenance</h3>" + _render_value(provenance)
            if provenance
            else ""
        )
        + "</section>"
    )


def _roster_html(report: PostDraftReportRead) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{player.overall_pick}</td>"
        f"<td>{escape(player.display_name)}</td>"
        f"<td>{escape(player.primary_position)}</td>"
        f"<td>{escape(player.starter_assignment or 'Depth')}</td>"
        f"<td>{_render_value(player.saved_personal_rank)}</td>"
        f"<td>{_render_value(player.saved_tier_order)}</td>"
        f"<td>{'Yes' if player.saved_favorite else 'No'}</td>"
        "</tr>"
        for player in report.roster
    )
    return (
        '<section class="report-section" id="roster">'
        "<h2>Roster inventory</h2>"
        "<table><caption>Drafted roster in pick order</caption>"
        "<thead><tr>"
        '<th scope="col">Pick</th><th scope="col">Player</th>'
        '<th scope="col">Position</th><th scope="col">Assignment</th>'
        '<th scope="col">Saved rank</th><th scope="col">Saved tier</th>'
        '<th scope="col">Favorite</th>'
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def _moments_html(report: PostDraftReportRead) -> str:
    if not report.moments:
        body = '<p class="muted">No bounded decision moments were recorded.</p>'
    else:
        def codes(moment: PostDraftReportMomentRead) -> dict[str, object]:
            return {
                "reason_codes": moment.reason_codes,
                "limitation_codes": moment.limitation_codes,
            }

        body = "<ol>" + "".join(
            "<li>"
            f"<h3>{escape(_label(moment.moment_kind))}</h3>"
            f"{_render_value(_safe_document(moment.safe_summary))}"
            f"{_render_value(_safe_document(codes(moment)))}"
            "</li>"
            for moment in report.moments
        ) + "</ol>"
    return (
        '<section class="report-section" id="moments">'
        "<h2>Decision moments</h2>"
        + body
        + "</section>"
    )


def _filename(draft_name: str, completed_at: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", draft_name.casefold()).strip("-")[:60].strip("-")
    if not slug:
        slug = "draft-report"
    date = completed_at[:10] if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", completed_at) else "undated"
    return f"friendly-hub-{slug}-{date}.html"


def render_report_html(report: PostDraftReportRead) -> ReportHtmlExport:
    sections = "".join(_section_html(section) for section in report.sections)
    identity = _safe_document(
        {
            "draft_name": report.draft_name,
            "mode": report.draft_mode,
            "completed_at": report.completed_at,
            "generated_at": report.generated_at,
            "report_engine_version": report.report_engine_version,
            "report_rules_version": report.report_rules_version,
            "explanation_template_version": report.explanation_template_version,
            "league_shape_fingerprint": report.league_shape_fingerprint,
        }
    )
    css = """
    :root{font-family:Arial,sans-serif;color:#172026;background:#f7f4ec}
    body{margin:0;line-height:1.45}
    main,header,footer{max-width:1100px;margin:auto;padding:24px}
    header{background:#172026;color:#fff}
    h1,h2,h3{line-height:1.15}
    h2{border-bottom:2px solid #bf4b2c;padding-bottom:6px}
    .report-section{background:#fff;margin:18px 0;padding:20px}
    .report-section{border:1px solid #c8c5bc;break-inside:avoid}
    table{width:100%;border-collapse:collapse;margin:8px 0}
    caption{text-align:left;font-weight:bold;margin-bottom:6px}
    th,td{border:1px solid #c8c5bc;padding:7px;text-align:left;vertical-align:top}
    .nested th{width:34%}
    .status-grid{display:flex;gap:28px}
    .status-grid div{display:flex;gap:8px}
    .status-grid dt{font-weight:bold}
    .muted{color:#59636a}
    .explanation{font-size:1.05rem}
    footer{font-size:.9rem;color:#59636a}
    @media print{
      body{background:#fff}header{color:#000;background:#fff}
      .report-section{border:0;padding:8px 0}
    }
    """
    content_security_policy = (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; "
        "script-src 'none'; connect-src 'none'; frame-src 'none'; "
        "form-action 'none'"
    )
    html = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" '
        f'content="{content_security_policy}">'
        f"<title>{escape(report.draft_name)} - Friendly Hub report</title>"
        f"<style>{css}</style></head><body>"
        f"<header><h1>{escape(report.draft_name)}</h1><p>Standalone post-draft report</p></header>"
        "<main><section class=\"report-section\"><h2>Report identity and limits</h2>"
        f"{_render_value(identity)}</section>{_roster_html(report)}"
        f"{sections}{_moments_html(report)}</main>"
        "<footer>This local report describes saved evidence, does not project "
        "outcomes, and leaves judgment with the user.</footer>"
        "</body></html>"
    )
    byte_count = len(html.encode("utf-8"))
    if byte_count >= MAXIMUM_EXPORT_BYTES:
        raise ValueError("report export exceeds the two MiB limit")
    return ReportHtmlExport(
        filename=_filename(report.draft_name, report.completed_at),
        html=html,
        byte_count=byte_count,
    )
