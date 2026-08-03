import {
  Fragment,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";

import {
  ApiError,
  type DraftCandidateResponse,
  type MockPickDecision,
  type MockSession,
  type MockSessionCreate,
  advanceMockCpuPick,
  correctDraftPick,
  createMockSession,
  getBoards,
  getDraftCandidates,
  getMockDecision,
  getMockSession,
  getMockSessions,
  recordDraftPick,
  undoDraftPick,
  updateDraftSession,
  updateMockGuidanceStatus,
  updateMockLearning,
  updateMockStrategy,
} from "../../api/client";

type BoardSummary = Awaited<ReturnType<typeof getBoards>>["items"][number];
type MockHistory = Awaited<ReturnType<typeof getMockSessions>>["items"][number];
type DraftView = DraftCandidateResponse["view"];
type UiError = { message: string; action?: string };
type RunState = "idle" | "running" | "stopping" | "pausing";

const strategies = [
  ["balanced", "Balanced build"],
  ["win_now", "Win now"],
  ["productive_struggle", "Productive struggle"],
  ["hero_rb", "Hero RB"],
  ["robust_rb", "Robust RB"],
  ["wr_heavy", "WR heavy"],
  ["early_qb_superflex", "Early QB (superflex)"],
] as const;

function sentence(value: string) {
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^\w/, (letter) => letter.toUpperCase());
}

function formatError(error: unknown): UiError {
  if (error instanceof ApiError) {
    return { message: error.message, action: error.action };
  }
  return {
    message: "The Mock Lab could not finish that action.",
    action: "Refresh the saved rehearsal and try again.",
  };
}

function isFormField(target: EventTarget | null) {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  );
}

function personalRank(
  candidate: DraftCandidateResponse["items"][number],
): number | string {
  if (
    "personal_rank" in candidate &&
    typeof candidate.personal_rank === "number"
  ) {
    return candidate.personal_rank;
  }
  return "—";
}

function tierName(
  candidate: DraftCandidateResponse["items"][number],
): string {
  if ("tier_name" in candidate && typeof candidate.tier_name === "string") {
    return candidate.tier_name;
  }
  return "Unassigned";
}

function MockSetup({
  board,
  busy,
  onCreate,
}: {
  board: BoardSummary;
  busy: boolean;
  onCreate: (payload: MockSessionCreate) => Promise<void>;
}) {
  const [name, setName] = useState("Strategy rehearsal");
  const [teamCount, setTeamCount] = useState(10);
  const [roundCount, setRoundCount] = useState(24);
  const [userSlot, setUserSlot] = useState(1);
  const [draftFormat, setDraftFormat] =
    useState<MockSessionCreate["draft_format"]>("snake");
  const [thirdRoundReversal, setThirdRoundReversal] = useState(true);
  const [seed, setSeed] = useState("20260728");
  const [randomness, setRandomness] = useState(25);
  const [strategyKey, setStrategyKey] = useState("balanced");

  function submit(event: FormEvent) {
    event.preventDefault();
    void onCreate({
      name,
      league_profile_id: board.league_profile_id,
      draft_format: draftFormat,
      third_round_reversal:
        draftFormat === "snake" ? thirdRoundReversal : false,
      team_count: teamCount,
      round_count: roundCount,
      user_slot: Math.min(userSlot, teamCount),
      seed,
      randomness,
      strategy_key: strategyKey,
      include_in_learning: false,
    });
  }

  return (
    <form className="mock-setup" onSubmit={submit}>
      <div className="draft-setup-heading">
        <div>
          <p className="eyebrow">New rehearsal</p>
          <h3>Set the room, then roll cameras.</h3>
        </div>
        <span>Learning off by default</span>
      </div>
      <div className="mock-setup-grid">
        <label className="mock-name-field">
          Rehearsal name
          <input
            required
            maxLength={200}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          Teams
          <input
            type="number"
            min={2}
            max={32}
            value={teamCount}
            onChange={(event) => {
              const next = Number(event.target.value);
              setTeamCount(next);
              setUserSlot((current) => Math.min(current, next));
            }}
          />
        </label>
        <label>
          Rounds
          <input
            type="number"
            min={1}
            max={60}
            value={roundCount}
            onChange={(event) => setRoundCount(Number(event.target.value))}
          />
        </label>
        <label>
          Your slot
          <input
            type="number"
            min={1}
            max={teamCount}
            value={userSlot}
            onChange={(event) => setUserSlot(Number(event.target.value))}
          />
        </label>
        <label>
          Format
          <select
            value={draftFormat}
            onChange={(event) =>
              setDraftFormat(
                event.target.value as MockSessionCreate["draft_format"],
              )
            }
          >
            <option value="snake">Snake</option>
            <option value="linear">Linear</option>
          </select>
        </label>
        <label>
          Seed
          <input
            required
            inputMode="numeric"
            pattern="[0-9]+"
            title="Use digits only so the same seed can be replayed."
            value={seed}
            onChange={(event) => setSeed(event.target.value)}
          />
        </label>
        <label>
          Randomness · {randomness}
          <input
            aria-label="Randomness"
            type="range"
            min={0}
            max={100}
            value={randomness}
            onChange={(event) => setRandomness(Number(event.target.value))}
          />
        </label>
        <label>
          Strategy guide
          <select
            value={strategyKey}
            onChange={(event) => setStrategyKey(event.target.value)}
          >
            {strategies.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="mock-reversal-field">
          <input
            type="checkbox"
            checked={thirdRoundReversal}
            disabled={draftFormat !== "snake"}
            onChange={(event) => setThirdRoundReversal(event.target.checked)}
          />
          Third-round reversal
          <small>Reverses round three, then resumes the snake order.</small>
        </label>
      </div>
      <div className="draft-setup-footer">
        <p>
          CPU teams use a frozen copy of <strong>{board.name}</strong>. The
          simulation cannot change your Personal Board or make your picks.
        </p>
        <button className="primary-button" type="submit" disabled={busy}>
          Create practice simulation
        </button>
      </div>
    </form>
  );
}

export function MockWorkspace() {
  const [boards, setBoards] = useState<BoardSummary[]>([]);
  const [boardId, setBoardId] = useState("");
  const [history, setHistory] = useState<MockHistory[]>([]);
  const [mock, setMock] = useState<MockSession | null>(null);
  const [candidates, setCandidates] =
    useState<DraftCandidateResponse | null>(null);
  const [view, setView] = useState<DraftView>("personal");
  const [search, setSearch] = useState("");
  const [pendingCandidateId, setPendingCandidateId] = useState<string | null>(
    null,
  );
  const [correctingPick, setCorrectingPick] = useState<number | null>(null);
  const [pivotStrategy, setPivotStrategy] = useState("balanced");
  const [decision, setDecision] = useState<MockPickDecision | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [runState, setRunState] = useState<RunState>("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<UiError | null>(null);
  const stopRequested = useRef(false);
  const pauseRequested = useRef(false);

  const selectedBoard = boards.find((board) => board.id === boardId);
  const draft = mock?.draft;
  const correctionTarget = draft?.picks.find(
    (pick) => pick.overall_pick === correctingPick,
  );

  async function refreshHistory(nextBoardId = boardId) {
    if (!nextBoardId) return;
    const result = await getMockSessions(nextBoardId);
    setHistory(result.items);
  }

  async function loadMock(sessionId: string) {
    const loaded = await getMockSession(sessionId);
    setMock(loaded);
    setPivotStrategy(loaded.mock.current_strategy_key);
    setPendingCandidateId(null);
    setCorrectingPick(null);
    setDecision(null);
  }

  async function openMock(sessionId: string) {
    setError(null);
    setNotice(null);
    try {
      await loadMock(sessionId);
    } catch (caught) {
      setError(formatError(caught));
    }
  }

  async function refreshAuthoritative(sessionId: string) {
    try {
      await loadMock(sessionId);
      await refreshHistory();
    } catch {
      // Keep the original actionable error visible.
    }
  }

  async function loadBoard(nextBoardId: string) {
    setLoading(true);
    setError(null);
    setNotice(null);
    setMock(null);
    setCandidates(null);
    try {
      const result = await getMockSessions(nextBoardId);
      setHistory(result.items);
      if (result.items[0]) await loadMock(result.items[0].session_id);
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
          await loadBoard(first.id);
        } else {
          setLoading(false);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(formatError(caught));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!draft) {
      setCandidates(null);
      return;
    }
    let cancelled = false;
    getDraftCandidates(draft.id, {
      view,
      search,
      includeDrafted: false,
      limit: 200,
      offset: 0,
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
  }, [draft?.id, draft?.revision, search, view]);

  async function createPractice(payload: MockSessionCreate) {
    if (!boardId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createMockSession(boardId, payload);
      setMock(created);
      setPivotStrategy(created.mock.current_strategy_key);
      await refreshHistory(boardId);
      setNotice("Practice simulation created and saved locally.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function advanceOne(current: MockSession) {
    const currentPick = current.draft.current_pick;
    if (!currentPick || !current.can_advance_cpu) return current;
    return advanceMockCpuPick(current.draft.id, {
      draft_revision: current.draft.revision,
      mock_revision: current.mock.revision,
      expected_overall_pick: currentPick.overall_pick,
      expected_selecting_slot: currentPick.selecting_slot,
    });
  }

  async function advanceSingle() {
    if (!mock || !mock.can_advance_cpu) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await advanceOne(mock);
      setMock(updated);
      await refreshHistory();
      setNotice(
        `CPU pick ${updated.last_cpu_decision?.overall_pick ?? ""} saved.`
          .trim(),
      );
    } catch (caught) {
      setError(formatError(caught));
      await refreshAuthoritative(mock.draft.id);
    } finally {
      setBusy(false);
    }
  }

  async function runToUser() {
    if (!mock || !mock.can_advance_cpu || runState !== "idle") return;
    stopRequested.current = false;
    pauseRequested.current = false;
    setRunState("running");
    setBusy(true);
    setError(null);
    setNotice(null);
    let current = mock;
    try {
      while (
        current.can_advance_cpu &&
        current.draft.status === "active" &&
        !current.draft.user_on_the_clock &&
        !stopRequested.current
      ) {
        current = await advanceOne(current);
        setMock(current);
      }
      if (
        pauseRequested.current &&
        current.draft.status === "active" &&
        current.draft.current_pick
      ) {
        await updateDraftSession(current.draft.id, {
          revision: current.draft.revision,
          status: "paused",
        });
        current = await getMockSession(current.draft.id);
        setMock(current);
      }
      await refreshHistory();
      setNotice(
        pauseRequested.current
          ? "Practice paused after the latest saved CPU pick."
          : stopRequested.current
          ? "Stopped after the latest saved CPU pick."
          : current.draft.user_on_the_clock
            ? "The run stopped safely. You are on the clock."
            : "The run stopped at the latest saved state.",
      );
    } catch (caught) {
      setError(formatError(caught));
      await refreshAuthoritative(current.draft.id);
    } finally {
      stopRequested.current = false;
      pauseRequested.current = false;
      setRunState("idle");
      setBusy(false);
    }
  }

  function requestStop() {
    stopRequested.current = true;
    setRunState("stopping");
  }

  function requestPause() {
    pauseRequested.current = true;
    stopRequested.current = true;
    setRunState("pausing");
  }

  async function saveUserPick() {
    if (!mock || !draft || !pendingCandidateId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (correctionTarget) {
        await correctDraftPick(
          draft.id,
          correctionTarget.overall_pick,
          {
            revision: draft.revision,
            expected_current_player_id: correctionTarget.player_id,
            replacement_player_id: pendingCandidateId,
          },
        );
      } else {
        if (!draft.user_on_the_clock || !draft.current_pick) return;
        await recordDraftPick(draft.id, {
          revision: draft.revision,
          expected_overall_pick: draft.current_pick.overall_pick,
          player_id: pendingCandidateId,
          client_entered_at: new Date().toISOString(),
        });
      }
      const updated = await getMockSession(draft.id);
      setMock(updated);
      setPendingCandidateId(null);
      setCorrectingPick(null);
      await refreshHistory();
      setNotice(
        correctionTarget
          ? `Pick ${correctionTarget.overall_pick} corrected. The manual pick is authoritative.`
          : "Your pick is confirmed and saved. No CPU action was bundled with it.",
      );
    } catch (caught) {
      setError(formatError(caught));
      await refreshAuthoritative(draft.id);
    } finally {
      setBusy(false);
    }
  }

  async function pauseOrResume() {
    if (!mock || !draft || !["active", "paused"].includes(draft.status)) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await updateDraftSession(draft.id, {
        revision: draft.revision,
        status: draft.status === "active" ? "paused" : "active",
      });
      const updated = await getMockSession(draft.id);
      setMock(updated);
      await refreshHistory();
      setNotice(
        updated.draft.status === "paused"
          ? "Practice paused at the same saved pick."
          : "Practice resumed from the preserved pick.",
      );
    } catch (caught) {
      setError(formatError(caught));
      await refreshAuthoritative(draft.id);
    } finally {
      setBusy(false);
    }
  }

  async function undoLatest() {
    if (!mock || !draft || draft.active_pick_count === 0) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await undoDraftPick(draft.id, { revision: draft.revision });
      const updated = await getMockSession(draft.id);
      setMock(updated);
      await refreshHistory();
      setNotice(
        "Latest pick undone. Its saved CPU explanation remains in the audit.",
      );
    } catch (caught) {
      setError(formatError(caught));
      await refreshAuthoritative(draft.id);
    } finally {
      setBusy(false);
    }
  }

  async function savePivot() {
    if (
      !mock ||
      !draft?.current_pick ||
      pivotStrategy === mock.mock.current_strategy_key
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const completedPicks = draft.picks;
      const updated = await updateMockStrategy(draft.id, {
        mock_revision: mock.mock.revision,
        expected_current_overall_pick: draft.current_pick.overall_pick,
        strategy_key: pivotStrategy,
      });
      setMock(updated);
      await refreshHistory();
      setNotice(
        `Guide pivoted. All ${completedPicks.length} completed picks remain unchanged.`,
      );
    } catch (caught) {
      setError(formatError(caught));
      await refreshAuthoritative(draft.id);
    } finally {
      setBusy(false);
    }
  }

  async function toggleLearning(include: boolean) {
    if (!mock) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await updateMockLearning(mock.draft.id, {
        mock_revision: mock.mock.revision,
        include_in_learning: include,
      });
      setMock(updated);
      await refreshHistory();
      setNotice(
        include
          ? "This rehearsal may now contribute to future local summaries."
          : "This rehearsal is excluded from future local summaries.",
      );
    } catch (caught) {
      setError(formatError(caught));
      await refreshAuthoritative(mock.draft.id);
    } finally {
      setBusy(false);
    }
  }

  async function dismissCheckpoint() {
    if (!mock) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateMockGuidanceStatus(
        mock.draft.id,
        mock.current_checkpoint.id,
        {
          mock_revision: mock.mock.revision,
          status: "dismissed",
        },
      );
      setMock(updated);
      setNotice("Checkpoint dismissed. Its audit remains saved.");
    } catch (caught) {
      setError(formatError(caught));
      await refreshAuthoritative(mock.draft.id);
    } finally {
      setBusy(false);
    }
  }

  async function inspectDecision() {
    if (!mock?.last_cpu_decision) return;
    try {
      setDecision(
        await getMockDecision(
          mock.draft.id,
          mock.last_cpu_decision.overall_pick,
        ),
      );
    } catch (caught) {
      setError(formatError(caught));
    }
  }

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (isFormField(event.target)) return;
      if (
        event.key.toLowerCase() === "r" &&
        mock?.can_advance_cpu &&
        runState === "idle" &&
        !busy
      ) {
        event.preventDefault();
        void runToUser();
      }
      if (event.key.toLowerCase() === "s" && runState !== "idle") {
        event.preventDefault();
        requestStop();
      }
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [busy, mock, runState]);

  const selectedProfile = useMemo(() => {
    const slot = draft?.current_pick?.selecting_slot;
    return mock?.cpu_profiles.find((profile) => profile.draft_slot === slot);
  }, [draft?.current_pick?.selecting_slot, mock?.cpu_profiles]);

  const candidateItems = candidates?.items ?? [];
  const canChooseCandidate = Boolean(
    correctionTarget ||
      (draft?.status === "active" && draft.user_on_the_clock),
  );

  return (
    <section className="draft-workspace mock-workspace">
      <div className="draft-workspace-heading">
        <div>
          <p className="eyebrow">V1 · Mock strategy lab</p>
          <h2>Rehearse the room. Keep every final call.</h2>
          <p>
            CPU teams can advance only in this practice workspace. Your picks
            always stop the rehearsal and wait for explicit confirmation.
          </p>
        </div>
        <span className="mock-practice-badge">Practice simulation</span>
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
          Personal Board snapshot
          <select
            value={boardId}
            disabled={loading || boards.length === 0 || busy}
            onChange={(event) => {
              setBoardId(event.target.value);
              void loadBoard(event.target.value);
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
          <strong>{history.length}</strong>
          <span>saved rehearsals</span>
        </div>
        <button
          className="quiet-button"
          type="button"
          disabled={!selectedBoard || busy}
          onClick={() => {
            setMock(null);
            setCandidates(null);
            setNotice(null);
          }}
        >
          New rehearsal
        </button>
      </div>

      {!loading && boards.length === 0 && (
        <div className="draft-empty">
          <strong>A Personal Board is the casting list for this rehearsal.</strong>
          <p>Create a board and add relevant players before opening the Mock Lab.</p>
        </div>
      )}

      {history.length > 0 && (
        <div className="draft-session-tabs" aria-label="Saved mock rehearsals">
          {history.map((item) => (
            <button
              type="button"
              key={item.session_id}
              aria-current={
                item.session_id === draft?.id ? "page" : undefined
              }
              disabled={busy}
              onClick={() => void openMock(item.session_id)}
            >
              <strong>{item.name}</strong>
              <span>
                {item.completion_state} · seed {item.seed} ·{" "}
                {item.include_in_learning ? "learning on" : "learning off"}
              </span>
            </button>
          ))}
        </div>
      )}

      {selectedBoard && !mock && (
        <MockSetup
          key={selectedBoard.id}
          board={selectedBoard}
          busy={busy}
          onCreate={createPractice}
        />
      )}

      {mock && draft && (
        <>
          <div className="mock-control-strip">
            <div className="mock-strip-identity">
              <span className="mock-practice-badge">Practice simulation</span>
              <strong>{draft.name}</strong>
              <small>
                Seed {mock.mock.seed} · Randomness {mock.mock.randomness} · Saved
                locally
              </small>
            </div>
            <div>
              <span>Strategy</span>
              <strong>{sentence(mock.mock.current_strategy_key)}</strong>
              <small>
                Draft rev {draft.revision} · Mock rev {mock.mock.revision}
              </small>
            </div>
            <div className={draft.user_on_the_clock ? "is-user-clock" : ""}>
              <span>Current pick</span>
              <strong>
                {draft.current_pick
                  ? `${draft.current_pick.round_number}.${String(
                      draft.current_pick.pick_in_round,
                    ).padStart(2, "0")}`
                  : "Complete"}
              </strong>
              <small>
                {draft.current_pick?.selecting_team ?? "Room closed"}
              </small>
            </div>
            <div className="mock-run-actions">
              {runState === "idle" ? (
                <>
                  <button
                    className="primary-button"
                    type="button"
                    disabled={busy || !mock.can_advance_cpu}
                    onClick={() => void runToUser()}
                  >
                    Run to my pick
                  </button>
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={busy || !mock.can_advance_cpu}
                    onClick={() => void advanceSingle()}
                  >
                    Advance one CPU pick
                  </button>
                </>
              ) : (
                <button
                  className="danger-button"
                  type="button"
                  disabled={
                    runState === "stopping" || runState === "pausing"
                  }
                  onClick={requestStop}
                >
                  {runState === "stopping" || runState === "pausing"
                    ? "Stopping after current pick…"
                    : "Stop after current pick"}
                </button>
              )}
              <button
                className="quiet-button"
                type="button"
                disabled={
                  runState === "idle"
                    ? busy || !["active", "paused"].includes(draft.status)
                    : runState === "pausing"
                }
                onClick={() =>
                  runState === "idle"
                    ? void pauseOrResume()
                    : requestPause()
                }
              >
                {runState === "pausing"
                  ? "Pausing after current pick…"
                  : draft.status === "paused"
                    ? "Resume"
                    : "Pause"}
              </button>
              <span className="mock-shortcuts">
                <kbd>R</kbd> Run <kbd>S</kbd> Stop
              </span>
            </div>
          </div>

          <div className="mock-evidence-strip">
            <div>
              <span>CPU profile</span>
              <strong>
                {selectedProfile
                  ? sentence(selectedProfile.archetype_key)
                  : draft.user_on_the_clock
                    ? "Your manual decision"
                    : "No active CPU"}
              </strong>
              {selectedProfile && (
                <small>
                  {selectedProfile.source === "fallback"
                    ? "Fallback model — not learned manager behavior"
                    : `History model · ${selectedProfile.confidence} confidence`}
                </small>
              )}
            </div>
            <div>
              <span>Progress</span>
              <strong>
                {draft.active_pick_count} / {draft.total_picks} saved
              </strong>
              <small>
                {draft.user_on_the_clock
                  ? "Stopped for your pick"
                  : `${draft.picks_until_user ?? 0} picks until you`}
              </small>
            </div>
            <label className="mock-learning-toggle">
              <input
                type="checkbox"
                checked={mock.mock.include_in_learning}
                disabled={busy}
                onChange={(event) => void toggleLearning(event.target.checked)}
              />
              <span>
                Include in local learning
                <small>
                  Changes future summaries only. It never changes saved picks.
                </small>
              </span>
            </label>
          </div>

          <div className="mock-operating-grid">
            <section className="draft-candidate-panel">
              <div className="draft-candidate-toolbar">
                <div className="draft-view-tabs">
                  {(["blind", "personal", "position", "tier"] as const).map(
                    (value) => (
                      <button
                        type="button"
                        key={value}
                        aria-current={view === value ? "page" : undefined}
                        onClick={() => setView(value)}
                      >
                        {value}
                      </button>
                    ),
                  )}
                </div>
                <label>
                  <span className="visually-hidden">Search candidates</span>
                  <input
                    type="search"
                    placeholder="Search candidates"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                  />
                </label>
                <span className="draft-shortcuts">
                  Your selection is always manual and confirmed.
                </span>
              </div>
              <div className="draft-candidate-heading">
                <div>
                  <p className="eyebrow">
                    {correctionTarget
                      ? `Correcting pick ${correctionTarget.overall_pick}`
                      : draft.user_on_the_clock
                        ? "You are on the clock"
                        : "Scouting board"}
                  </p>
                  <h3>{candidates?.total ?? 0} available candidates</h3>
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
              <div className="draft-candidate-table-wrap">
                <table className="draft-candidate-table">
                  <thead>
                    <tr>
                      <th>Personal</th>
                      <th>Player</th>
                      <th>Pos</th>
                      <th>Tier</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidateItems.map((candidate) => {
                      const contextual = "personal_rank" in candidate;
                      const pending =
                        candidate.player_id === pendingCandidateId;
                      return (
                        <Fragment key={candidate.player_id}>
                          <tr
                            className={pending ? "is-pending" : undefined}
                          >
                            <td className="draft-rank-cell">
                              {contextual
                                ? personalRank(candidate)
                                : "Hidden"}
                            </td>
                            <th scope="row">
                              <strong>{candidate.display_name}</strong>
                              <span>{candidate.team ?? "FA"}</span>
                            </th>
                            <td>{candidate.primary_position}</td>
                            <td className="draft-context-cell">
                              {contextual
                                ? tierName(candidate)
                                : "Hidden"}
                            </td>
                            <td>
                              <button
                                className="quiet-button"
                                type="button"
                                disabled={!canChooseCandidate || busy}
                                onClick={() =>
                                  setPendingCandidateId(candidate.player_id)
                                }
                              >
                                {correctionTarget ? "Use correction" : "Draft"}
                              </button>
                            </td>
                          </tr>
                          {pending && (
                            <tr className="draft-confirmation-row">
                              <td colSpan={5}>
                                <span>
                                  Confirm{" "}
                                  <strong>{candidate.display_name}</strong>. No
                                  CPU pick is included.
                                </span>
                                <div>
                                  <button
                                    className="quiet-button"
                                    type="button"
                                    onClick={() => setPendingCandidateId(null)}
                                  >
                                    Cancel
                                  </button>
                                  <button
                                    className="primary-button"
                                    type="button"
                                    disabled={busy}
                                    onClick={() => void saveUserPick()}
                                  >
                                    Confirm pick
                                  </button>
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
                {candidateItems.length === 0 && (
                  <div className="draft-empty">No candidates match this view.</div>
                )}
              </div>
            </section>

            <aside className="mock-strategy-panel">
              <p className="eyebrow">Strategy checkpoint</p>
              <h3>{sentence(mock.current_checkpoint.state)}</h3>
              <p>{mock.current_checkpoint.explanation}</p>
              {mock.current_checkpoint.viable_pivot_explanation && (
                <p className="mock-pivot-note">
                  {mock.current_checkpoint.viable_pivot_explanation}
                </p>
              )}
              <dl className="mock-checkpoint-facts">
                <div>
                  <dt>Confidence</dt>
                  <dd>{sentence(mock.current_checkpoint.confidence)}</dd>
                </div>
                <div>
                  <dt>Effective pick</dt>
                  <dd>{mock.current_checkpoint.effective_overall_pick}</dd>
                </div>
              </dl>
              <label>
                Future strategy guide
                <select
                  value={pivotStrategy}
                  disabled={busy || !draft.current_pick}
                  onChange={(event) => setPivotStrategy(event.target.value)}
                >
                  {strategies.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="secondary-button"
                type="button"
                disabled={
                  busy ||
                  !draft.current_pick ||
                  pivotStrategy === mock.mock.current_strategy_key
                }
                onClick={() => void savePivot()}
              >
                Pivot future guidance
              </button>
              <small className="mock-panel-explainer">
                A pivot changes later checkpoints. It never rewrites completed
                picks.
              </small>
              {mock.current_checkpoint.status === "open" && (
                <button
                  className="quiet-button"
                  type="button"
                  disabled={busy}
                  onClick={() => void dismissCheckpoint()}
                >
                  Dismiss checkpoint
                </button>
              )}
              <div className="mock-limitations">
                <strong>Evidence limits</strong>
                {(mock.mock.strategy_limitations.length > 0 ||
                  mock.current_checkpoint.limitation_codes.length > 0) ? (
                  <ul>
                    {[
                      ...new Set([
                        ...mock.mock.strategy_limitations,
                        ...mock.current_checkpoint.limitation_codes,
                      ]),
                    ].map((limitation) => (
                      <li key={limitation}>{sentence(limitation)}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No current strategy limitations.</p>
                )}
              </div>
            </aside>

            <aside className="draft-pick-rail mock-audit-panel">
              <p className="eyebrow">Saved pick audit</p>
              <h3>Latest decisions</h3>
              {mock.last_cpu_decision && (
                <details className="mock-decision" open>
                  <summary>
                    Pick {mock.last_cpu_decision.overall_pick}:{" "}
                    {mock.last_cpu_decision.chosen_player_display_name}
                  </summary>
                  <p>
                    {sentence(mock.last_cpu_decision.profile_archetype_key)} ·{" "}
                    {mock.last_cpu_decision.profile_source === "fallback"
                      ? "Fallback model"
                      : "History model"}
                  </p>
                  <ul>
                    {mock.last_cpu_decision.reason_codes.map((reason) => (
                      <li key={reason}>{sentence(reason)}</li>
                    ))}
                  </ul>
                  <button
                    className="quiet-button"
                    type="button"
                    onClick={() => void inspectDecision()}
                  >
                    Inspect saved score
                  </button>
                  {decision &&
                    decision.overall_pick ===
                      mock.last_cpu_decision.overall_pick && (
                      <dl className="mock-score-grid">
                        {Object.entries(decision.component_scores).map(
                          ([key, value]) => (
                            <div key={key}>
                              <dt>{sentence(key)}</dt>
                              <dd>{value}</dd>
                            </div>
                          ),
                        )}
                      </dl>
                    )}
                </details>
              )}
              <div className="mock-audit-actions">
                <button
                  className="quiet-button"
                  type="button"
                  disabled={busy || draft.active_pick_count === 0}
                  onClick={() => void undoLatest()}
                >
                  Undo latest
                </button>
              </div>
              <ol>
                {[...draft.picks].reverse().map((pick) => (
                  <li key={pick.overall_pick}>
                    <span>{pick.overall_pick}</span>
                    <strong>{pick.player_display_name}</strong>
                    <button
                      className="quiet-button"
                      type="button"
                      disabled={busy}
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
                <p className="draft-rail-empty">No picks saved yet.</p>
              )}
              {(mock.recovery_guidance || draft.recovery_guidance) && (
                <p className="draft-recovery">
                  {mock.recovery_guidance ?? draft.recovery_guidance}
                </p>
              )}
            </aside>
          </div>
        </>
      )}
    </section>
  );
}
