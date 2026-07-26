import {
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  ApiError,
  type Board,
  type BoardCreate,
  type BoardEntryPatch,
  type BoardListResponse,
  type BoardTierCreate,
  type PlayerListResponse,
  addBoardEntry,
  addBoardTier,
  createBoard,
  getBoard,
  getBoardExportUrl,
  getBoards,
  getPlayers,
  removeBoardEntry,
  removeBoardTier,
  reorderBoard,
  updateBoard,
  updateBoardEntry,
  updateBoardTier,
} from "../../api/client";

type BoardSummary = BoardListResponse["items"][number];
type BoardEntry = Board["entries"][number];
type BoardTier = Board["tiers"][number];
type UiError = { message: string; action?: string };

function formatError(error: unknown): UiError {
  if (error instanceof ApiError) {
    return { message: error.message, action: error.action };
  }
  return {
    message: "The personal board could not complete that action.",
    action: "Try again. Your saved board should be unchanged.",
  };
}

function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function useModalDialog() {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return dialogRef;
}

function CreateBoardDialog({
  onCancel,
  onCreate,
  saving,
}: {
  onCancel: () => void;
  onCreate: (payload: BoardCreate) => Promise<void>;
  saving: boolean;
}) {
  const dialogRef = useModalDialog();
  const [name, setName] = useState("Dynasty Startup Board");
  const [description, setDescription] = useState(
    "My authoritative player order for this draft room.",
  );
  const [scope, setScope] = useState<BoardCreate["scope"]>("overall");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onCreate({ name, description, scope, league_profile_id: null });
  }

  return (
    <dialog
      ref={dialogRef}
      className="board-dialog"
      aria-labelledby="create-board-title"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <form onSubmit={submit}>
        <div className="dialog-heading">
          <div>
            <p className="eyebrow">New scouting room</p>
            <h2 id="create-board-title">Create a personal board</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Close board creator"
            onClick={onCancel}
          >
            ×
          </button>
        </div>
        <p className="dialog-copy">
          Build separate overall, rookie, or veteran boards without mixing their
          order or notes.
        </p>
        <div className="board-dialog-fields">
          <label>
            Board name
            <input
              autoFocus
              required
              maxLength={200}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            Board scope
            <select
              value={scope}
              onChange={(event) =>
                setScope(event.target.value as BoardCreate["scope"])
              }
            >
              <option value="overall">Overall</option>
              <option value="rookie">Rookie</option>
              <option value="veteran">Veteran</option>
            </select>
          </label>
          <label className="board-description-field">
            Description
            <textarea
              maxLength={2000}
              rows={3}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
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
            {saving ? "Creating…" : "Create board"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

function TierDialog({
  tier,
  saving,
  onCancel,
  onSave,
  onRemove,
}: {
  tier: BoardTier | null;
  saving: boolean;
  onCancel: () => void;
  onSave: (payload: BoardTierCreate) => Promise<void>;
  onRemove: (() => Promise<void>) | null;
}) {
  const dialogRef = useModalDialog();
  const [name, setName] = useState(tier?.name ?? "Tier 1");
  const [color, setColor] = useState(tier?.color ?? "#A8FF60");
  const [confirmRemove, setConfirmRemove] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSave({
      name,
      color: color || null,
      tier_order: tier?.tier_order,
    });
  }

  return (
    <dialog
      ref={dialogRef}
      className="board-dialog tier-dialog"
      aria-labelledby="tier-dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <form onSubmit={submit}>
        <div className="dialog-heading">
          <div>
            <p className="eyebrow">Board structure</p>
            <h2 id="tier-dialog-title">{tier ? "Edit tier" : "Add a tier"}</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Close tier editor"
            onClick={onCancel}
          >
            ×
          </button>
        </div>
        <div className="board-dialog-fields tier-dialog-fields">
          <label>
            Tier name
            <input
              autoFocus
              required
              maxLength={80}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            Tier color
            <span className="color-input-row">
              <input
                type="color"
                value={color || "#A8FF60"}
                onChange={(event) => setColor(event.target.value.toUpperCase())}
              />
              <input
                aria-label="Tier color value"
                maxLength={32}
                value={color}
                onChange={(event) => setColor(event.target.value)}
              />
            </span>
          </label>
        </div>
        {confirmRemove ? (
          <div className="confirmation-panel" role="alert">
            <p>
              Remove this tier? Players stay on the board and become unassigned.
            </p>
            <div>
              <button
                className="quiet-button"
                type="button"
                onClick={() => setConfirmRemove(false)}
              >
                Keep tier
              </button>
              <button
                className="quiet-button danger-text"
                type="button"
                disabled={saving}
                onClick={() => void onRemove?.()}
              >
                {saving ? "Removing…" : "Remove tier"}
              </button>
            </div>
          </div>
        ) : (
          <div className="dialog-actions dialog-actions-split">
            {onRemove ? (
              <button
                className="text-button danger-text"
                type="button"
                onClick={() => setConfirmRemove(true)}
              >
                Remove tier
              </button>
            ) : (
              <span />
            )}
            <div>
              <button
                className="quiet-button"
                type="button"
                onClick={onCancel}
                disabled={saving}
              >
                Cancel
              </button>
              <button className="primary-button" type="submit" disabled={saving}>
                {saving ? "Saving…" : tier ? "Save tier" : "Add tier"}
              </button>
            </div>
          </div>
        )}
      </form>
    </dialog>
  );
}

function EntryDialog({
  entry,
  tiers,
  saving,
  onCancel,
  onSave,
  onRemove,
}: {
  entry: BoardEntry;
  tiers: BoardTier[];
  saving: boolean;
  onCancel: () => void;
  onSave: (payload: BoardEntryPatch) => Promise<void>;
  onRemove: () => Promise<void>;
}) {
  const dialogRef = useModalDialog();
  const [tierId, setTierId] = useState(entry.tier_id ?? "");
  const [note, setNote] = useState(entry.note ?? "");
  const [favorite, setFavorite] = useState(entry.favorite);
  const [confirmRemove, setConfirmRemove] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSave({
      tier_id: tierId || null,
      note: note || null,
      favorite,
    });
  }

  return (
    <dialog
      ref={dialogRef}
      className="board-dialog entry-dialog"
      aria-labelledby="entry-dialog-title"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <form onSubmit={submit}>
        <div className="dialog-heading">
          <div>
            <p className="eyebrow">Personal evaluation</p>
            <h2 id="entry-dialog-title">{entry.player.display_name}</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Close player board editor"
            onClick={onCancel}
          >
            ×
          </button>
        </div>
        <p className="dialog-copy">
          Your note, tier, favorite, and manual rank remain authoritative.
        </p>
        <div className="board-dialog-fields">
          <label>
            Tier
            <select
              autoFocus
              value={tierId}
              onChange={(event) => setTierId(event.target.value)}
            >
              <option value="">Unassigned</option>
              {tiers.map((tier) => (
                <option key={tier.id} value={tier.id}>
                  {tier.name}
                </option>
              ))}
            </select>
          </label>
          <label className="checkbox-field board-favorite-field">
            <input
              type="checkbox"
              checked={favorite}
              onChange={(event) => setFavorite(event.target.checked)}
            />
            Mark as one of my guys
          </label>
          <label className="board-description-field">
            Scouting note
            <textarea
              rows={6}
              maxLength={5000}
              placeholder="What do you believe, and where is the uncertainty?"
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
        </div>
        {confirmRemove ? (
          <div className="confirmation-panel" role="alert">
            <p>
              Remove this player from the active board? Re-adding them restores
              this note and favorite.
            </p>
            <div>
              <button
                className="quiet-button"
                type="button"
                onClick={() => setConfirmRemove(false)}
              >
                Keep player
              </button>
              <button
                className="quiet-button danger-text"
                type="button"
                disabled={saving}
                onClick={() => void onRemove()}
              >
                {saving ? "Removing…" : "Remove from board"}
              </button>
            </div>
          </div>
        ) : (
          <div className="dialog-actions dialog-actions-split">
            <button
              className="text-button danger-text"
              type="button"
              onClick={() => setConfirmRemove(true)}
            >
              Remove from board
            </button>
            <div>
              <button
                className="quiet-button"
                type="button"
                onClick={onCancel}
                disabled={saving}
              >
                Cancel
              </button>
              <button className="primary-button" type="submit" disabled={saving}>
                {saving ? "Saving…" : "Save evaluation"}
              </button>
            </div>
          </div>
        )}
      </form>
    </dialog>
  );
}

function AddPlayerDialog({
  board,
  saving,
  onCancel,
  onAdd,
}: {
  board: Board;
  saving: boolean;
  onCancel: () => void;
  onAdd: (playerId: string) => Promise<void>;
}) {
  const dialogRef = useModalDialog();
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [players, setPlayers] = useState<PlayerListResponse | null>(null);
  const [error, setError] = useState<UiError | null>(null);
  const existingIds = useMemo(
    () => new Set(board.entries.map((entry) => entry.player.id)),
    [board.entries],
  );

  useEffect(() => {
    let active = true;
    setError(null);
    getPlayers({ search, relevantOnly: true, limit: 100, offset: 0 })
      .then((response) => {
        if (active) setPlayers(response);
      })
      .catch((caught: unknown) => {
        if (active) setError(formatError(caught));
      });
    return () => {
      active = false;
    };
  }, [search]);

  const availablePlayers =
    players?.items.filter((player) => !existingIds.has(player.id)) ?? [];

  return (
    <dialog
      ref={dialogRef}
      className="board-dialog add-player-dialog"
      aria-labelledby="add-player-title"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <div className="dialog-heading">
        <div>
          <p className="eyebrow">Canonical player universe</p>
          <h2 id="add-player-title">Add a player</h2>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label="Close player picker"
          onClick={onCancel}
        >
          ×
        </button>
      </div>
      <form
        className="board-player-search"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(searchInput);
        }}
      >
        <label>
          Search relevant players
          <span>
            <input
              autoFocus
              type="search"
              placeholder="Name or suffix"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
            />
            <button className="quiet-button" type="submit">
              Search
            </button>
          </span>
        </label>
      </form>
      {error && (
        <div className="notice notice-error" role="alert">
          <strong>{error.message}</strong>
          {error.action && <span>{error.action}</span>}
        </div>
      )}
      <div className="player-picker-list">
        {players === null ? (
          <div className="picker-empty-state">
            <strong>Loading the local player universe...</strong>
          </div>
        ) : players.total === 0 ? (
          <div className="picker-empty-state">
            <strong>No canonical players are available yet.</strong>
            <span>Import players in the Player Universe first.</span>
          </div>
        ) : availablePlayers.length === 0 ? (
          <div className="picker-empty-state">
            <strong>Every matching player is already on this board.</strong>
            <span>Search another name or close the picker.</span>
          </div>
        ) : (
          availablePlayers.map((player) => (
            <article className="player-picker-card" key={player.id}>
              <div>
                <strong>{player.display_name}</strong>
                <span>
                  {player.primary_position} · {player.team ?? "FA"} ·{" "}
                  {titleCase(player.status)}
                </span>
              </div>
              <button
                className="secondary-button"
                type="button"
                disabled={saving}
                onClick={() => void onAdd(player.id)}
              >
                {saving ? "Adding…" : "Add"}
                <span className="visually-hidden"> {player.display_name}</span>
              </button>
            </article>
          ))
        )}
      </div>
    </dialog>
  );
}

export function BoardWorkspace() {
  const [boards, setBoards] = useState<BoardSummary[]>([]);
  const [selectedBoardId, setSelectedBoardId] = useState<string | null>(null);
  const [board, setBoard] = useState<Board | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<UiError | null>(null);
  const [showCreateBoard, setShowCreateBoard] = useState(false);
  const [showPlayerPicker, setShowPlayerPicker] = useState(false);
  const [editingTier, setEditingTier] = useState<BoardTier | "new" | null>(null);
  const [editingEntry, setEditingEntry] = useState<BoardEntry | null>(null);
  const [confirmArchive, setConfirmArchive] = useState(false);

  async function refreshBoardList(preferredBoardId?: string) {
    const response = await getBoards(includeArchived);
    setBoards(response.items);
    const requestedId = preferredBoardId ?? selectedBoardId;
    const nextId =
      response.items.find((item) => item.id === requestedId)?.id ??
      response.items[0]?.id ??
      null;
    setSelectedBoardId(nextId);
    if (!nextId) setBoard(null);
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    getBoards(includeArchived)
      .then((response) => {
        if (!active) return;
        setBoards(response.items);
        setSelectedBoardId((current) => {
          if (response.items.some((item) => item.id === current)) return current;
          return response.items[0]?.id ?? null;
        });
        if (response.items.length === 0) setBoard(null);
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
  }, [includeArchived]);

  useEffect(() => {
    if (!selectedBoardId) return;
    let active = true;
    setLoading(true);
    setBoard(null);
    setError(null);
    getBoard(selectedBoardId)
      .then((response) => {
        if (active) setBoard(response);
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

  async function runBoardMutation(
    actionName: string,
    mutation: () => Promise<Board>,
    successMessage: string,
  ): Promise<boolean> {
    clearMessages();
    setBusyAction(actionName);
    try {
      const updated = await mutation();
      setBoard(updated);
      setNotice(successMessage);
      try {
        await refreshBoardList(updated.id);
      } catch (refreshError) {
        setError(formatError(refreshError));
      }
      return true;
    } catch (caught) {
      setError(formatError(caught));
      return false;
    } finally {
      setBusyAction(null);
    }
  }

  async function createNewBoard(payload: BoardCreate) {
    clearMessages();
    setBusyAction("create-board");
    try {
      const created = await createBoard(payload);
      setBoard(created);
      setSelectedBoardId(created.id);
      setShowCreateBoard(false);
      setNotice("Personal board created locally.");
      await refreshBoardList(created.id);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  async function saveTier(payload: BoardTierCreate) {
    if (!board || !editingTier) return;
    const existingTier = editingTier === "new" ? null : editingTier;
    const saved = await runBoardMutation(
      "tier",
      () =>
        existingTier
          ? updateBoardTier(board.id, existingTier.id, payload)
          : addBoardTier(board.id, payload),
      existingTier ? "Tier updated." : "Tier added.",
    );
    if (saved) setEditingTier(null);
  }

  async function deleteTier() {
    if (!board || !editingTier || editingTier === "new") return;
    const removed = await runBoardMutation(
      "tier",
      () => removeBoardTier(board.id, editingTier.id),
      "Tier removed. Its players are still on the board.",
    );
    if (removed) setEditingTier(null);
  }

  async function addPlayer(playerId: string) {
    if (!board) return;
    const added = await runBoardMutation(
      "add-player",
      () => addBoardEntry(board.id, { player_id: playerId }),
      "Player added to the end of your board.",
    );
    if (added) setShowPlayerPicker(false);
  }

  async function saveEntry(payload: BoardEntryPatch) {
    if (!board || !editingEntry) return;
    const saved = await runBoardMutation(
      "entry",
      () => updateBoardEntry(board.id, editingEntry.id, payload),
      "Player evaluation saved locally.",
    );
    if (saved) setEditingEntry(null);
  }

  async function deleteEntry() {
    if (!board || !editingEntry) return;
    const removed = await runBoardMutation(
      "entry",
      () => removeBoardEntry(board.id, editingEntry.id),
      "Player removed. Re-adding them will restore this evaluation.",
    );
    if (removed) setEditingEntry(null);
  }

  async function toggleFavorite(entry: BoardEntry) {
    if (!board) return;
    await runBoardMutation(
      `favorite-${entry.id}`,
      () =>
        updateBoardEntry(board.id, entry.id, {
          favorite: !entry.favorite,
        }),
      entry.favorite
        ? `${entry.player.display_name} removed from My Guys.`
        : `${entry.player.display_name} marked as one of My Guys.`,
    );
  }

  async function moveEntry(index: number, direction: -1 | 1) {
    if (!board) return;
    const target = index + direction;
    if (target < 0 || target >= board.entries.length) return;
    const playerIds = board.entries.map((entry) => entry.player.id);
    [playerIds[index], playerIds[target]] = [playerIds[target], playerIds[index]];
    await runBoardMutation(
      "order",
      () => reorderBoard(board.id, { player_ids: playerIds }),
      "Manual board order saved.",
    );
  }

  async function archiveOrRestoreBoard() {
    if (!board) return;
    const willArchive = !board.archived;
    clearMessages();
    setBusyAction("archive");
    try {
      const updated = await updateBoard(board.id, { archived: willArchive });
      setConfirmArchive(false);
      setNotice(
        willArchive
          ? "Board archived with all work preserved."
          : "Board restored.",
      );
      if (willArchive && !includeArchived) {
        await refreshBoardList();
      } else {
        setBoard(updated);
        await refreshBoardList(updated.id);
      }
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusyAction(null);
    }
  }

  const tierById = useMemo(
    () => new Map(board?.tiers.map((tier) => [tier.id, tier]) ?? []),
    [board?.tiers],
  );
  const favoriteCount =
    board?.entries.filter((entry) => entry.favorite).length ?? 0;

  return (
    <section className="board-workspace" aria-labelledby="board-workspace-title">
      <div className="workspace-heading board-workspace-heading">
        <div>
          <p className="eyebrow">Phase 2 · Personal conviction</p>
          <h2 id="board-workspace-title">Personal Boards</h2>
          <p>
            Your order is the depth chart. Tiers, notes, and future Gut ELO
            suggestions support it; they never replace it.
          </p>
        </div>
        <span className="privacy-pill">Private · saved locally</span>
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

      <div className="board-layout">
        <aside className="board-sidebar" aria-label="Personal boards">
          <div className="board-sidebar-heading">
            <div>
              <span>Board room</span>
              <strong>{boards.length}</strong>
            </div>
            <button
              className="icon-button"
              type="button"
              aria-label="Create personal board"
              onClick={() => setShowCreateBoard(true)}
            >
              +
            </button>
          </div>
          <div className="board-list">
            {boards.map((item) => (
              <button
                type="button"
                key={item.id}
                aria-current={selectedBoardId === item.id ? "page" : undefined}
                onClick={() => setSelectedBoardId(item.id)}
              >
                <span>{item.name}</span>
                <small>
                  {titleCase(item.scope)} · {item.entry_count}{" "}
                  {item.entry_count === 1 ? "player" : "players"}
                  {item.archived ? " · Archived" : ""}
                </small>
              </button>
            ))}
          </div>
          <label className="checkbox-field board-archive-filter">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={(event) => setIncludeArchived(event.target.checked)}
            />
            Show archived boards
          </label>
        </aside>

        <div className="board-stage" aria-busy={loading}>
          {!board ? (
            <div className="empty-player-state empty-board-state">
              <span aria-hidden="true">PB</span>
              <h3>Create your first personal board.</h3>
              <p>
                Start with an overall, rookie, or veteran board. Every ranking,
                note, and favorite stays in your local database.
              </p>
              <button
                className="primary-button"
                type="button"
                onClick={() => setShowCreateBoard(true)}
              >
                Create personal board
              </button>
            </div>
          ) : (
            <>
              <div className="board-stage-heading">
                <div>
                  <div className="board-title-row">
                    <h3>{board.name}</h3>
                    <span>{titleCase(board.scope)}</span>
                    {board.archived && <span>Archived</span>}
                  </div>
                  <p>
                    {board.description ??
                      "A private, manually ordered personal board."}
                  </p>
                </div>
                <div className="board-header-actions">
                  <a
                    className="quiet-link"
                    href={getBoardExportUrl(board.id)}
                    download
                  >
                    Export CSV
                  </a>
                  {board.archived ? (
                    <button
                      className="secondary-button"
                      type="button"
                      disabled={busyAction === "archive"}
                      onClick={() => void archiveOrRestoreBoard()}
                    >
                      Restore board
                    </button>
                  ) : (
                    <button
                      className="text-button danger-text"
                      type="button"
                      onClick={() => setConfirmArchive(true)}
                    >
                      Archive board
                    </button>
                  )}
                </div>
              </div>

              {confirmArchive && (
                <div className="confirmation-panel board-archive-confirm" role="alert">
                  <p>
                    Archive this board? Its tiers, order, favorites, and notes
                    remain saved and can be restored.
                  </p>
                  <div>
                    <button
                      className="quiet-button"
                      type="button"
                      onClick={() => setConfirmArchive(false)}
                    >
                      Keep active
                    </button>
                    <button
                      className="quiet-button danger-text"
                      type="button"
                      disabled={busyAction === "archive"}
                      onClick={() => void archiveOrRestoreBoard()}
                    >
                      {busyAction === "archive"
                        ? "Archiving…"
                        : "Archive board"}
                    </button>
                  </div>
                </div>
              )}

              <div className="board-stat-strip" aria-label="Board summary">
                <div>
                  <strong>{board.entry_count}</strong>
                  <span>Ranked players</span>
                </div>
                <div>
                  <strong>{board.tiers.length}</strong>
                  <span>Tiers</span>
                </div>
                <div>
                  <strong>{favoriteCount}</strong>
                  <span>My Guys</span>
                </div>
                <div>
                  <strong>Manual</strong>
                  <span>Authority</span>
                </div>
              </div>

              {!board.archived && (
                <div className="board-toolbar">
                  <div>
                    <button
                      className="primary-button"
                      type="button"
                      onClick={() => setShowPlayerPicker(true)}
                    >
                      Add player
                    </button>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => setEditingTier("new")}
                    >
                      Add tier
                    </button>
                  </div>
                  <span>Use arrows to save manual order instantly.</span>
                </div>
              )}

              <div className="tier-legend" aria-label="Board tiers">
                <div className="tier-legend-heading">
                  <strong>Tier legend</strong>
                  <span>Tier labels do not change rank.</span>
                </div>
                <div>
                  {board.tiers.map((tier) => (
                    <button
                      type="button"
                      key={tier.id}
                      disabled={board.archived}
                      onClick={() => setEditingTier(tier)}
                    >
                      <span
                        className="tier-color"
                        style={{ backgroundColor: tier.color ?? "#476154" }}
                        aria-hidden="true"
                      />
                      {tier.name}
                    </button>
                  ))}
                  {board.tiers.length === 0 && (
                    <span className="muted-copy">
                      No tiers yet. Players can remain unassigned.
                    </span>
                  )}
                </div>
              </div>

              {board.entries.length === 0 ? (
                <div className="empty-player-state board-entry-empty">
                  <span aria-hidden="true">01</span>
                  <h3>Your board is ready for its first player.</h3>
                  <p>
                    Add from the canonical Player Universe. No provider IDs or
                    cloud storage enter this board.
                  </p>
                  {!board.archived && (
                    <button
                      className="primary-button"
                      type="button"
                      onClick={() => setShowPlayerPicker(true)}
                    >
                      Add first player
                    </button>
                  )}
                </div>
              ) : (
                <ol className="board-ranking-list" aria-label="Manual player order">
                  {board.entries.map((entry, index) => {
                    const tier = entry.tier_id
                      ? tierById.get(entry.tier_id)
                      : undefined;
                    return (
                      <li
                        className={entry.favorite ? "board-entry is-favorite" : "board-entry"}
                        key={entry.id}
                      >
                        <div className="board-rank" aria-label={`Rank ${entry.rank}`}>
                          {String(entry.rank).padStart(2, "0")}
                        </div>
                        <div className="board-entry-player">
                          <div>
                            <strong>{entry.player.display_name}</strong>
                            {entry.favorite && <span>My Guy</span>}
                          </div>
                          <p>
                            {entry.player.primary_position} ·{" "}
                            {entry.player.team ?? "FA"} ·{" "}
                            {titleCase(entry.player.status)}
                            {entry.player.is_rookie ? " · Rookie" : ""}
                          </p>
                        </div>
                        <div className="board-entry-tier">
                          {tier ? (
                            <span>
                              <i
                                style={{ backgroundColor: tier.color ?? "#476154" }}
                                aria-hidden="true"
                              />
                              {tier.name}
                            </span>
                          ) : (
                            <span className="unassigned-tier">Unassigned</span>
                          )}
                        </div>
                        <p className="board-entry-note">
                          {entry.note ?? "No scouting note yet."}
                        </p>
                        <div className="board-entry-actions">
                          <button
                            className="rank-button"
                            type="button"
                            aria-label={`Move ${entry.player.display_name} up`}
                            disabled={
                              board.archived ||
                              index === 0 ||
                              busyAction === "order"
                            }
                            onClick={() => void moveEntry(index, -1)}
                          >
                            ↑
                          </button>
                          <button
                            className="rank-button"
                            type="button"
                            aria-label={`Move ${entry.player.display_name} down`}
                            disabled={
                              board.archived ||
                              index === board.entries.length - 1 ||
                              busyAction === "order"
                            }
                            onClick={() => void moveEntry(index, 1)}
                          >
                            ↓
                          </button>
                          <button
                            className="favorite-button"
                            type="button"
                            aria-label={`${entry.favorite ? "Remove" : "Mark"} ${entry.player.display_name} ${entry.favorite ? "from" : "as"} My Guys`}
                            aria-pressed={entry.favorite}
                            disabled={
                              board.archived ||
                              busyAction === `favorite-${entry.id}`
                            }
                            onClick={() => void toggleFavorite(entry)}
                          >
                            ★
                          </button>
                          <button
                            className="text-button"
                            type="button"
                            disabled={board.archived}
                            onClick={() => setEditingEntry(entry)}
                          >
                            Edit
                            <span className="visually-hidden">
                              {" "}
                              {entry.player.display_name}
                            </span>
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </>
          )}
        </div>
      </div>

      {showCreateBoard && (
        <CreateBoardDialog
          saving={busyAction === "create-board"}
          onCancel={() => setShowCreateBoard(false)}
          onCreate={createNewBoard}
        />
      )}
      {board && showPlayerPicker && (
        <AddPlayerDialog
          board={board}
          saving={busyAction === "add-player"}
          onCancel={() => setShowPlayerPicker(false)}
          onAdd={addPlayer}
        />
      )}
      {board && editingTier && (
        <TierDialog
          tier={editingTier === "new" ? null : editingTier}
          saving={busyAction === "tier"}
          onCancel={() => setEditingTier(null)}
          onSave={saveTier}
          onRemove={editingTier === "new" ? null : deleteTier}
        />
      )}
      {board && editingEntry && (
        <EntryDialog
          entry={editingEntry}
          tiers={board.tiers}
          saving={busyAction === "entry"}
          onCancel={() => setEditingEntry(null)}
          onSave={saveEntry}
          onRemove={deleteEntry}
        />
      )}
    </section>
  );
}
