import { type SyntheticEvent, useState } from "react";

import {
  ApiError,
  type AlertEvidenceSnapshot,
  type AlertEvidenceSnapshotList,
  getAlertEvidenceSnapshots,
} from "../../api/client";
import {
  AlertEvidenceImportPanel,
  type AlertEvidenceDraftShape,
} from "./AlertEvidenceImportPanel";

type UiError = { message: string; action?: string };

function formatError(error: unknown): UiError {
  if (error instanceof ApiError) {
    return { message: error.message, action: error.action };
  }
  return {
    message: "Saved evidence snapshots could not be listed.",
    action: "The draft can still be created without decision support.",
  };
}

function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

export function DraftDecisionSupportSetup({
  draftShape,
  onSnapshotChange,
}: {
  draftShape: AlertEvidenceDraftShape;
  onSnapshotChange: (snapshotId: string | null) => void;
}) {
  const [snapshots, setSnapshots] =
    useState<AlertEvidenceSnapshotList | null>(null);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState("");
  const [attachEnabled, setAttachEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<UiError | null>(null);

  const selectedSnapshot = snapshots?.items.find(
    (snapshot) => snapshot.id === selectedSnapshotId,
  );

  async function loadSnapshots() {
    if (loaded || loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getAlertEvidenceSnapshots();
      setSnapshots(result);
      setSelectedSnapshotId(result.items[0]?.id ?? "");
      setLoaded(true);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setLoading(false);
    }
  }

  function handleToggle(event: SyntheticEvent<HTMLDetailsElement>) {
    if (event.currentTarget.open) void loadSnapshots();
  }

  function updateSelection(snapshotId: string, enabled = attachEnabled) {
    setSelectedSnapshotId(snapshotId);
    onSnapshotChange(enabled && snapshotId ? snapshotId : null);
  }

  function addCommittedSnapshot(snapshot: AlertEvidenceSnapshot) {
    setSnapshots((current) => ({
      items: [
        snapshot,
        ...(current?.items.filter((item) => item.id !== snapshot.id) ?? []),
      ],
      total:
        (current?.items.some((item) => item.id === snapshot.id)
          ? current.total
          : (current?.total ?? 0) + 1),
      limit: current?.limit ?? 100,
      offset: 0,
    }));
    updateSelection(snapshot.id);
  }

  return (
    <details className="draft-decision-setup" onToggle={handleToggle}>
      <summary>Decision support (optional)</summary>
      <div className="draft-decision-setup-body">
        <p>
          A draft never requires market evidence. If attached, alerts stay out
          of Blind view and cannot make a pick or trade.
        </p>

        {loading && <p role="status">Reading committed snapshots…</p>}
        {error && (
          <div className="draft-alert-error" role="alert">
            <strong>{error.message}</strong>
            {error.action && <span>{error.action}</span>}
            <button
              className="text-button"
              type="button"
              onClick={() => void loadSnapshots()}
            >
              Retry
            </button>
          </div>
        )}

        {snapshots && snapshots.items.length > 0 && (
          <>
            <label className="draft-decision-attach-toggle">
              <input
                type="checkbox"
                checked={attachEnabled}
                onChange={(event) => {
                  const enabled = event.target.checked;
                  setAttachEnabled(enabled);
                  onSnapshotChange(
                    enabled && selectedSnapshotId ? selectedSnapshotId : null,
                  );
                }}
              />
              Attach decision support when this room opens
            </label>
            <label>
              Evidence snapshot
              <select
                value={selectedSnapshotId}
                disabled={!attachEnabled}
                onChange={(event) => updateSelection(event.target.value)}
              >
                {snapshots.items.map((snapshot) => (
                  <option value={snapshot.id} key={snapshot.id}>
                    {snapshot.source_label} ·{" "}
                    {dateLabel(snapshot.source_as_of)}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}

        {loaded && snapshots?.items.length === 0 && (
          <p>No committed evidence snapshots are available yet.</p>
        )}

        {selectedSnapshot && attachEnabled && (
          <dl className="draft-decision-summary">
            <div>
              <dt>Evidence</dt>
              <dd>{selectedSnapshot.source_label}</dd>
            </div>
            <div>
              <dt>Freshness</dt>
              <dd>
                {Object.values(selectedSnapshot.freshness_states)
                  .map(titleCase)
                  .join(" · ") || "Not evaluated"}
              </dd>
            </div>
            <div>
              <dt>Compatibility</dt>
              <dd>{titleCase(selectedSnapshot.compatibility_state)}</dd>
            </div>
            <div>
              <dt>Defaults</dt>
              <dd>Top 2 tiers/favorites · 6+ spot gap · 5-pick snooze</dd>
            </div>
          </dl>
        )}

        <AlertEvidenceImportPanel
          draft={draftShape}
          onCommitted={addCommittedSnapshot}
        />
      </div>
    </details>
  );
}
