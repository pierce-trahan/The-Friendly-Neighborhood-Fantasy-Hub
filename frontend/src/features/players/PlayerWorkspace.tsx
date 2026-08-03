import {
  type ChangeEvent,
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  ApiError,
  type MappingDecisionRequest,
  type Player,
  type PlayerImportSession,
  type PlayerListResponse,
  type PlayerPatch,
  type PlayerPosition,
  type PlayerStatus,
  cancelPlayerImport,
  commitPlayerImport,
  decidePlayerImportRow,
  getPlayerExportUrl,
  getPlayers,
  previewPlayerCsv,
  previewPlayerFixture,
  updatePlayer,
} from "../../api/client";

type WorkspaceView = "universe" | "preview" | "review";
type ImportRow = PlayerImportSession["rows"][number];
type ImportOutcome = ImportRow["outcome"];
type UiError = { message: string; action?: string };

const positions: PlayerPosition[] = ["QB", "RB", "WR", "TE", "K", "DEF"];
const statuses: PlayerStatus[] = [
  "active",
  "inactive",
  "injured",
  "reserve",
  "unknown",
];
const outcomeOrder: ImportOutcome[] = [
  "new",
  "matched",
  "changed",
  "ambiguous",
  "invalid",
  "ignored",
];

function formatError(error: unknown): UiError {
  if (error instanceof ApiError) {
    return { message: error.message, action: error.action };
  }
  return {
    message: "The player workspace could not complete that action.",
    action: "Try again. Your saved player universe should be unchanged.",
  };
}

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function outcomeCount(
  session: PlayerImportSession,
  outcome: ImportOutcome,
): number {
  return session[`${outcome}_count` as keyof PlayerImportSession] as number;
}

function isManualDecision(row: ImportRow): boolean {
  return row.reason_code.startsWith("IMPORT.PLAYER.MANUAL_");
}

function EditPlayerDialog({
  player,
  saving,
  onCancel,
  onSave,
}: {
  player: Player;
  saving: boolean;
  onCancel: () => void;
  onSave: (patch: PlayerPatch) => Promise<void>;
}) {
  const [displayName, setDisplayName] = useState(player.display_name);
  const [team, setTeam] = useState(player.team ?? "");
  const [position, setPosition] = useState<PlayerPosition>(
    player.primary_position,
  );
  const [status, setStatus] = useState<PlayerStatus>(player.status);
  const [rookieClass, setRookieClass] = useState(
    player.rookie_class?.toString() ?? "",
  );
  const [isRookie, setIsRookie] = useState(player.is_rookie);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSave({
      display_name: displayName,
      team: team || null,
      primary_position: position,
      fantasy_positions: [position],
      status,
      rookie_class: rookieClass ? Number(rookieClass) : null,
      is_rookie: isRookie,
    });
  }

  return (
    <dialog
      ref={dialogRef}
      className="edit-player-dialog"
      aria-labelledby="edit-player-title"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <form method="dialog" onSubmit={submit}>
        <div className="dialog-heading">
          <div>
            <p className="eyebrow">Manual correction</p>
            <h2 id="edit-player-title">Edit player presentation</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Close player editor"
            onClick={onCancel}
          >
            ×
          </button>
        </div>
        <p className="dialog-copy">
          This changes the Hub’s canonical player card. Source IDs stay protected
          and cannot be edited here.
        </p>
        <div className="edit-player-grid">
          <label>
            Display name
            <input
              required
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
            />
          </label>
          <label>
            NFL team
            <input
              value={team}
              maxLength={8}
              placeholder="FA"
              onChange={(event) => setTeam(event.target.value.toUpperCase())}
            />
          </label>
          <label>
            Position
            <select
              value={position}
              onChange={(event) =>
                setPosition(event.target.value as PlayerPosition)
              }
            >
              {[...positions, "UNKNOWN" as const].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            Status
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value as PlayerStatus)}
            >
              {statuses.map((value) => (
                <option key={value} value={value}>
                  {titleCase(value)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Rookie class
            <input
              type="number"
              min="1900"
              max="2200"
              value={rookieClass}
              placeholder="Optional"
              onChange={(event) => setRookieClass(event.target.value)}
            />
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={isRookie}
              onChange={(event) => setIsRookie(event.target.checked)}
            />
            Current rookie
          </label>
        </div>
        <div className="dialog-actions">
          <button
            className="quiet-button"
            type="button"
            onClick={onCancel}
            disabled={saving}
          >
            Cancel
          </button>
          <button className="primary-button" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save correction"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

function ImportSummary({ session }: { session: PlayerImportSession }) {
  return (
    <div className="outcome-grid" aria-label="Import outcome counts">
      {outcomeOrder.map((outcome) => (
        <div className={`outcome-card outcome-${outcome}`} key={outcome}>
          <span>{titleCase(outcome)}</span>
          <strong>{outcomeCount(session, outcome)}</strong>
        </div>
      ))}
    </div>
  );
}

export function PlayerWorkspace() {
  const [view, setView] = useState<WorkspaceView>("universe");
  const [players, setPlayers] = useState<PlayerListResponse | null>(null);
  const [session, setSession] = useState<PlayerImportSession | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [position, setPosition] = useState<PlayerPosition | "">("");
  const [status, setStatus] = useState<PlayerStatus | "">("");
  const [rookieClass, setRookieClass] = useState("");
  const [relevantOnly, setRelevantOnly] = useState(true);
  const [offset, setOffset] = useState(0);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<UiError | null>(null);
  const [outcomeFilter, setOutcomeFilter] = useState<ImportOutcome | "all">(
    "all",
  );
  const [editingPlayer, setEditingPlayer] = useState<Player | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const limit = 25;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getPlayers({
      search,
      position,
      status,
      rookieClass: rookieClass ? Number(rookieClass) : undefined,
      relevantOnly,
      limit,
      offset,
    })
      .then((response) => {
        if (active) setPlayers(response);
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
  }, [
    search,
    position,
    status,
    rookieClass,
    relevantOnly,
    offset,
    refreshVersion,
  ]);

  const visiblePreviewRows = useMemo(
    () =>
      session?.rows.filter(
        (row) => outcomeFilter === "all" || row.outcome === outcomeFilter,
      ) ?? [],
    [outcomeFilter, session],
  );

  const reviewRows = useMemo(
    () =>
      session?.rows.filter(
        (row) =>
          row.outcome === "ambiguous" ||
          row.outcome === "invalid" ||
          isManualDecision(row),
      ) ?? [],
    [session],
  );

  const unresolvedCount = session
    ? session.ambiguous_count + session.invalid_count
    : 0;

  function clearMessages() {
    setError(null);
    setNotice(null);
  }

  async function beginSafeSample() {
    clearMessages();
    setBusyAction("fixture");
    try {
      const preview = await previewPlayerFixture();
      setSession(preview);
      setOutcomeFilter("all");
      setView("preview");
      setNotice("Safe sample preview created. No canonical players changed yet.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  async function beginCsv(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    clearMessages();
    setBusyAction("csv");
    try {
      const preview = await previewPlayerCsv({
        filename: file.name,
        csv_text: await file.text(),
      });
      setSession(preview);
      setOutcomeFilter("all");
      setView("preview");
      setNotice(`${file.name} is ready for review. Nothing has been committed.`);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  async function decide(
    row: ImportRow,
    decision: MappingDecisionRequest,
  ) {
    if (!session) return;
    clearMessages();
    setBusyAction(row.id);
    try {
      setSession(await decidePlayerImportRow(session.id, row.id, decision));
      setNotice(
        decision.decision === "clear"
          ? "Decision undone. The row needs review again."
          : "Review decision saved locally.",
      );
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  async function commitImport() {
    if (!session || unresolvedCount > 0) return;
    clearMessages();
    setBusyAction("commit");
    try {
      const result = await commitPlayerImport(session.id);
      setSession(null);
      setView("universe");
      setOffset(0);
      setRefreshVersion((version) => version + 1);
      setNotice(
        `Import complete: ${result.created_players} created, ${result.updated_players} updated, ${result.ignored_rows} ignored.`,
      );
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  async function cancelImport() {
    if (!session) return;
    clearMessages();
    setBusyAction("cancel");
    try {
      await cancelPlayerImport(session.id);
      setSession(null);
      setView("universe");
      setNotice("Import preview cancelled. The player universe was not changed.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  async function savePlayerCorrection(patch: PlayerPatch) {
    if (!editingPlayer) return;
    clearMessages();
    setBusyAction("edit");
    try {
      await updatePlayer(editingPlayer.id, patch);
      setEditingPlayer(null);
      setRefreshVersion((version) => version + 1);
      setNotice("Player correction saved locally.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOffset(0);
    setSearch(searchInput.trim());
  }

  function resetFilters() {
    setSearchInput("");
    setSearch("");
    setPosition("");
    setStatus("");
    setRookieClass("");
    setRelevantOnly(true);
    setOffset(0);
  }

  return (
    <section className="player-workspace" aria-labelledby="players-title">
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">V1 · Player identity</p>
          <h2 id="players-title">Player Universe</h2>
          <p>
            One canonical player card powers every future board, comparison, and
            draft pick. Suggestions remain unconfirmed until you approve them.
          </p>
        </div>
        <span className="privacy-pill">Private · local database</span>
      </div>

      <nav className="workspace-tabs" aria-label="Player workspace views">
        <button
          type="button"
          aria-current={view === "universe" ? "page" : undefined}
          onClick={() => setView("universe")}
        >
          Player Universe
        </button>
        <button
          type="button"
          disabled={!session}
          aria-current={view === "preview" ? "page" : undefined}
          onClick={() => setView("preview")}
        >
          Import Preview
        </button>
        <button
          type="button"
          disabled={!session}
          aria-current={view === "review" ? "page" : undefined}
          onClick={() => setView("review")}
        >
          Needs Review
          {session && <span>{unresolvedCount}</span>}
        </button>
      </nav>

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

      {view === "universe" && (
        <>
          <div className="player-actions">
            <div>
              <button
                className="primary-button"
                type="button"
                onClick={beginSafeSample}
                disabled={busyAction !== null}
              >
                {busyAction === "fixture" ? "Preparing…" : "Load safe sample"}
              </button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={busyAction !== null}
              >
                {busyAction === "csv" ? "Reading CSV…" : "Import CSV"}
              </button>
              <input
                ref={fileInputRef}
                className="visually-hidden"
                type="file"
                accept=".csv,text/csv"
                aria-label="Choose player CSV"
                onChange={beginCsv}
              />
            </div>
            <a className="quiet-link" href={getPlayerExportUrl()} download>
              Export canonical CSV
            </a>
          </div>

          <form className="player-filters" onSubmit={submitSearch}>
            <label className="search-field">
              Search canonical players
              <span>
                <input
                  type="search"
                  value={searchInput}
                  placeholder="Name or suffix"
                  onChange={(event) => setSearchInput(event.target.value)}
                />
                <button className="quiet-button" type="submit">
                  Search
                </button>
              </span>
            </label>
            <label>
              Position
              <select
                value={position}
                onChange={(event) => {
                  setPosition(event.target.value as PlayerPosition | "");
                  setOffset(0);
                }}
              >
                <option value="">All positions</option>
                {positions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Status
              <select
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value as PlayerStatus | "");
                  setOffset(0);
                }}
              >
                <option value="">All statuses</option>
                {statuses.map((value) => (
                  <option key={value} value={value}>
                    {titleCase(value)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Rookie class
              <input
                type="number"
                min="1900"
                max="2200"
                value={rookieClass}
                placeholder="Any year"
                onChange={(event) => {
                  setRookieClass(event.target.value);
                  setOffset(0);
                }}
              />
            </label>
            <label className="checkbox-field filter-checkbox">
              <input
                type="checkbox"
                checked={relevantOnly}
                onChange={(event) => {
                  setRelevantOnly(event.target.checked);
                  setOffset(0);
                }}
              />
              Relevant pool only
            </label>
            <button className="text-button" type="button" onClick={resetFilters}>
              Reset filters
            </button>
          </form>

          <div className="result-heading">
            <div>
              <p className="eyebrow">Canonical records</p>
              <h3>
                {loading ? "Loading players…" : `${players?.total ?? 0} players`}
              </h3>
            </div>
            <p>SQLite is authoritative · source IDs remain private</p>
          </div>

          {!loading && players?.items.length === 0 ? (
            <div className="empty-player-state">
              <span aria-hidden="true">FN</span>
              <h3>No players match this view.</h3>
              <p>
                Load the fictional safe sample, import a CSV, or reset the
                filters. Nothing is sent to a cloud service.
              </p>
              <button
                className="primary-button"
                type="button"
                onClick={beginSafeSample}
                disabled={busyAction !== null}
              >
                Load safe player sample
              </button>
            </div>
          ) : (
            <div className="player-table-wrap" aria-busy={loading}>
              <table className="player-table">
                <caption className="visually-hidden">
                  Canonical player universe
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Player</th>
                    <th scope="col">Position</th>
                    <th scope="col">Team</th>
                    <th scope="col">Status</th>
                    <th scope="col">Rookie class</th>
                    <th scope="col">
                      <span className="visually-hidden">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {players?.items.map((player) => (
                    <tr key={player.id}>
                      <th data-label="Player" scope="row">
                        <span className="player-name">{player.display_name}</span>
                        <span className="player-flags">
                          {player.relevant && <em>Relevant</em>}
                          {player.is_rookie && <em>Rookie</em>}
                        </span>
                      </th>
                      <td data-label="Position">
                        <span className="position-chip">
                          {player.primary_position}
                        </span>
                      </td>
                      <td data-label="Team">{player.team ?? "FA"}</td>
                      <td data-label="Status">{titleCase(player.status)}</td>
                      <td data-label="Rookie class">
                        {player.rookie_class ?? "—"}
                      </td>
                      <td data-label="Action">
                        <button
                          className="text-button"
                          type="button"
                          onClick={() => setEditingPlayer(player)}
                        >
                          Edit
                          <span className="visually-hidden">
                            {" "}
                            {player.display_name}
                          </span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {players && players.total > 0 && (
            <div className="pagination" aria-label="Player results pagination">
              <button
                className="quiet-button"
                type="button"
                disabled={offset === 0 || loading}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </button>
              <span>
                {offset + 1}–{Math.min(offset + limit, players.total)} of{" "}
                {players.total}
              </span>
              <button
                className="quiet-button"
                type="button"
                disabled={offset + limit >= players.total || loading}
                onClick={() => setOffset(offset + limit)}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}

      {view === "preview" && session && (
        <div className="import-view">
          <div className="import-callout">
            <div>
              <p className="eyebrow">Review before commit</p>
              <h3>Nothing has changed in your player universe yet.</h3>
              <p>
                This persisted preview can be inspected, corrected, cancelled,
                or committed as one local database transaction.
              </p>
            </div>
            <span>{session.filename ?? titleCase(session.source)}</span>
          </div>
          <ImportSummary session={session} />
          <div className="preview-filter">
            <label>
              Show outcomes
              <select
                value={outcomeFilter}
                onChange={(event) =>
                  setOutcomeFilter(
                    event.target.value as ImportOutcome | "all",
                  )
                }
              >
                <option value="all">All rows</option>
                {outcomeOrder.map((outcome) => (
                  <option key={outcome} value={outcome}>
                    {titleCase(outcome)} ({outcomeCount(session, outcome)})
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="player-table-wrap">
            <table className="player-table import-table">
              <caption className="visually-hidden">Import preview rows</caption>
              <thead>
                <tr>
                  <th scope="col">Row</th>
                  <th scope="col">Source player</th>
                  <th scope="col">Position</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Explanation</th>
                </tr>
              </thead>
              <tbody>
                {visiblePreviewRows.map((row) => (
                  <tr key={row.id}>
                    <td data-label="Row">{row.row_number}</td>
                    <th data-label="Source player" scope="row">
                      {row.source_name ?? "Unreadable row"}
                    </th>
                    <td data-label="Position">
                      {row.candidate?.primary_position ?? "—"}
                    </td>
                    <td data-label="Outcome">
                      <span className={`outcome-badge outcome-${row.outcome}`}>
                        {titleCase(row.outcome)}
                      </span>
                    </td>
                    <td data-label="Explanation">{row.explanation}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="import-actions">
            <button
              className="quiet-button"
              type="button"
              onClick={cancelImport}
              disabled={busyAction !== null}
            >
              {busyAction === "cancel" ? "Cancelling…" : "Cancel preview"}
            </button>
            {unresolvedCount > 0 && (
              <button
                className="secondary-button"
                type="button"
                onClick={() => setView("review")}
              >
                Review {unresolvedCount} unresolved
              </button>
            )}
            <button
              className="primary-button"
              type="button"
              disabled={unresolvedCount > 0 || busyAction !== null}
              onClick={commitImport}
            >
              {busyAction === "commit" ? "Committing…" : "Commit import"}
            </button>
          </div>
        </div>
      )}

      {view === "review" && session && (
        <div className="review-view">
          <div className="review-heading">
            <div>
              <p className="eyebrow">Human decision required</p>
              <h3>
                {unresolvedCount === 0
                  ? "Every row is resolved."
                  : `${unresolvedCount} rows still need your call.`}
              </h3>
              <p>
                A name resemblance is scouting evidence, not proof of identity.
                The Hub never accepts an uncertain match for you.
              </p>
            </div>
            <button
              className="secondary-button"
              type="button"
              onClick={() => setView("preview")}
            >
              Back to full preview
            </button>
          </div>

          {reviewRows.length === 0 ? (
            <div className="review-complete">
              <strong>Review complete</strong>
              <span>The import is ready for its final preview and commit.</span>
            </div>
          ) : (
            <div className="review-list">
              {reviewRows.map((row) => {
                const manual = isManualDecision(row);
                return (
                  <article className="review-card" key={row.id}>
                    <div className="review-card-heading">
                      <div>
                        <span className="row-number">Row {row.row_number}</span>
                        <h4>{row.source_name ?? "Unreadable source row"}</h4>
                        <p>{row.explanation}</p>
                      </div>
                      <span
                        className={`outcome-badge outcome-${row.outcome}`}
                      >
                        {manual ? "Decision saved" : titleCase(row.outcome)}
                      </span>
                    </div>

                    {row.candidate && (
                      <dl className="normalized-candidate">
                        <div>
                          <dt>Normalized name</dt>
                          <dd>{row.candidate.display_name}</dd>
                        </div>
                        <div>
                          <dt>Position</dt>
                          <dd>{row.candidate.primary_position}</dd>
                        </div>
                        <div>
                          <dt>Team</dt>
                          <dd>{row.candidate.team ?? "Unknown"}</dd>
                        </div>
                      </dl>
                    )}

                    {!manual && row.candidate_players.length > 0 && (
                      <div className="candidate-grid">
                        {row.candidate_players.map((candidate) => (
                          <section className="candidate-card" key={candidate.id}>
                            <span>Unconfirmed suggestion</span>
                            <h5>{candidate.display_name}</h5>
                            <p>
                              {candidate.primary_position} ·{" "}
                              {candidate.team ?? "FA"} ·{" "}
                              {titleCase(candidate.status)}
                            </p>
                            <button
                              className="secondary-button"
                              type="button"
                              disabled={busyAction === row.id}
                              onClick={() =>
                                decide(row, {
                                  decision: "match_existing",
                                  player_id: candidate.id,
                                })
                              }
                            >
                              Match this player
                            </button>
                          </section>
                        ))}
                      </div>
                    )}

                    <div className="review-actions">
                      {manual ? (
                        <button
                          className="quiet-button"
                          type="button"
                          disabled={busyAction === row.id}
                          onClick={() => decide(row, { decision: "clear" })}
                        >
                          Undo decision
                        </button>
                      ) : (
                        <>
                          {row.candidate && (
                            <button
                              className="quiet-button"
                              type="button"
                              disabled={busyAction === row.id}
                              onClick={() =>
                                decide(row, { decision: "create_new" })
                              }
                            >
                              Create new player
                            </button>
                          )}
                          <button
                            className="text-button danger-text"
                            type="button"
                            disabled={busyAction === row.id}
                            onClick={() => decide(row, { decision: "ignore" })}
                          >
                            Ignore row
                          </button>
                        </>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          <div className="import-actions review-footer">
            <span>
              {unresolvedCount > 0
                ? "Commit stays locked until every row is resolved."
                : "All decisions are reversible until you commit."}
            </span>
            <button
              className="primary-button"
              type="button"
              disabled={unresolvedCount > 0 || busyAction !== null}
              onClick={commitImport}
            >
              {busyAction === "commit" ? "Committing…" : "Commit import"}
            </button>
          </div>
        </div>
      )}

      {editingPlayer && (
        <EditPlayerDialog
          player={editingPlayer}
          saving={busyAction === "edit"}
          onCancel={() => setEditingPlayer(null)}
          onSave={savePlayerCorrection}
        />
      )}
    </section>
  );
}
