import {
  Fragment,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  ApiError,
  type BoardListResponse,
  type DraftCandidateResponse,
  type DraftSession,
  type DraftSessionCreate,
  type DraftSessionList,
  correctDraftPick,
  createDraftSession,
  getBoards,
  getDraftCandidates,
  getDraftExportUrl,
  getDraftSession,
  getDraftSessions,
  recordDraftPick,
  resetDraftSession,
  undoDraftPick,
  updateDraftSession,
} from "../../api/client";

type BoardSummary = BoardListResponse["items"][number];
type SessionSummary = DraftSessionList["items"][number];
type DraftView = DraftCandidateResponse["view"];
type Candidate = DraftCandidateResponse["items"][number];
type UiError = { message: string; action?: string };

const positions = ["QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN"];
const candidatePageSize = 200;

function formatError(error: unknown): UiError {
  if (error instanceof ApiError) {
    return { message: error.message, action: error.action };
  }
  return {
    message: "The draft room could not complete that action.",
    action: "Refresh the room. Saved picks remain in the local database.",
  };
}

function sessionToSummary(session: DraftSession): SessionSummary {
  const {
    available_count: _available,
    blind_data_hidden: _blind,
    candidate_total: _candidateTotal,
    completed_at: _completedAt,
    current_pick: _currentPick,
    league_profile_id: _leagueProfile,
    pick_timer_seconds: _timer,
    picks: _picks,
    picks_until_user: _distance,
    recommendation_state_present: _recommendation,
    recovery_guidance: _guidance,
    reset_from_session_id: _resetFrom,
    teams: _teams,
    user_on_the_clock: _onClock,
    ...summary
  } = session;
  return summary;
}

function statusLabel(status: DraftSession["status"]): string {
  if (status === "active") return "Live";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function Setup({
  board,
  busy,
  onStart,
}: {
  board: BoardSummary;
  busy: boolean;
  onStart: (payload: DraftSessionCreate) => Promise<void>;
}) {
  const [name, setName] = useState(`${board.name} Draft`);
  const [mode, setMode] = useState<DraftSessionCreate["mode"]>("live");
  const [draftFormat, setDraftFormat] =
    useState<DraftSessionCreate["draft_format"]>("snake");
  const [thirdRoundReversal, setThirdRoundReversal] = useState(false);
  const [teamCount, setTeamCount] = useState(10);
  const [roundCount, setRoundCount] = useState(24);
  const [userSlot, setUserSlot] = useState(1);
  const [timer, setTimer] = useState(120);
  const [teamNames, setTeamNames] = useState(() =>
    Array.from({ length: 10 }, (_, index) => `Team ${index + 1}`),
  );

  function changeTeamCount(nextCount: number) {
    const boundedCount = Math.max(2, Math.min(32, nextCount || 2));
    setTeamCount(boundedCount);
    setUserSlot((current) => Math.min(current, boundedCount));
    setTeamNames((current) =>
      Array.from(
        { length: boundedCount },
        (_, index) => current[index] ?? `Team ${index + 1}`,
      ),
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onStart({
      name,
      mode,
      draft_format: draftFormat,
      third_round_reversal:
        draftFormat === "snake" && thirdRoundReversal,
      team_count: teamCount,
      round_count: roundCount,
      user_slot: Math.min(userSlot, teamCount),
      pick_timer_seconds: timer,
      team_names: teamNames.map(
        (teamName, index) => teamName.trim() || `Team ${index + 1}`,
      ),
    });
  }

  return (
    <form className="draft-setup" onSubmit={submit}>
      <div className="draft-setup-heading">
        <div>
          <p className="eyebrow">New draft session</p>
          <h3>Freeze the board, order, and room configuration.</h3>
        </div>
        <span>{board.entry_count} personally ranked</span>
      </div>
      <div className="draft-setup-grid">
        <label className="draft-name-field">
          Session name
          <input
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          Mode
          <select
            value={mode}
            onChange={(event) =>
              setMode(event.target.value as DraftSessionCreate["mode"])
            }
          >
            <option value="live">Live room</option>
            <option value="mock">Mock draft</option>
          </select>
        </label>
        <label>
          Format
          <select
            value={draftFormat}
            onChange={(event) => {
              const value = event.target
                .value as DraftSessionCreate["draft_format"];
              setDraftFormat(value);
              if (value === "linear") setThirdRoundReversal(false);
            }}
          >
            <option value="snake">Snake</option>
            <option value="linear">Linear</option>
          </select>
        </label>
        <label>
          Teams
          <input
            type="number"
            min="2"
            max="32"
            value={teamCount}
            onChange={(event) => changeTeamCount(Number(event.target.value))}
          />
        </label>
        <label>
          Rounds
          <input
            type="number"
            min="1"
            max="60"
            value={roundCount}
            onChange={(event) => setRoundCount(Number(event.target.value))}
          />
        </label>
        <label>
          Your slot
          <input
            type="number"
            min="1"
            max={teamCount}
            value={userSlot}
            onChange={(event) => setUserSlot(Number(event.target.value))}
          />
        </label>
        <label>
          Display timer
          <input
            type="number"
            min="1"
            max="86400"
            value={timer}
            onChange={(event) => setTimer(Number(event.target.value))}
          />
        </label>
        <label className="draft-reversal-field">
          <input
            type="checkbox"
            checked={thirdRoundReversal}
            disabled={draftFormat !== "snake"}
            onChange={(event) => setThirdRoundReversal(event.target.checked)}
          />
          Third-round reversal
          <small>Rounds two and three both run backward.</small>
          </label>
      </div>
      <details className="draft-team-name-editor">
        <summary>Customize team names</summary>
        <div className="draft-team-name-grid">
          {teamNames.map((teamName, index) => (
            <label key={index}>
              Team {index + 1} name
              <input
                required
                maxLength={100}
                value={teamName}
                onChange={(event) =>
                  setTeamNames((current) =>
                    current.map((value, teamIndex) =>
                      teamIndex === index ? event.target.value : value,
                    ),
                  )
                }
              />
              {userSlot === index + 1 && <small>Your draft slot</small>}
            </label>
          ))}
        </div>
      </details>
      <div className="draft-setup-footer">
        <p>
          Team names default to their draft slots. No provider draft identifiers
          are stored.
        </p>
        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? "Opening room..." : "Create draft room"}
        </button>
      </div>
    </form>
  );
}

function CandidateRow({
  candidate,
  canSelect,
  correction,
  pending,
  busy,
  rowRef,
  onFocus,
  onRequestSelect,
  onConfirm,
  onCancel,
}: {
  candidate: Candidate;
  canSelect: boolean;
  correction: boolean;
  pending: boolean;
  busy: boolean;
  rowRef: (node: HTMLTableRowElement | null) => void;
  onFocus: () => void;
  onRequestSelect: () => void;
  onConfirm: () => Promise<void>;
  onCancel: () => void;
}) {
  const contextual = "personal_rank" in candidate ? candidate : null;
  const drafted = candidate.drafted_overall_pick !== null;
  return (
    <Fragment>
      <tr
        ref={rowRef}
        className={drafted ? "is-drafted" : pending ? "is-pending" : undefined}
        data-player-id={candidate.player_id}
        tabIndex={drafted ? -1 : 0}
        onFocus={onFocus}
      >
        {contextual && (
          <td className="draft-rank-cell">
            {contextual.personal_rank ? `#${contextual.personal_rank}` : "—"}
          </td>
        )}
        <th scope="row">
          <strong>{candidate.display_name}</strong>
          <span>
            {candidate.team ?? "FA"} · {candidate.player_status}
            {candidate.is_rookie ? " · Rookie" : ""}
          </span>
        </th>
        <td>
          <span className="position-chip">{candidate.primary_position}</span>
        </td>
        {contextual && (
          <td className="draft-context-cell">
            {contextual.tier_name ?? "Unranked"}
          </td>
        )}
        <td>
          {drafted ? (
            <span className="drafted-label">
              Pick {candidate.drafted_overall_pick}
            </span>
          ) : (
            <button
              className={correction ? "secondary-button" : "primary-button"}
              type="button"
              disabled={!canSelect || busy}
              onClick={onRequestSelect}
            >
              {correction ? "Use correction" : "Draft"}
            </button>
          )}
        </td>
      </tr>
      {pending && (
        <tr className="draft-confirmation-row">
          <td colSpan={contextual ? 5 : 3}>
            <span>
              {correction ? "Confirm correction to" : "Confirm pick:"}{" "}
              <strong>{candidate.display_name}</strong>
            </span>
            <div>
              <button
                className="quiet-button"
                type="button"
                disabled={busy}
                onClick={onCancel}
              >
                Cancel
              </button>
              <button
                className="primary-button"
                type="button"
                disabled={busy}
                onClick={() => void onConfirm()}
              >
                {correction ? "Confirm correction" : "Confirm pick"}
              </button>
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  );
}

export function DraftWorkspace() {
  const [boards, setBoards] = useState<BoardSummary[]>([]);
  const [boardId, setBoardId] = useState("");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [draft, setDraft] = useState<DraftSession | null>(null);
  const [candidates, setCandidates] =
    useState<DraftCandidateResponse | null>(null);
  const [view, setView] = useState<DraftView>("blind");
  const [search, setSearch] = useState("");
  const [position, setPosition] = useState("QB");
  const [includeDrafted, setIncludeDrafted] = useState(false);
  const [candidateOffset, setCandidateOffset] = useState(0);
  const [focusedCandidateId, setFocusedCandidateId] = useState<string | null>(
    null,
  );
  const [pendingCandidateId, setPendingCandidateId] = useState<string | null>(
    null,
  );
  const [correctingPick, setCorrectingPick] = useState<number | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<UiError | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const candidateRowRefs = useRef(
    new Map<string, HTMLTableRowElement>(),
  );

  const selectedBoard = boards.find((board) => board.id === boardId);
  const correctionTarget = draft?.picks.find(
    (pick) => pick.overall_pick === correctingPick,
  );

  async function loadSession(sessionId: string) {
    const loaded = await getDraftSession(sessionId);
    setDraft(loaded);
    setCandidateOffset(0);
    setFocusedCandidateId(null);
    setCorrectingPick(null);
    setPendingCandidateId(null);
    setConfirmReset(false);
  }

  async function openSession(sessionId: string) {
    setError(null);
    try {
      await loadSession(sessionId);
    } catch (caught) {
      setError(formatError(caught));
    }
  }

  async function refreshSessionAfterError(sessionId: string) {
    try {
      setDraft(await getDraftSession(sessionId));
      setCorrectingPick(null);
      setPendingCandidateId(null);
    } catch {
      // The original actionable error remains the useful message.
    }
  }

  async function loadBoardSessions(nextBoardId: string) {
    setLoading(true);
    setError(null);
    setNotice(null);
    setDraft(null);
    setCandidates(null);
    try {
      const result = await getDraftSessions(nextBoardId);
      setSessions(result.items);
      if (result.items[0]) await loadSession(result.items[0].id);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    getBoards()
      .then(async (result) => {
        if (cancelled) return;
        setBoards(result.items);
        const first = result.items[0];
        if (first) {
          setBoardId(first.id);
          await loadBoardSessions(first.id);
        } else {
          setLoading(false);
        }
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
    if (!draft) return;
    let cancelled = false;
    getDraftCandidates(draft.id, {
      view,
      search,
      positions: view === "position" ? [position] : [],
      includeDrafted,
      limit: candidatePageSize,
      offset: candidateOffset,
    })
      .then((result) => {
        if (!cancelled) setCandidates(result);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(formatError(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [
    candidateOffset,
    draft?.id,
    draft?.revision,
    includeDrafted,
    position,
    search,
    view,
  ]);

  async function runMutation(
    mutation: () => Promise<DraftSession>,
    successMessage: string,
  ) {
    if (!draft) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await mutation();
      setDraft(updated);
      setSessions((current) => [
        sessionToSummary(updated),
        ...current.filter((item) => item.id !== updated.id),
      ]);
      setNotice(successMessage);
      setCorrectingPick(null);
      setPendingCandidateId(null);
    } catch (caught) {
      setError(formatError(caught));
      await refreshSessionAfterError(draft.id);
    } finally {
      setBusy(false);
    }
  }

  async function startSession(payload: DraftSessionCreate) {
    if (!boardId) return;
    setBusy(true);
    setError(null);
    try {
      const created = await createDraftSession(boardId, payload);
      setDraft(created);
      setSessions((current) => [
        sessionToSummary(created),
        ...current.filter((item) => item.id !== created.id),
      ]);
      setNotice("Draft room created. Pick one is ready.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function selectCandidate(playerId: string) {
    if (!draft) return;
    if (correctionTarget) {
      await runMutation(
        () =>
          correctDraftPick(draft.id, correctionTarget.overall_pick, {
            revision: draft.revision,
            expected_current_player_id: correctionTarget.player_id,
            replacement_player_id: playerId,
          }),
        `Pick ${correctionTarget.overall_pick} corrected and saved.`,
      );
      return;
    }
    if (!draft.current_pick) return;
    await runMutation(
      () =>
        recordDraftPick(draft.id, {
          revision: draft.revision,
          expected_overall_pick: draft.current_pick!.overall_pick,
          player_id: playerId,
          client_entered_at: new Date().toISOString(),
        }),
      "Pick saved to the local draft record.",
    );
  }

  async function resetRoom() {
    if (!draft) return;
    const previousSession = draft;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const replacement = await resetDraftSession(draft.id, {
        revision: draft.revision,
      });
      setDraft(replacement);
      setSessions((current) => [
        sessionToSummary(replacement),
        ...current
          .filter((item) => item.id !== replacement.id)
          .map((item) =>
            item.id === previousSession.id
              ? {
                  ...item,
                  status: "reset" as const,
                  revision: previousSession.revision + 1,
                  updated_at: replacement.created_at,
                }
              : item,
          ),
      ]);
      setConfirmReset(false);
      setCorrectingPick(null);
      setPendingCandidateId(null);
      setNotice("Clean replacement room created; old session preserved.");
    } catch (caught) {
      setError(formatError(caught));
      await refreshSessionAfterError(previousSession.id);
    } finally {
      setBusy(false);
    }
  }

  const candidateItems = candidates?.items ?? [];
  const viewCount = candidates?.total ?? 0;
  const candidatePageEnd = Math.min(
    candidateOffset + candidateItems.length,
    viewCount,
  );

  function changeCandidateView(nextView: DraftView) {
    setView(nextView);
    setCandidateOffset(0);
    setPendingCandidateId(null);
    setFocusedCandidateId(null);
  }

  function moveCandidateFocus(direction: -1 | 1) {
    const selectableCandidates = candidateItems.filter(
      (candidate) => candidate.drafted_overall_pick === null,
    );
    if (selectableCandidates.length === 0) return;
    const currentIndex = selectableCandidates.findIndex(
      (candidate) => candidate.player_id === focusedCandidateId,
    );
    const nextIndex =
      currentIndex < 0
        ? direction > 0
          ? 0
          : selectableCandidates.length - 1
        : Math.max(
            0,
            Math.min(selectableCandidates.length - 1, currentIndex + direction),
          );
    const nextCandidate = selectableCandidates[nextIndex];
    setFocusedCandidateId(nextCandidate.player_id);
    candidateRowRefs.current.get(nextCandidate.player_id)?.focus();
  }

  function handleCandidateKeyDown(
    event: ReactKeyboardEvent<HTMLTableElement>,
  ) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      moveCandidateFocus(event.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (event.key === "Enter") {
      const eventCandidateId =
        (event.target as HTMLElement).closest<HTMLTableRowElement>(
          "tr[data-player-id]",
        )?.dataset.playerId ?? focusedCandidateId;
      if (!eventCandidateId) return;
      const candidate = candidateItems.find(
        (item) => item.player_id === eventCandidateId,
      );
      if (
        candidate?.drafted_overall_pick === null &&
        (Boolean(correctionTarget) || draft?.status === "active")
      ) {
        event.preventDefault();
        setPendingCandidateId(eventCandidateId);
      }
      return;
    }
    if (event.key === "Escape") {
      setPendingCandidateId(null);
    }
  }

  useEffect(() => {
    function handleWorkspaceShortcut(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const isFormField =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        target?.isContentEditable;
      if (event.key === "/" && !isFormField) {
        event.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (
        event.key.toLowerCase() === "u" &&
        !isFormField &&
        draft &&
        draft.active_pick_count > 0 &&
        !busy
      ) {
        event.preventDefault();
        void runMutation(
          () => undoDraftPick(draft.id, { revision: draft.revision }),
          "Latest pick undone. The player is available again.",
        );
      }
    }
    window.addEventListener("keydown", handleWorkspaceShortcut);
    return () => window.removeEventListener("keydown", handleWorkspaceShortcut);
  }, [busy, draft]);

  const statusCopy = useMemo(() => {
    if (!draft) return "";
    if (draft.status === "completed") return "Final pick recorded";
    if (draft.status === "reset") return "Audit-only reset session";
    if (draft.status === "paused") return "Current pick preserved";
    if (draft.user_on_the_clock) return "You are on the clock";
    return draft.picks_until_user === null
      ? "No future user pick"
      : `${draft.picks_until_user} picks until you`;
  }, [draft]);

  return (
    <section className="draft-workspace">
      <div className="draft-workspace-heading">
        <div>
          <p className="eyebrow">Phase 3 · Draft room</p>
          <h2>Run the room without surrendering the board.</h2>
          <p>
            Every click is revision-guarded, saved immediately, and recoverable
            after restart. Blind mode removes personal context at the API.
          </p>
        </div>
        <span className="privacy-pill">Local scorebook</span>
      </div>

      <div className="workspace-messages">
        {error && (
          <div className="notice notice-error" role="alert">
            <strong>{error.message}</strong>
            {error.action && <span>{error.action}</span>}
          </div>
        )}
        {notice && (
          <div className="notice notice-success" role="status">
            {notice}
          </div>
        )}
      </div>

      <div className="draft-board-bar">
        <label>
          Personal Board
          <select
            value={boardId}
            disabled={loading || boards.length === 0}
            onChange={(event) => {
              setBoardId(event.target.value);
              setPendingCandidateId(null);
              void loadBoardSessions(event.target.value);
            }}
          >
            {boards.length === 0 && <option value="">No boards available</option>}
            {boards.map((board) => (
              <option key={board.id} value={board.id}>
                {board.name}
              </option>
            ))}
          </select>
        </label>
        <div>
          <strong>{sessions.length}</strong>
          <span>saved sessions</span>
        </div>
        <button
          className="quiet-button"
          type="button"
          disabled={!selectedBoard}
          onClick={() => {
            setDraft(null);
            setCandidates(null);
            setNotice(null);
            setPendingCandidateId(null);
          }}
        >
          New room
        </button>
      </div>

      {!loading && boards.length === 0 && (
        <div className="draft-empty">
          <strong>A Personal Board is the call sheet for this room.</strong>
          <p>Create a board and add at least two relevant players first.</p>
        </div>
      )}

      {sessions.length > 0 && (
        <div className="draft-session-tabs" aria-label="Saved draft sessions">
          {sessions.map((item) => (
            <button
              type="button"
              key={item.id}
              aria-current={item.id === draft?.id ? "page" : undefined}
              onClick={() => void openSession(item.id)}
            >
              <strong>{item.name}</strong>
              <span>
                {statusLabel(item.status)} · {item.active_pick_count}/
                {item.total_picks}
              </span>
            </button>
          ))}
        </div>
      )}

      {selectedBoard && !draft && (
        <Setup
          key={selectedBoard.id}
          board={selectedBoard}
          busy={busy}
          onStart={startSession}
        />
      )}

      {draft && (
        <>
          <div className="draft-live-strip">
            <div>
              <span className={`draft-status draft-status-${draft.status}`}>
                {statusLabel(draft.status)}
              </span>
              <strong>{draft.name}</strong>
              <small>
                {draft.mode.toUpperCase()} · {draft.draft_format.toUpperCase()}
                {draft.third_round_reversal ? " · 3RR" : ""}
                {" · "}Saved locally
              </small>
            </div>
            <div className="draft-clock-block">
              <span>Current pick</span>
              <strong>
                {draft.current_pick
                  ? `${draft.current_pick.round_number}.${draft.current_pick.pick_in_round
                      .toString()
                      .padStart(2, "0")}`
                  : "—"}
              </strong>
              <small>{draft.current_pick?.selecting_team ?? "Room closed"}</small>
            </div>
            <div className={draft.user_on_the_clock ? "is-user-clock" : ""}>
              <span>Draft distance</span>
              <strong>{statusCopy}</strong>
              <small>Revision {draft.revision}</small>
            </div>
            <div className="draft-session-actions">
              {draft.status === "active" && (
                <button
                  className="secondary-button"
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void runMutation(
                      () =>
                        updateDraftSession(draft.id, {
                          revision: draft.revision,
                          status: "paused",
                        }),
                      "Draft paused at the same current pick.",
                    )
                  }
                >
                  Pause
                </button>
              )}
              {draft.status === "paused" && (
                <button
                  className="primary-button"
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void runMutation(
                      () =>
                        updateDraftSession(draft.id, {
                          revision: draft.revision,
                          status: "active",
                        }),
                      "Draft resumed from the preserved pick.",
                    )
                  }
                >
                  Resume
                </button>
              )}
              <button
                className="quiet-button"
                type="button"
                disabled={busy || draft.active_pick_count === 0}
                onClick={() =>
                  void runMutation(
                    () =>
                      undoDraftPick(draft.id, { revision: draft.revision }),
                    "Latest pick undone. The player is available again.",
                  )
                }
              >
                Undo latest
              </button>
              <a
                className="quiet-link"
                href={getDraftExportUrl(draft.id)}
                download
              >
                Export CSV
              </a>
            </div>
          </div>

          <div className="draft-operating-grid">
            <section className="draft-candidate-panel">
              <div className="draft-candidate-toolbar">
                <div className="draft-view-tabs">
                  {(["blind", "personal", "position", "tier"] as const).map(
                    (value) => (
                      <button
                        type="button"
                        key={value}
                        aria-current={view === value ? "page" : undefined}
                        onClick={() => changeCandidateView(value)}
                      >
                        {value}
                      </button>
                    ),
                  )}
                </div>
                <label>
                  <span className="visually-hidden">Search candidates</span>
                  <input
                    ref={searchRef}
                    type="search"
                    placeholder="Search candidates"
                    value={search}
                    onChange={(event) => {
                      setSearch(event.target.value);
                      setCandidateOffset(0);
                      setPendingCandidateId(null);
                    }}
                  />
                </label>
                {view === "position" && (
                  <select
                    aria-label="Candidate position"
                    value={position}
                    onChange={(event) => {
                      setPosition(event.target.value);
                      setCandidateOffset(0);
                      setPendingCandidateId(null);
                    }}
                  >
                    {positions.map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                  </select>
                )}
                <label className="draft-audit-toggle">
                  <input
                    type="checkbox"
                    checked={includeDrafted}
                    onChange={(event) => {
                      setIncludeDrafted(event.target.checked);
                      setCandidateOffset(0);
                      setPendingCandidateId(null);
                    }}
                  />
                  Show drafted
                </label>
                <span className="draft-shortcuts" aria-label="Keyboard shortcuts">
                  <kbd>/</kbd> Search <kbd>↑↓</kbd> Move <kbd>Enter</kbd> Select{" "}
                  <kbd>U</kbd> Undo
                </span>
              </div>
              <div className="draft-candidate-heading">
                <div>
                  <p className="eyebrow">
                    {view === "blind" ? "Context removed" : "Board context"}
                  </p>
                  <h3>{viewCount} candidates in this view</h3>
                </div>
                {correctionTarget && (
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={() => {
                      setCorrectingPick(null);
                      setPendingCandidateId(null);
                    }}
                  >
                    Cancel correction
                  </button>
                )}
              </div>
              {correctionTarget && (
                <div className="draft-correction-banner" role="status">
                  Replacing pick {correctionTarget.overall_pick}:{" "}
                  <strong>{correctionTarget.player_display_name}</strong>
                </div>
              )}
              <div className="draft-candidate-table-wrap">
                <table
                  className="draft-candidate-table"
                  onKeyDown={handleCandidateKeyDown}
                >
                  <thead>
                    <tr>
                      {view !== "blind" && <th>Personal</th>}
                      <th>Player</th>
                      <th>Pos</th>
                      {view !== "blind" && <th>Tier</th>}
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidateItems.map((candidate) => (
                      <CandidateRow
                        key={candidate.player_id}
                        candidate={candidate}
                        correction={Boolean(correctionTarget)}
                        pending={candidate.player_id === pendingCandidateId}
                        canSelect={
                          Boolean(correctionTarget) || draft.status === "active"
                        }
                        busy={busy}
                        rowRef={(node) => {
                          if (node) {
                            candidateRowRefs.current.set(candidate.player_id, node);
                          } else {
                            candidateRowRefs.current.delete(candidate.player_id);
                          }
                        }}
                        onFocus={() =>
                          setFocusedCandidateId(candidate.player_id)
                        }
                        onRequestSelect={() =>
                          setPendingCandidateId(candidate.player_id)
                        }
                        onConfirm={() => selectCandidate(candidate.player_id)}
                        onCancel={() => setPendingCandidateId(null)}
                      />
                    ))}
                  </tbody>
                </table>
                {candidateItems.length === 0 && (
                  <div className="draft-empty">No candidates match this view.</div>
                )}
              </div>
              {viewCount > candidatePageSize && (
                <div className="draft-pagination">
                  <span>
                    Showing {candidateOffset + 1}–{candidatePageEnd} of{" "}
                    {viewCount}
                  </span>
                  <div>
                    <button
                      className="quiet-button"
                      type="button"
                      disabled={candidateOffset === 0}
                      onClick={() => {
                        setCandidateOffset((current) =>
                          Math.max(0, current - candidatePageSize),
                        );
                        setPendingCandidateId(null);
                      }}
                    >
                      Previous
                    </button>
                    <button
                      className="quiet-button"
                      type="button"
                      disabled={candidatePageEnd >= viewCount}
                      onClick={() => {
                        setCandidateOffset(
                          (current) => current + candidatePageSize,
                        );
                        setPendingCandidateId(null);
                      }}
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </section>

            <aside className="draft-room-panel">
              <p className="eyebrow">Room board</p>
              <h3>
                {draft.current_pick
                  ? `${draft.current_pick.selecting_team} selects`
                  : statusLabel(draft.status)}
              </h3>
              <div className="draft-room-metrics">
                <div>
                  <strong>{draft.active_pick_count}</strong>
                  <span>Recorded</span>
                </div>
                <div>
                  <strong>{draft.available_count}</strong>
                  <span>Available</span>
                </div>
                <div>
                  <strong>{draft.total_picks}</strong>
                  <span>Capacity</span>
                </div>
              </div>
              <ol className="draft-team-order">
                {draft.teams.map((team) => (
                  <li
                    key={team.draft_slot}
                    className={
                      draft.current_pick?.selecting_slot === team.draft_slot
                        ? "is-selecting"
                        : team.is_user
                          ? "is-user"
                          : undefined
                    }
                  >
                    <span>{team.draft_slot}</span>
                    <strong>{team.display_name}</strong>
                    {team.is_user && <small>You</small>}
                  </li>
                ))}
              </ol>
              {draft.recovery_guidance && (
                <p className="draft-recovery">{draft.recovery_guidance}</p>
              )}
              <div className="draft-reset-control">
                {!confirmReset ? (
                  <button
                    className="text-button"
                    type="button"
                    disabled={busy || draft.status === "reset"}
                    onClick={() => setConfirmReset(true)}
                  >
                    Reset room
                  </button>
                ) : (
                  <>
                    <p>Keep this session for audit and open a clean replacement?</p>
                    <div>
                      <button
                        className="quiet-button"
                        type="button"
                        onClick={() => setConfirmReset(false)}
                      >
                        Cancel
                      </button>
                      <button
                        className="secondary-button"
                        type="button"
                        disabled={busy}
                        onClick={() => void resetRoom()}
                      >
                        Confirm reset
                      </button>
                    </div>
                  </>
                )}
              </div>
            </aside>

            <aside className="draft-pick-rail">
              <div>
                <p className="eyebrow">Pick rail</p>
                <h3>Latest selections</h3>
              </div>
              {draft.current_pick && (
                <div className="draft-current-marker">
                  <span>On the clock</span>
                  <strong>
                    {draft.current_pick.overall_pick}.{" "}
                    {draft.current_pick.selecting_team}
                  </strong>
                </div>
              )}
              <ol>
                {draft.picks.map((pick) => (
                  <li key={pick.overall_pick}>
                    <span>{pick.overall_pick}</span>
                    <div>
                      <strong>{pick.player_display_name}</strong>
                      <small>
                        {pick.player_position} · {pick.player_team ?? "FA"} ·{" "}
                        {pick.selecting_team}
                      </small>
                    </div>
                    <button
                      className="text-button"
                      type="button"
                      disabled={busy || draft.status === "reset"}
                      onClick={() => {
                        setCorrectingPick(pick.overall_pick);
                        setPendingCandidateId(null);
                      }}
                    >
                      Correct
                    </button>
                  </li>
                ))}
              </ol>
              {draft.picks.length === 0 && (
                <p className="draft-rail-empty">
                  Picks appear here immediately after the server confirms them.
                </p>
              )}
            </aside>
          </div>
        </>
      )}
    </section>
  );
}
