import {
  type FormEvent,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  ApiError,
  type Board,
  type BoardListResponse,
  type GutEloActionCreate,
  type GutEloSession,
  type GutEloSessionCreate,
  type GutEloSessionList,
  createGutEloSession,
  getBoard,
  getBoards,
  getGutEloSession,
  getGutEloSessions,
  recordGutEloAction,
  undoGutEloAction,
  updateGutEloSession,
} from "../../api/client";

type BoardSummary = BoardListResponse["items"][number];
type SessionSummary = GutEloSessionList["items"][number];
type QueueMode = GutEloSessionCreate["queue_mode"];
type Outcome = GutEloActionCreate["outcome"];
type UiError = { message: string; action?: string };

const positions = ["QB", "RB", "WR", "TE", "K", "DEF", "UNKNOWN"] as const;

function formatError(error: unknown): UiError {
  if (error instanceof ApiError) {
    return { message: error.message, action: error.action };
  }
  return {
    message: "The Gut ELO room could not complete that action.",
    action: "Try again. Your Personal Board and saved choices are unchanged.",
  };
}

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function queueLabel(
  queueMode: QueueMode,
  position: string | null,
  tierName: string | null,
): string {
  if (queueMode === "position") return `${position ?? "Position"} queue`;
  if (queueMode === "tier") return `${tierName ?? "Tier"} queue`;
  if (queueMode === "uncertainty") return "Uncertainty review";
  return "Full board";
}

function sessionToSummary(session: GutEloSession): SessionSummary {
  const {
    actions: _actions,
    manual_board_unchanged: _manualBoardUnchanged,
    next_pair: _nextPair,
    participants: _participants,
    progress: _progress,
    revision: _revision,
    ...summary
  } = session;
  return summary;
}

function SessionSetup({
  board,
  busy,
  onStart,
}: {
  board: Board;
  busy: boolean;
  onStart: (payload: GutEloSessionCreate) => Promise<void>;
}) {
  const [queueMode, setQueueMode] = useState<QueueMode>("board");
  const [position, setPosition] =
    useState<GutEloSessionCreate["position"]>("QB");
  const [tierId, setTierId] = useState(board.tiers[0]?.id ?? "");
  const [targetCount, setTargetCount] = useState("");

  const eligibleCount = useMemo(() => {
    if (queueMode === "position") {
      return board.entries.filter(
        (entry) => entry.player.primary_position === position,
      ).length;
    }
    if (queueMode === "tier") {
      return board.entries.filter((entry) => entry.tier_id === tierId).length;
    }
    return board.entries.length;
  }, [board.entries, position, queueMode, tierId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onStart({
      queue_mode: queueMode,
      position: queueMode === "position" ? position : null,
      tier_id: queueMode === "tier" ? tierId : null,
      target_count: targetCount ? Number(targetCount) : null,
    });
  }

  return (
    <div className="gut-setup">
      <div className="gut-setup-intro">
        <p className="eyebrow">New comparison run</p>
        <h3>Set the question, then trust the first reaction.</h3>
        <p>
          Each session freezes its participant list. Your choices produce a
          separate preference signal and never move the Personal Board.
        </p>
      </div>

      <form className="gut-setup-form" onSubmit={submit}>
        <fieldset>
          <legend>Who should enter this session?</legend>
          <div className="gut-queue-grid">
            {(
              [
                ["board", "Full board", "A broad read across every active player."],
                ["position", "One position", "Resolve a specific position room."],
                ["tier", "One tier", "Stress-test a close manual tier."],
                [
                  "uncertainty",
                  "Uncertainty",
                  "Prioritize players with the least decisive evidence.",
                ],
              ] as const
            ).map(([value, label, description]) => (
              <label
                className={
                  queueMode === value
                    ? "gut-queue-option is-selected"
                    : "gut-queue-option"
                }
                key={value}
              >
                <input
                  type="radio"
                  name="queue-mode"
                  value={value}
                  checked={queueMode === value}
                  onChange={() => setQueueMode(value)}
                />
                <strong>{label}</strong>
                <span>{description}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="gut-setup-fields">
          {queueMode === "position" && (
            <label>
              Position
              <select
                value={position ?? "QB"}
                onChange={(event) =>
                  setPosition(
                    event.target.value as GutEloSessionCreate["position"],
                  )
                }
              >
                {positions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
          )}
          {queueMode === "tier" && (
            <label>
              Personal Board tier
              <select
                required
                value={tierId}
                onChange={(event) => setTierId(event.target.value)}
              >
                {board.tiers.length === 0 && (
                  <option value="">No tiers available</option>
                )}
                {board.tiers.map((tier) => (
                  <option key={tier.id} value={tier.id}>
                    {tier.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Resolved comparison target
            <input
              type="number"
              min="1"
              max="40"
              value={targetCount}
              placeholder="Automatic bounded target"
              onChange={(event) => setTargetCount(event.target.value)}
            />
          </label>
          <div className="gut-eligible-count" aria-live="polite">
            <strong>{eligibleCount}</strong>
            <span>eligible players</span>
          </div>
        </div>

        {eligibleCount < 2 && (
          <p className="gut-setup-warning" role="alert">
            This queue needs at least two players. Add eligible players to the
            Personal Board or choose a broader queue.
          </p>
        )}

        <div className="gut-setup-submit">
          <p>
            Automatic targets stop the session once it has a useful bounded
            sample. You can pause or undo at any time.
          </p>
          <button
            className="primary-button"
            type="submit"
            disabled={busy || eligibleCount < 2}
          >
            {busy ? "Opening session..." : "Start Gut ELO session"}
          </button>
        </div>
      </form>
    </div>
  );
}

function PlayerChoiceCard({
  player,
  side,
  disabled,
  onChoose,
}: {
  player: NonNullable<GutEloSession["next_pair"]>["player_a"];
  side: "left" | "right";
  disabled: boolean;
  onChoose: () => void;
}) {
  return (
    <button
      className={`gut-player-choice gut-player-choice-${side}`}
      type="button"
      disabled={disabled}
      aria-label={`Choose ${player.display_name}`}
      onClick={onChoose}
    >
      <span className="gut-choice-key" aria-hidden="true">
        {side === "left" ? "1" : "2"}
      </span>
      <span className="position-chip">{player.primary_position}</span>
      <strong>{player.display_name}</strong>
      <span className="gut-player-meta">
        {player.team ?? "FA"} / {titleCase(player.status)}
        {player.is_rookie ? " / Rookie" : ""}
      </span>
      <span className="gut-choice-call">Take {player.first_name}</span>
    </button>
  );
}

function SessionResults({ session }: { session: GutEloSession }) {
  return (
    <section className="gut-results" aria-labelledby="gut-results-title">
      <div className="gut-results-heading">
        <div>
          <p className="eyebrow">Separate preference signal</p>
          <h3 id="gut-results-title">Gut order vs. manual order</h3>
        </div>
        <span>Personal Board unchanged</span>
      </div>
      <div className="player-table-wrap">
        <table className="player-table gut-results-table">
          <thead>
            <tr>
              <th scope="col">Gut</th>
              <th scope="col">Player</th>
              <th scope="col">Rating</th>
              <th scope="col">Manual start</th>
              <th scope="col">Movement</th>
              <th scope="col">Decisions</th>
            </tr>
          </thead>
          <tbody>
            {session.participants.map((participant) => {
              const movement =
                participant.starting_manual_rank - participant.gut_rank;
              return (
                <tr key={participant.player.id}>
                  <th scope="row" data-label="Gut rank">
                    #{participant.gut_rank}
                  </th>
                  <td data-label="Player">
                    <strong className="player-name">
                      {participant.player.display_name}
                    </strong>
                    <span className="muted-copy">
                      {participant.player.primary_position} /{" "}
                      {participant.player.team ?? "FA"}
                      {participant.starting_tier_name
                        ? ` / ${participant.starting_tier_name}`
                        : ""}
                    </span>
                  </td>
                  <td data-label="Rating">
                    {participant.rating.toFixed(1)}
                  </td>
                  <td data-label="Manual start">
                    #{participant.starting_manual_rank}
                  </td>
                  <td data-label="Movement">
                    <span
                      className={
                        movement > 0
                          ? "gut-movement gut-movement-up"
                          : movement < 0
                            ? "gut-movement gut-movement-down"
                            : "gut-movement"
                      }
                    >
                      {movement > 0
                        ? `Up ${movement}`
                        : movement < 0
                          ? `Down ${Math.abs(movement)}`
                          : "Even"}
                    </span>
                  </td>
                  <td data-label="Decisions">
                    {participant.decisive_count}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function GutEloWorkspace() {
  const [boards, setBoards] = useState<BoardSummary[]>([]);
  const [selectedBoardId, setSelectedBoardId] = useState<string | null>(null);
  const [board, setBoard] = useState<Board | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [session, setSession] = useState<GutEloSession | null>(null);
  const [setupMode, setSetupMode] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<UiError | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    getBoards(false)
      .then((response) => {
        if (!active) return;
        setBoards(response.items);
        setSelectedBoardId(response.items[0]?.id ?? null);
        if (response.items.length === 0) setSetupMode(true);
      })
      .catch((caught: unknown) => {
        if (active) setError(formatError(caught));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedBoardId) {
      setBoard(null);
      setSessions([]);
      setSession(null);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    setBoard(null);
    setSessions([]);
    setSession(null);
    setSetupMode(false);
    Promise.all([
      getBoard(selectedBoardId),
      getGutEloSessions(selectedBoardId),
    ])
      .then(async ([boardResponse, sessionResponse]) => {
        if (!active) return;
        setBoard(boardResponse);
        setSessions(sessionResponse.items);
        const newest = sessionResponse.items[0];
        if (!newest) {
          setSession(null);
          setSetupMode(true);
          return;
        }
        const fullSession = await getGutEloSession(newest.id);
        if (!active) return;
        setSession(fullSession);
        setSetupMode(false);
      })
      .catch((caught: unknown) => {
        if (active) setError(formatError(caught));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedBoardId]);

  function clearMessages() {
    setNotice(null);
    setError(null);
  }

  function acceptSession(updated: GutEloSession) {
    setSession(updated);
    setSessions((current) => {
      const summary = sessionToSummary(updated);
      const remaining = current.filter((item) => item.id !== updated.id);
      return [summary, ...remaining].sort((left, right) =>
        right.updated_at.localeCompare(left.updated_at),
      );
    });
  }

  async function startSession(payload: GutEloSessionCreate) {
    if (!board) return;
    clearMessages();
    setBusyAction("start");
    try {
      const created = await createGutEloSession(board.id, payload);
      acceptSession(created);
      setSetupMode(false);
      setNotice("Gut ELO session started. The Personal Board is unchanged.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  async function openSession(sessionId: string) {
    clearMessages();
    setBusyAction("open");
    try {
      setSession(await getGutEloSession(sessionId));
      setSetupMode(false);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  async function recordOutcome(outcome: Outcome) {
    if (!session?.next_pair || busyAction) return;
    clearMessages();
    setBusyAction("choice");
    try {
      const updated = await recordGutEloAction(session.id, {
        revision: session.next_pair.revision,
        player_a_id: session.next_pair.player_a.id,
        player_b_id: session.next_pair.player_b.id,
        outcome,
      });
      acceptSession(updated);
      setNotice(
        outcome === "skip"
          ? "Pair postponed. It can return after other matchups."
          : outcome === "insufficient"
            ? "Not-enough-information saved without changing either rating."
            : "Preference saved locally.",
      );
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  async function choosePlayer(playerId: string) {
    if (!session?.next_pair) return;
    await recordOutcome(
      playerId === session.next_pair.player_a.id ? "a_win" : "b_win",
    );
  }

  async function changeStatus(status: "active" | "paused") {
    if (!session || busyAction) return;
    clearMessages();
    setBusyAction("status");
    try {
      const updated = await updateGutEloSession(session.id, { status });
      acceptSession(updated);
      setNotice(
        status === "paused"
          ? "Session paused. Every choice is saved."
          : "Session resumed at the next unresolved pair.",
      );
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  async function undo() {
    if (!session || session.actions.length === 0 || busyAction) return;
    clearMessages();
    setBusyAction("undo");
    try {
      acceptSession(await undoGutEloAction(session.id));
      setNotice("Latest comparison undone and ratings replayed.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  const tierName = useMemo(() => {
    if (!session?.tier_id) return null;
    return board?.tiers.find((tier) => tier.id === session.tier_id)?.name ?? null;
  }, [board?.tiers, session?.tier_id]);

  const visualPair = useMemo(() => {
    if (!session?.next_pair) return null;
    const { player_a: playerA, player_b: playerB } = session.next_pair;
    return session.revision % 2 === 0
      ? { left: playerA, right: playerB }
      : { left: playerB, right: playerA };
  }, [session]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLSelectElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLButtonElement ||
        event.repeat ||
        busyAction
      ) {
        return;
      }
      const key = event.key.toLowerCase();
      if (visualPair && session?.status === "active") {
        if (key === "1" || key === "arrowleft") {
          event.preventDefault();
          void choosePlayer(visualPair.left.id);
          return;
        }
        if (key === "2" || key === "arrowright") {
          event.preventDefault();
          void choosePlayer(visualPair.right.id);
          return;
        }
        if (key === "s") {
          event.preventDefault();
          void recordOutcome("skip");
          return;
        }
        if (key === "n") {
          event.preventDefault();
          void recordOutcome("insufficient");
          return;
        }
      }
      if (key === "u" && session?.actions.length) {
        event.preventDefault();
        void undo();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  return (
    <section className="gut-workspace" aria-labelledby="gut-workspace-title">
      <div className="workspace-heading gut-workspace-heading">
        <div>
          <p className="eyebrow">V1 · Instinct lab</p>
          <h2 id="gut-workspace-title">Gut ELO</h2>
          <p>
            Make quick head-to-head calls, surface your conviction, and compare
            the signal with the board you control.
          </p>
        </div>
        <span className="privacy-pill">Explainable / saved locally</span>
      </div>

      <div className="workspace-messages" aria-live="polite">
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

      <div className="gut-layout" aria-busy={loading}>
        <aside className="gut-sidebar" aria-label="Gut ELO session room">
          <label className="gut-board-select">
            Personal Board
            <select
              value={selectedBoardId ?? ""}
              onChange={(event) => setSelectedBoardId(event.target.value)}
            >
              {boards.length === 0 && (
                <option value="">No active boards</option>
              )}
              {boards.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>

          <div className="gut-sidebar-heading">
            <div>
              <span>Saved sessions</span>
              <strong>{sessions.length}</strong>
            </div>
            <button
              className="icon-button"
              type="button"
              aria-label="Start a new Gut ELO session"
              disabled={!board}
              onClick={() => {
                clearMessages();
                setSetupMode(true);
              }}
            >
              +
            </button>
          </div>
          <div className="gut-session-list">
            {sessions.map((item, index) => (
              <button
                type="button"
                key={item.id}
                aria-current={
                  !setupMode && session?.id === item.id ? "page" : undefined
                }
                disabled={busyAction === "open"}
                onClick={() => void openSession(item.id)}
              >
                <span>
                  Run {sessions.length - index}
                  <i className={`gut-status-dot gut-status-${item.status}`} />
                </span>
                <small>
                  {titleCase(item.queue_mode)} / {item.resolved_count} of{" "}
                  {item.target_count}
                </small>
              </button>
            ))}
            {sessions.length === 0 && (
              <p>No saved sessions for this board yet.</p>
            )}
          </div>
          {board && (
            <div className="gut-board-authority">
              <span>Official order</span>
              <strong>Personal Board</strong>
              <small>{board.entry_count} ranked players</small>
            </div>
          )}
        </aside>

        <div className="gut-stage">
          {!board ? (
            <div className="empty-player-state gut-empty-state">
              <span aria-hidden="true">GE</span>
              <h3>Build a Personal Board first.</h3>
              <p>
                Gut ELO compares players you have deliberately placed on a
                board. Open the Boards tab, add at least two players, then
                return here.
              </p>
            </div>
          ) : setupMode || !session ? (
            <SessionSetup
              key={board.id}
              board={board}
              busy={busyAction === "start"}
              onStart={startSession}
            />
          ) : (
            <>
              <header className="gut-session-heading">
                <div>
                  <div className="gut-session-title">
                    <span
                      className={`gut-status-badge gut-status-${session.status}`}
                    >
                      {titleCase(session.status)}
                    </span>
                    <span>{titleCase(session.board_scope)}</span>
                  </div>
                  <h3>{session.board_name}</h3>
                  <p>
                    {queueLabel(session.queue_mode, session.position, tierName)}
                    {" / "}
                    {session.participant_count} players
                  </p>
                </div>
                <div className="gut-session-actions">
                  {session.status === "active" && (
                    <button
                      className="quiet-button"
                      type="button"
                      disabled={busyAction !== null}
                      onClick={() => void changeStatus("paused")}
                    >
                      Pause
                    </button>
                  )}
                  {session.status === "paused" && (
                    <button
                      className="primary-button"
                      type="button"
                      disabled={busyAction !== null}
                      onClick={() => void changeStatus("active")}
                    >
                      Resume
                    </button>
                  )}
                  <button
                    className="quiet-button"
                    type="button"
                    disabled={
                      session.actions.length === 0 || busyAction !== null
                    }
                    onClick={() => void undo()}
                  >
                    Undo <kbd>U</kbd>
                  </button>
                </div>
              </header>

              <div className="gut-progress-panel">
                <div className="gut-progress-copy">
                  <div>
                    <strong>{session.progress.progress_percent}%</strong>
                    <span>
                      {session.progress.resolved_count} of{" "}
                      {session.progress.target_count} resolved
                    </span>
                  </div>
                  <span className="gut-stability">
                    {titleCase(session.progress.stability_label)}
                  </span>
                </div>
                <div
                  className="gut-progress-track"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={session.progress.progress_percent}
                  aria-label="Session progress"
                >
                  <span
                    style={{ width: `${session.progress.progress_percent}%` }}
                  />
                </div>
                <p>{session.progress.stability_explanation}</p>
                <div className="gut-progress-stats">
                  <span>
                    <strong>{session.progress.coverage_percent}%</strong>{" "}
                    decisive coverage
                  </span>
                  <span>
                    <strong>{session.progress.decisive_count}</strong> choices
                  </span>
                  <span>
                    <strong>{session.progress.insufficient_count}</strong>{" "}
                    insufficient
                  </span>
                  <span>
                    <strong>{session.progress.skip_count}</strong> skips
                  </span>
                </div>
              </div>

              {session.status === "active" && visualPair ? (
                <section
                  className="gut-comparison"
                  aria-labelledby="gut-comparison-title"
                >
                  <div className="gut-comparison-prompt">
                    <p className="eyebrow">
                      Comparison {session.revision + 1}
                    </p>
                    <h3 id="gut-comparison-title">
                      Who would you rather roster?
                    </h3>
                    <p>First reaction. No market data, no forced certainty.</p>
                  </div>
                  <div className="gut-choice-grid">
                    <PlayerChoiceCard
                      player={visualPair.left}
                      side="left"
                      disabled={busyAction !== null}
                      onChoose={() => void choosePlayer(visualPair.left.id)}
                    />
                    <span className="gut-versus" aria-hidden="true">
                      VS
                    </span>
                    <PlayerChoiceCard
                      player={visualPair.right}
                      side="right"
                      disabled={busyAction !== null}
                      onChoose={() => void choosePlayer(visualPair.right.id)}
                    />
                  </div>
                  <div className="gut-comparison-controls">
                    <button
                      className="quiet-button"
                      type="button"
                      disabled={busyAction !== null}
                      onClick={() => void recordOutcome("skip")}
                    >
                      Skip for now <kbd>S</kbd>
                    </button>
                    <button
                      className="quiet-button"
                      type="button"
                      disabled={busyAction !== null}
                      onClick={() => void recordOutcome("insufficient")}
                    >
                      Not enough information <kbd>N</kbd>
                    </button>
                  </div>
                  <p className="gut-keyboard-note">
                    Keyboard: <kbd>1</kbd> or <kbd>←</kbd> left, <kbd>2</kbd> or{" "}
                    <kbd>→</kbd> right, <kbd>S</kbd> skip, <kbd>N</kbd>{" "}
                    insufficient.
                  </p>
                </section>
              ) : session.status === "paused" ? (
                <div className="gut-state-callout">
                  <span aria-hidden="true">II</span>
                  <div>
                    <p className="eyebrow">Session paused</p>
                    <h3>Your place is saved.</h3>
                    <p>
                      Resume whenever you want. Ratings and the next pair are
                      rebuilt from the saved action history.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="gut-state-callout gut-complete-callout">
                  <span aria-hidden="true">✓</span>
                  <div>
                    <p className="eyebrow">Bounded target reached</p>
                    <h3>This run has a useful preference signal.</h3>
                    <p>
                      Review the movement below. Nothing has been applied to the
                      Personal Board unless you choose to make a manual edit
                      there.
                    </p>
                  </div>
                </div>
              )}

              <SessionResults session={session} />
            </>
          )}
        </div>
      </div>
    </section>
  );
}
