import { useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  type DraftSession,
  type PostDraftReport,
  type PostDraftReportComparison,
  type PostDraftReportSummary,
  generatePostDraftReport,
  getBoardPostDraftReports,
  getBoards,
  getDraftSession,
  getDraftSessions,
  getPostDraftReport,
  previewPostDraftReportComparison,
} from "../../api/client";
import { ReportComparison } from "./ReportComparison";
import { ReportDetail } from "./ReportDetail";
import { humanize } from "./ReportSection";

type BoardSummary = Awaited<ReturnType<typeof getBoards>>["items"][number];
type DraftSummary = Awaited<ReturnType<typeof getDraftSessions>>["items"][number];
type UiError = { message: string; action?: string };

function formatError(error: unknown): UiError {
  if (error instanceof ApiError) {
    return { message: error.message, action: error.action };
  }
  return {
    message: "The Reports workspace could not finish that local action.",
    action: "Refresh the saved board and try again.",
  };
}

function timestamp(value: string | null) {
  if (!value) return "Completion time unavailable";
  return `${value.replace("T", " ").replace("Z", "").slice(0, 16)} UTC`;
}

export function ReportWorkspace() {
  const [boards, setBoards] = useState<BoardSummary[]>([]);
  const [boardId, setBoardId] = useState("");
  const [drafts, setDrafts] = useState<DraftSummary[]>([]);
  const [reports, setReports] = useState<PostDraftReportSummary[]>([]);
  const [selectedReport, setSelectedReport] = useState<PostDraftReport | null>(null);
  const [confirmDraft, setConfirmDraft] = useState<DraftSession | null>(null);
  const [comparisonIds, setComparisonIds] = useState<string[]>([]);
  const [comparison, setComparison] = useState<PostDraftReportComparison | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<UiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const lastTrigger = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    getBoards()
      .then((response) => {
        if (cancelled) return;
        setBoards(response.items);
        setBoardId(response.items[0]?.id ?? "");
        if (response.items.length === 0) setLoading(false);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(formatError(caught));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!boardId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSelectedReport(null);
    setComparisonIds([]);
    setComparison(null);
    Promise.all([getDraftSessions(boardId), getBoardPostDraftReports(boardId)])
      .then(([draftResponse, reportResponse]) => {
        if (cancelled) return;
        setDrafts(draftResponse.items);
        setReports(reportResponse.items);
        setLoading(false);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(formatError(caught));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [boardId]);

  const completedDrafts = useMemo(
    () => drafts.filter((draft) => draft.status === "completed"),
    [drafts],
  );
  const reportByDraft = useMemo(
    () => new Map(reports.map((report) => [report.draft_session_id, report])),
    [reports],
  );

  async function refreshBoard() {
    if (!boardId) return;
    const [draftResponse, reportResponse] = await Promise.all([
      getDraftSessions(boardId),
      getBoardPostDraftReports(boardId),
    ]);
    setDrafts(draftResponse.items);
    setReports(reportResponse.items);
  }

  async function prepareGeneration(
    draftId: string,
    trigger: HTMLButtonElement,
  ) {
    lastTrigger.current = trigger;
    setBusy(true);
    setError(null);
    try {
      const draft = await getDraftSession(draftId);
      if (draft.status !== "completed" || !draft.completed_at) {
        throw new Error("Draft is no longer completed");
      }
      setConfirmDraft(draft);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  function closeConfirmation() {
    setConfirmDraft(null);
    queueMicrotask(() => lastTrigger.current?.focus());
  }

  async function confirmGeneration() {
    if (!confirmDraft?.completed_at) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await generatePostDraftReport(confirmDraft.id, {
        draft_revision: confirmDraft.revision,
        expected_completed_at: confirmDraft.completed_at,
      });
      setSelectedReport(result.report);
      setConfirmDraft(null);
      setNotice(
        result.idempotent
          ? "The existing report was opened; no duplicate was created."
          : "The report was generated and saved locally.",
      );
      try {
        await refreshBoard();
      } catch (refreshError) {
        setError(formatError(refreshError));
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        try {
          const refreshed = await getDraftSession(confirmDraft.id);
          setConfirmDraft(refreshed.completed_at ? refreshed : null);
        } catch {
          setConfirmDraft(null);
        }
      }
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function openReport(reportId: string) {
    setBusy(true);
    setError(null);
    try {
      setSelectedReport(await getPostDraftReport(reportId));
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  function toggleComparison(reportId: string) {
    setComparison(null);
    setComparisonIds((current) =>
      current.includes(reportId)
        ? current.filter((id) => id !== reportId)
        : [...current, reportId],
    );
  }

  async function previewComparison() {
    setBusy(true);
    setError(null);
    try {
      setComparison(await previewPostDraftReportComparison(comparisonIds));
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="reports-workspace" aria-labelledby="reports-heading">
      <header className="workspace-heading reports-heading">
        <div>
          <p className="eyebrow">Phase 6 · local review room</p>
          <h2 id="reports-heading">Reports</h2>
          <p>
            Review the evidence your draft actually saved. Reports describe
            construction and limits; your judgment remains authoritative.
          </p>
        </div>
        {boards.length > 0 && (
          <label>
            Personal Board
            <select value={boardId} onChange={(event) => setBoardId(event.target.value)}>
              {boards.map((board) => (
                <option key={board.id} value={board.id}>{board.name}</option>
              ))}
            </select>
          </label>
        )}
      </header>

      {error && (
        <div className="notice notice-error" role="alert">
          <strong>{error.message}</strong>{error.action && <span>{error.action}</span>}
        </div>
      )}
      {notice && <div className="notice notice-success" role="status">{notice}</div>}

      {loading ? (
        <p role="status">Loading saved local report history…</p>
      ) : boards.length === 0 ? (
        <div className="card"><h3>Create a Personal Board first.</h3></div>
      ) : (
        <>
          <div className="reports-index-grid">
            <section className="report-index-panel" aria-labelledby="eligible-heading">
              <div className="report-subheading">
                <p className="eyebrow">Explicit generation</p>
                <h2 id="eligible-heading">Completed drafts</h2>
              </div>
              {completedDrafts.length === 0 ? (
                <p className="report-muted">No completed drafts are available on this board.</p>
              ) : (
                <ul className="report-index-list">
                  {completedDrafts.map((draft) => {
                    const saved = reportByDraft.get(draft.id);
                    return (
                      <li key={draft.id}>
                        <div>
                          <strong>{draft.name}</strong>
                          <span>
                            {humanize(draft.mode)} · revision {draft.revision} ·{" "}
                            {draft.active_pick_count} picks
                          </span>
                        </div>
                        {saved ? (
                          <button type="button" onClick={() => void openReport(saved.id)}>
                            Open saved report
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={(event) =>
                              void prepareGeneration(draft.id, event.currentTarget)
                            }
                          >
                            Prepare report
                          </button>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            <section className="report-index-panel" aria-labelledby="history-heading">
              <div className="report-subheading">
                <p className="eyebrow">Immutable history</p>
                <h2 id="history-heading">Saved reports</h2>
              </div>
              {reports.length === 0 ? (
                <p className="report-muted">No reports have been generated for this board.</p>
              ) : (
                <ul className="report-index-list">
                  {reports.map((report) => (
                    <li key={report.id}>
                      <div>
                        <strong>{report.draft_name}</strong>
                        <span>
                          {humanize(report.draft_mode)} · {report.completed_at.slice(0, 10)} ·{" "}
                          {humanize(report.draft_format)}
                        </span>
                      </div>
                      <button type="button" onClick={() => void openReport(report.id)}>
                        View report
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          {reports.length >= 2 && (
            <ReportComparison
              reports={reports}
              selectedIds={comparisonIds}
              result={comparison}
              busy={busy}
              onToggle={toggleComparison}
              onPreview={() => void previewComparison()}
            />
          )}
          {selectedReport && <ReportDetail report={selectedReport} />}
        </>
      )}

      {confirmDraft && (
        <div className="report-dialog-backdrop">
          <section
            className="report-confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="report-confirm-heading"
          >
            <p className="eyebrow">Confirm local generation</p>
            <h2 id="report-confirm-heading">Generate report for {confirmDraft.name}?</h2>
            <p>
              The report will freeze completed revision <strong>{confirmDraft.revision}</strong>,
              completed {timestamp(confirmDraft.completed_at)}. It will not modify the draft,
              Personal Board, mock, or alert history.
            </p>
            <div className="report-dialog-actions">
              <button type="button" className="secondary-button" onClick={closeConfirmation}>
                Cancel
              </button>
              <button
                type="button"
                className="primary-button"
                autoFocus
                disabled={busy}
                onClick={() => void confirmGeneration()}
              >
                {busy ? "Generating locally…" : "Generate saved report"}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
