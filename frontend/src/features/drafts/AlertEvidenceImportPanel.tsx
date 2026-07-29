import { type ChangeEvent, type FormEvent, useState } from "react";

import {
  ApiError,
  type AlertEvidencePreview,
  type AlertEvidenceSnapshot,
  type DraftSession,
  commitAlertEvidence,
  previewAlertEvidence,
  saveAlertEvidenceMapping,
} from "../../api/client";

type UiError = { message: string; action?: string };
export type AlertEvidenceDraftShape = Pick<
  DraftSession,
  "team_count" | "round_count" | "draft_format" | "third_round_reversal"
>;

function formatError(error: unknown): UiError {
  if (error instanceof ApiError) {
    return { message: error.message, action: error.action };
  }
  return {
    message: "The evidence files could not be previewed.",
    action: "Check the selected CSV files and try again.",
  };
}

function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function readLocalFile(file: File): Promise<string> {
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result ?? "")));
    reader.addEventListener("error", () =>
      reject(new Error("The selected file could not be read.")),
    );
    reader.readAsText(file);
  });
}

function localDateTimeValue(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 16);
}

export function AlertEvidenceImportPanel({
  draft,
  onCommitted,
}: {
  draft: AlertEvidenceDraftShape;
  onCommitted: (snapshot: AlertEvidenceSnapshot) => void;
}) {
  const [sourceLabel, setSourceLabel] = useState("Local market snapshot");
  const [sourceKind, setSourceKind] = useState<
    "synthetic" | "user_entered" | "public" | "licensed"
  >("user_entered");
  const [asOf, setAsOf] = useState(localDateTimeValue);
  const [leagueType, setLeagueType] = useState<
    "dynasty" | "keeper" | "redraft"
  >("dynasty");
  const [draftPurpose, setDraftPurpose] = useState<
    "startup" | "rookie" | "supplemental"
  >("startup");
  const [quarterbackMode, setQuarterbackMode] = useState<
    "one_qb" | "superflex"
  >("superflex");
  const [receptionScoring, setReceptionScoring] = useState<
    "standard" | "half_ppr" | "ppr"
  >("ppr");
  const [tightEndPremium, setTightEndPremium] = useState(true);
  const [permissionConfirmed, setPermissionConfirmed] = useState(false);
  const [commitConfirmed, setCommitConfirmed] = useState(false);
  const [playerFile, setPlayerFile] = useState<File | null>(null);
  const [pickFile, setPickFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<AlertEvidencePreview | null>(null);
  const [mappingSelections, setMappingSelections] = useState<
    Record<string, string>
  >({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<UiError | null>(null);

  function invalidatePreview() {
    setPreview(null);
    setCommitConfirmed(false);
    setNotice("");
  }

  function selectFile(
    event: ChangeEvent<HTMLInputElement>,
    setter: (file: File | null) => void,
  ) {
    setter(event.target.files?.[0] ?? null);
    invalidatePreview();
  }

  async function createPreview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!playerFile) return;
    setBusy(true);
    setError(null);
    setNotice("");
    try {
      const [playerCsvText, pickCsvText] = await Promise.all([
        readLocalFile(playerFile),
        pickFile ? readLocalFile(pickFile) : Promise.resolve(null),
      ]);
      const result = await previewAlertEvidence({
        metadata: {
          source_label: sourceLabel,
          source_kind: sourceKind,
          source_namespace: "local_user",
          as_of: new Date(asOf).toISOString(),
          permitted_use_confirmed: permissionConfirmed,
          league_type: leagueType,
          draft_purpose: draftPurpose,
          team_count: draft.team_count,
          draft_format: draft.draft_format,
          third_round_reversal: draft.third_round_reversal,
          round_count: draft.round_count,
          quarterback_mode: quarterbackMode,
          reception_scoring: receptionScoring,
          tight_end_premium: tightEndPremium,
          supported_draft_depth: draft.team_count * draft.round_count,
        },
        player_filename: playerFile.name,
        player_csv_text: playerCsvText,
        pick_filename: pickFile?.name ?? null,
        pick_csv_text: pickCsvText,
      });
      setPreview(result);
      setCommitConfirmed(false);
      setMappingSelections({});
      setNotice("Preview created. No active evidence changed.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function decideRow(
    rowId: string,
    decision: "confirm" | "ignore",
  ) {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await saveAlertEvidenceMapping(
        preview.id,
        rowId,
        decision === "confirm"
          ? {
              decision,
              player_id: mappingSelections[rowId] || null,
            }
          : { decision },
      );
      setPreview(updated);
      setNotice("Mapping decision saved to this preview.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function commitPreview() {
    if (!preview || !commitConfirmed) return;
    setBusy(true);
    setError(null);
    try {
      const result = await commitAlertEvidence(
        preview.id,
        preview.content_hash,
      );
      setPreview({ ...preview, status: "committed" });
      setNotice(
        result.idempotent
          ? "This identical evidence snapshot was already committed."
          : "Evidence committed locally. It is now available to attach.",
      );
      onCommitted(result.snapshot);
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  const commitBlocked =
    !preview ||
    preview.status === "committed" ||
    !preview.source.permitted_use_confirmed ||
    preview.review_required_player_count > 0 ||
    preview.invalid_player_count > 0 ||
    !commitConfirmed ||
    busy;

  return (
    <details className="alert-import-panel">
      <summary>Preview / import evidence</summary>
      <form onSubmit={(event) => void createPreview(event)}>
        <p>
          Files stay on this computer. Previewing changes no attached snapshot
          or draft state.
        </p>
        <div className="alert-import-grid">
          <label>
            Source label
            <input
              required
              maxLength={200}
              value={sourceLabel}
              onChange={(event) => {
                setSourceLabel(event.target.value);
                invalidatePreview();
              }}
            />
          </label>
          <label>
            Source kind
            <select
              value={sourceKind}
              onChange={(event) => {
                setSourceKind(
                  event.target.value as
                    | "synthetic"
                    | "user_entered"
                    | "public"
                    | "licensed",
                );
                invalidatePreview();
              }}
            >
              <option value="user_entered">User entered</option>
              <option value="synthetic">Synthetic</option>
              <option value="public">Public</option>
              <option value="licensed">Licensed</option>
            </select>
          </label>
          <label>
            Evidence as of
            <input
              required
              type="datetime-local"
              value={asOf}
              onChange={(event) => {
                setAsOf(event.target.value);
                invalidatePreview();
              }}
            />
          </label>
          <label>
            League type
            <select
              value={leagueType}
              onChange={(event) => {
                setLeagueType(
                  event.target.value as "dynasty" | "keeper" | "redraft",
                );
                invalidatePreview();
              }}
            >
              <option value="dynasty">Dynasty</option>
              <option value="keeper">Keeper</option>
              <option value="redraft">Redraft</option>
            </select>
          </label>
          <label>
            Draft purpose
            <select
              value={draftPurpose}
              onChange={(event) => {
                setDraftPurpose(
                  event.target.value as
                    | "startup"
                    | "rookie"
                    | "supplemental",
                );
                invalidatePreview();
              }}
            >
              <option value="startup">Startup</option>
              <option value="rookie">Rookie</option>
              <option value="supplemental">Supplemental</option>
            </select>
          </label>
          <label>
            Quarterback mode
            <select
              value={quarterbackMode}
              onChange={(event) => {
                setQuarterbackMode(
                  event.target.value as "one_qb" | "superflex",
                );
                invalidatePreview();
              }}
            >
              <option value="superflex">Superflex</option>
              <option value="one_qb">One QB</option>
            </select>
          </label>
          <label>
            Reception scoring
            <select
              value={receptionScoring}
              onChange={(event) => {
                setReceptionScoring(
                  event.target.value as "standard" | "half_ppr" | "ppr",
                );
                invalidatePreview();
              }}
            >
              <option value="ppr">PPR</option>
              <option value="half_ppr">Half PPR</option>
              <option value="standard">Standard</option>
            </select>
          </label>
          <label className="alert-import-checkbox">
            <input
              type="checkbox"
              checked={tightEndPremium}
              onChange={(event) => {
                setTightEndPremium(event.target.checked);
                invalidatePreview();
              }}
            />
            Tight end premium
          </label>
          <label>
            Player-signal CSV
            <input
              required
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => selectFile(event, setPlayerFile)}
            />
          </label>
          <label>
            Pick-value CSV (optional)
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => selectFile(event, setPickFile)}
            />
          </label>
        </div>
        <label className="alert-import-permission">
          <input
            type="checkbox"
            checked={permissionConfirmed}
            onChange={(event) => {
              setPermissionConfirmed(event.target.checked);
              invalidatePreview();
            }}
          />
          I confirm I am permitted to use these files locally for this draft.
        </label>
        <button
          className="secondary-button"
          type="submit"
          disabled={busy || !playerFile}
        >
          {busy ? "Reading files…" : "Preview evidence"}
        </button>
      </form>

      {error && (
        <div className="draft-alert-error" role="alert">
          <strong>{error.message}</strong>
          {error.action && <span>{error.action}</span>}
        </div>
      )}
      {notice && <p className="alert-import-notice" role="status">{notice}</p>}

      {preview && (
        <section className="alert-import-preview">
          <header>
            <div>
              <span>Preview only</span>
              <strong>{preview.source.label}</strong>
            </div>
            <span>{titleCase(preview.status)}</span>
          </header>
          <dl>
            <div>
              <dt>Matched</dt>
              <dd>{preview.matched_player_count}</dd>
            </div>
            <div>
              <dt>Review</dt>
              <dd>{preview.review_required_player_count}</dd>
            </div>
            <div>
              <dt>Unmatched</dt>
              <dd>{preview.unmatched_player_count}</dd>
            </div>
            <div>
              <dt>Pick curve</dt>
              <dd>{preview.pick_curve_available ? "Available" : "Unavailable"}</dd>
            </div>
          </dl>

          {preview.warnings.length > 0 && (
            <div className="alert-import-warnings">
              <strong>Preview warnings</strong>
              <ul>
                {preview.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}

          {preview.rows
            .filter((row) =>
              ["review_required", "unmatched"].includes(row.status),
            )
            .map((row) => (
              <div className="alert-import-mapping" key={row.id}>
                <div>
                  <strong>{row.display_name}</strong>
                  <span>
                    {row.position} · {row.team ?? "FA"} ·{" "}
                    {titleCase(row.status)}
                  </span>
                </div>
                {row.candidates.length > 0 && (
                  <select
                    aria-label={`Match ${row.display_name}`}
                    value={mappingSelections[row.id] ?? ""}
                    onChange={(event) =>
                      setMappingSelections((current) => ({
                        ...current,
                        [row.id]: event.target.value,
                      }))
                    }
                  >
                    <option value="">Choose player</option>
                    {row.candidates.map((candidate) => (
                      <option value={candidate.id} key={candidate.id}>
                        {candidate.display_name} · {candidate.position} ·{" "}
                        {candidate.team ?? "FA"}
                      </option>
                    ))}
                  </select>
                )}
                <div>
                  {row.candidates.length > 0 && (
                    <button
                      className="quiet-button"
                      type="button"
                      disabled={busy || !mappingSelections[row.id]}
                      onClick={() => void decideRow(row.id, "confirm")}
                    >
                      Confirm match
                    </button>
                  )}
                  <button
                    className="text-button"
                    type="button"
                    disabled={busy}
                    onClick={() => void decideRow(row.id, "ignore")}
                  >
                    Ignore row
                  </button>
                </div>
              </div>
            ))}

          <div className="alert-import-commit">
            <label>
              <input
                type="checkbox"
                checked={commitConfirmed}
                disabled={
                  preview.status === "committed" ||
                  !preview.source.permitted_use_confirmed
                }
                onChange={(event) => setCommitConfirmed(event.target.checked)}
              />
              Commit this exact preview as an immutable local snapshot.
            </label>
            {!preview.source.permitted_use_confirmed && (
              <p>
                Check the permitted-use confirmation above and create a new
                preview before commit.
              </p>
            )}
            <button
              className="primary-button"
              type="button"
              disabled={commitBlocked}
              onClick={() => void commitPreview()}
            >
              Commit evidence
            </button>
          </div>
        </section>
      )}
    </details>
  );
}
