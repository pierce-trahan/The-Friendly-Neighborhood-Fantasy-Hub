import {
  type KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  ApiError,
  type AlertDetail,
  type AlertEvent,
  type AlertEvidenceSnapshotList,
  type AlertGroup,
  type DraftAlertConfiguration,
  type DraftAlertList,
  type DraftSession,
  attachDraftAlertConfiguration,
  evaluateDraftAlerts,
  getAlertEvidenceSnapshots,
  getDraftAlert,
  getDraftAlertConfiguration,
  getDraftAlerts,
  updateDraftAlertConfiguration,
  updateDraftAlertStatus,
} from "../../api/client";
import { AlertEvidenceImportPanel } from "./AlertEvidenceImportPanel";

type UiError = { message: string; action?: string };
type LoadState = "loading" | "ready" | "missing" | "error";

function formatError(error: unknown): UiError {
  if (error instanceof ApiError) {
    return { message: error.message, action: error.action };
  }
  return {
    message: "Decision support could not refresh.",
    action: "The draft room is still safe. Retry from the alert rail.",
  };
}

function titleCase(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function kindLabel(kind: AlertEvent["kind"]): string {
  if (kind === "value_watch") return "Value watch";
  if (kind === "return_risk") return "Return risk";
  if (kind === "trade_up_window") return "Trade-up window";
  return "Evidence warning";
}

function rangeLabel(
  range: { low: number; high: number } | null,
  unit = "pick",
): string {
  if (!range) return "Unavailable";
  if (range.low === range.high) return `${unit} ${range.low}`;
  return `${unit}s ${range.low}–${range.high}`;
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function personalReason(event: AlertEvent): string {
  const reason = event.evidence.personal_reason;
  const parts: string[] = [];
  if (reason.favorite) parts.push("favorite");
  if (reason.tier_order !== null) parts.push(`tier ${reason.tier_order}`);
  if (reason.manual_rank !== null) parts.push(`personal rank ${reason.manual_rank}`);
  return parts.length > 0
    ? `Your board: ${parts.join(" · ")}`
    : "Your board qualified this player";
}

function evidenceHeadline(event: AlertEvent): string {
  if (event.kind === "value_watch" && event.evidence.market_gap) {
    return `Conservative gap: ${rangeLabel(event.evidence.market_gap, "spot")}`;
  }
  if (event.kind === "return_risk") {
    return `Return outlook: ${titleCase(event.evidence.return_risk)}`;
  }
  if (event.kind === "trade_up_window") {
    return `Target window: ${rangeLabel(event.evidence.target_pick_window)}`;
  }
  return "Evidence needs attention";
}

function strongestLimitation(event: AlertEvent): string {
  const code =
    event.limitation_codes[0] ?? event.evidence.limitation_codes[0] ?? null;
  return code
    ? titleCase(code)
    : "This is decision support, not a player value verdict.";
}

function formatCompatibility(
  configuration: DraftAlertConfiguration,
): string {
  return titleCase(configuration.format_compatibility);
}

function isFormField(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    target instanceof HTMLButtonElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  );
}

function eventForGroup(group: AlertGroup, focusedEventId: string | null) {
  return (
    group.events.find((event) => event.id === focusedEventId) ??
    group.events[0] ??
    null
  );
}

function AlertCard({
  group,
  focusedEventId,
  busy,
  onFocus,
  onInspect,
  onSnooze,
  onDismiss,
  onReopen,
  cardRef,
}: {
  group: AlertGroup;
  focusedEventId: string | null;
  busy: boolean;
  onFocus: (eventId: string) => void;
  onInspect: (eventId: string) => void;
  onSnooze: (eventId: string) => void;
  onDismiss: (eventId: string) => void;
  onReopen: (event: AlertEvent) => void;
  cardRef: (node: HTMLElement | null) => void;
}) {
  const event = eventForGroup(group, focusedEventId);
  if (!event) return null;
  const contextualComponents = Object.entries(event.evidence.components).filter(
    ([name, component]) =>
      ["win_now_production", "production", "age_risk", "strategy_fit"].includes(
        name,
      ) &&
      component.state === "available" &&
      component.band,
  );

  return (
    <article
      className="draft-alert-card"
      ref={cardRef}
      tabIndex={0}
      onFocus={() => onFocus(event.id)}
      onKeyDown={(keyboardEvent: ReactKeyboardEvent<HTMLElement>) => {
        if (keyboardEvent.key === "ArrowRight" || keyboardEvent.key === "ArrowLeft") {
          const currentIndex = group.events.findIndex(
            (item) => item.id === event.id,
          );
          const direction = keyboardEvent.key === "ArrowRight" ? 1 : -1;
          const nextIndex = Math.max(
            0,
            Math.min(group.events.length - 1, currentIndex + direction),
          );
          const nextEvent = group.events[nextIndex];
          if (nextEvent) {
            keyboardEvent.preventDefault();
            onFocus(nextEvent.id);
          }
        }
      }}
    >
      <header>
        <div>
          <strong>{group.player.display_name}</strong>
          <span>
            {group.player.primary_position} · {group.player.team ?? "FA"}
          </span>
        </div>
        <span className={`alert-confidence alert-confidence-${event.confidence}`}>
          {titleCase(event.confidence)}
        </span>
      </header>

      <div className="draft-alert-kind-tabs" aria-label="Alert kinds">
        {group.events.map((item) => (
          <button
            type="button"
            key={item.id}
            aria-pressed={item.id === event.id}
            onClick={() => onFocus(item.id)}
          >
            {kindLabel(item.kind)}
          </button>
        ))}
      </div>

      <p className="draft-alert-personal">{personalReason(event)}</p>
      <p className="draft-alert-signal">{evidenceHeadline(event)}</p>
      {contextualComponents.length > 0 && (
        <div className="draft-alert-context">
          {contextualComponents.map(([name, component]) => (
            <span key={name}>
              <strong>{titleCase(name)}</strong>{" "}
              {titleCase(component.band ?? "")}
            </span>
          ))}
        </div>
      )}
      <dl className="draft-alert-facts">
        <div>
          <dt>Freshness</dt>
          <dd>{titleCase(event.freshness)}</dd>
        </div>
        <div>
          <dt>Cost</dt>
          <dd>{titleCase(event.evidence.cost_availability)}</dd>
        </div>
        <div>
          <dt>Target</dt>
          <dd>{rangeLabel(event.evidence.target_pick_window)}</dd>
        </div>
      </dl>
      <p className="draft-alert-limitation">
        <span>Limit</span> {strongestLimitation(event)}
      </p>

      <div className="draft-alert-actions">
        <button
          className="secondary-button"
          type="button"
          onClick={() => onInspect(event.id)}
        >
          Inspect evidence
        </button>
        {event.status === "open" ? (
          <>
            <button
              className="quiet-button"
              type="button"
              disabled={busy}
              onClick={() => onSnooze(event.id)}
            >
              Snooze
            </button>
            <button
              className="text-button"
              type="button"
              disabled={busy}
              onClick={() => onDismiss(event.id)}
            >
              Dismiss
            </button>
          </>
        ) : (
          event.status !== "superseded" && (
            <button
              className="quiet-button"
              type="button"
              disabled={busy}
              onClick={() => onReopen(event)}
            >
              Reopen
            </button>
          )
        )}
      </div>
    </article>
  );
}

function EvidenceDrawer({
  detail,
  loading,
  onClose,
}: {
  detail: AlertDetail | null;
  loading: boolean;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  const evidence = detail?.current_evidence;

  return (
    <div className="alert-drawer-backdrop" role="presentation">
      <aside
        className="alert-evidence-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="alert-evidence-title"
      >
        <header>
          <div>
            <p className="eyebrow">Explainable evidence</p>
            <h2 id="alert-evidence-title">
              {detail?.player.display_name ?? "Loading evidence"}
            </h2>
          </div>
          <button
            ref={closeRef}
            className="quiet-button"
            type="button"
            onClick={onClose}
          >
            Close
          </button>
        </header>

        {loading || !detail || !evidence ? (
          <p className="alert-drawer-loading" role="status">
            Reading the saved explanation…
          </p>
        ) : (
          <div className="alert-drawer-content">
            <section className="alert-drawer-summary">
              <div>
                <span>Source</span>
                <strong>{evidence.source_label}</strong>
              </div>
              <div>
                <span>As of</span>
                <strong>{dateLabel(evidence.source_as_of)}</strong>
              </div>
              <div>
                <span>Compatibility</span>
                <strong>{titleCase(evidence.format_compatibility)}</strong>
              </div>
              <div>
                <span>Confidence</span>
                <strong>{titleCase(detail.event.confidence)}</strong>
              </div>
            </section>

            <section>
              <p className="eyebrow">Calculation</p>
              <dl className="alert-evidence-grid">
                <div>
                  <dt>Current pick</dt>
                  <dd>{evidence.current_overall_pick ?? "Unavailable"}</dd>
                </div>
                <div>
                  <dt>Next user pick</dt>
                  <dd>{evidence.next_user_pick ?? "Unavailable"}</dd>
                </div>
                <div>
                  <dt>Expected window</dt>
                  <dd>{rangeLabel(evidence.expected_selection)}</dd>
                </div>
                <div>
                  <dt>Conservative gap</dt>
                  <dd>{rangeLabel(evidence.market_gap, "spot")}</dd>
                </div>
                <div>
                  <dt>Return outlook</dt>
                  <dd>{titleCase(evidence.return_risk)}</dd>
                </div>
                <div>
                  <dt>Rule version</dt>
                  <dd>{evidence.rule_version}</dd>
                </div>
              </dl>
            </section>

            <section>
              <p className="eyebrow">Evidence components</p>
              <div className="alert-component-list">
                {Object.entries(evidence.components).map(([name, component]) => (
                  <article key={name}>
                    <div>
                      <strong>{titleCase(name)}</strong>
                      <span>{titleCase(component.state)}</span>
                    </div>
                    {component.state === "available" && component.band && (
                      <p>Band: {titleCase(component.band)}</p>
                    )}
                    {component.reasons.map((reason) => (
                      <p key={reason}>{titleCase(reason)}</p>
                    ))}
                  </article>
                ))}
              </div>
            </section>

            {detail.trade_reference && (
              <section>
                <p className="eyebrow">Pick-only trade reference</p>
                <div className="alert-trade-reference">
                  <strong>
                    Target {rangeLabel(detail.trade_reference.target_pick_window)}
                  </strong>
                  <span>
                    Estimated incremental cost:{" "}
                    {detail.trade_reference.incremental_cost
                      ? `${detail.trade_reference.incremental_cost.low}–${detail.trade_reference.incremental_cost.high}`
                      : "unavailable"}
                  </span>
                  {detail.trade_reference.pick_only_references.map((reference) => (
                    <span key={`${reference.season_offset}-${reference.round}`}>
                      {reference.label}: {reference.value.low}–{reference.value.high}
                    </span>
                  ))}
                  <small>
                    Reference only. Confirm any real trade yourself outside the Hub.
                  </small>
                </div>
              </section>
            )}

            <section>
              <p className="eyebrow">Confidence and limitations</p>
              <ul className="alert-reason-list">
                {evidence.confidence_reasons.map((reason) => (
                  <li key={reason}>{titleCase(reason)}</li>
                ))}
                {evidence.limitation_codes.map((code) => (
                  <li key={code}>{titleCase(code)}</li>
                ))}
                {detail.event.limitation_codes.map((code) => (
                  <li key={`event-${code}`}>{titleCase(code)}</li>
                ))}
              </ul>
            </section>

            <section>
              <p className="eyebrow">Event history</p>
              <dl className="alert-evidence-grid">
                <div>
                  <dt>Status</dt>
                  <dd>{titleCase(detail.event.status)}</dd>
                </div>
                <div>
                  <dt>Opened</dt>
                  <dd>{dateLabel(detail.event.created_at)}</dd>
                </div>
                <div>
                  <dt>Last confirmed revision</dt>
                  <dd>{detail.event.last_confirmed_draft_revision}</dd>
                </div>
                <div>
                  <dt>Last updated</dt>
                  <dd>{dateLabel(detail.event.updated_at)}</dd>
                </div>
              </dl>
            </section>
          </div>
        )}
      </aside>
    </div>
  );
}

export function DraftAlertRail({ draft }: { draft: DraftSession }) {
  const [configuration, setConfiguration] =
    useState<DraftAlertConfiguration | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [alerts, setAlerts] = useState<DraftAlertList | null>(null);
  const [scope, setScope] = useState<DraftAlertList["scope"]>("current");
  const [snapshots, setSnapshots] =
    useState<AlertEvidenceSnapshotList | null>(null);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState("");
  const [focusedEventId, setFocusedEventId] = useState<string | null>(null);
  const [drawerEventId, setDrawerEventId] = useState<string | null>(null);
  const [drawerDetail, setDrawerDetail] = useState<AlertDetail | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [snoozeEventId, setSnoozeEventId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<UiError | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const railRef = useRef<HTMLElement>(null);
  const eventCardRefs = useRef(new Map<string, HTMLElement>());
  const focusedEventIdRef = useRef<string | null>(null);

  const allEvents = useMemo(
    () => alerts?.items.flatMap((group) => group.events) ?? [],
    [alerts],
  );
  const focusedEvent =
    allEvents.find((event) => event.id === focusedEventId) ?? null;

  function focusEvent(eventId: string) {
    focusedEventIdRef.current = eventId;
    setFocusedEventId(eventId);
  }

  async function refreshAlertList(
    nextConfiguration: DraftAlertConfiguration,
    nextScope: DraftAlertList["scope"],
  ) {
    if (nextScope === "current" && nextConfiguration.enabled) {
      const savedAlerts = await getDraftAlerts(draft.id, "current");
      if (
        savedAlerts.evaluation_state === "current" &&
        savedAlerts.draft_revision === draft.revision &&
        savedAlerts.configuration_revision === nextConfiguration.revision
      ) {
        setAlerts(savedAlerts);
        return;
      }
      const result = await evaluateDraftAlerts(draft.id, {
        draft_revision: draft.revision,
        configuration_revision: nextConfiguration.revision,
        expected_current_overall_pick: draft.current_pick?.overall_pick ?? null,
        last_evaluation_draft_revision:
          savedAlerts.latest_evaluation?.draft_revision ?? null,
      });
      setAlerts(result.alerts);
      return;
    }
    setAlerts(await getDraftAlerts(draft.id, nextScope));
  }

  async function loadDecisionSupport(nextScope = scope) {
    setLoadState("loading");
    setError(null);
    try {
      const nextConfiguration = await getDraftAlertConfiguration(draft.id);
      setConfiguration(nextConfiguration);
      await refreshAlertList(nextConfiguration, nextScope);
      setLoadState("ready");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 404) {
        setConfiguration(null);
        setAlerts(null);
        setLoadState("missing");
        try {
          const availableSnapshots = await getAlertEvidenceSnapshots();
          setSnapshots(availableSnapshots);
          setSelectedSnapshotId(availableSnapshots.items[0]?.id ?? "");
        } catch (snapshotError) {
          setError(formatError(snapshotError));
        }
        return;
      }
      setError(formatError(caught));
      setLoadState("error");
    }
  }

  useEffect(() => {
    let cancelled = false;
    setLoadState("loading");
    setError(null);
    getDraftAlertConfiguration(draft.id)
      .then(async (nextConfiguration) => {
        if (cancelled) return;
        setConfiguration(nextConfiguration);
        if (scope === "current" && nextConfiguration.enabled) {
          const savedAlerts = await getDraftAlerts(draft.id, "current");
          if (cancelled) return;
          if (
            savedAlerts.evaluation_state === "current" &&
            savedAlerts.draft_revision === draft.revision &&
            savedAlerts.configuration_revision === nextConfiguration.revision
          ) {
            setAlerts(savedAlerts);
          } else {
            const result = await evaluateDraftAlerts(draft.id, {
              draft_revision: draft.revision,
              configuration_revision: nextConfiguration.revision,
              expected_current_overall_pick:
                draft.current_pick?.overall_pick ?? null,
              last_evaluation_draft_revision:
                savedAlerts.latest_evaluation?.draft_revision ?? null,
            });
            if (!cancelled) setAlerts(result.alerts);
          }
        } else {
          const result = await getDraftAlerts(draft.id, scope);
          if (!cancelled) setAlerts(result);
        }
        if (!cancelled) setLoadState("ready");
      })
      .catch(async (caught: unknown) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 404) {
          setConfiguration(null);
          setAlerts(null);
          setLoadState("missing");
          try {
            const availableSnapshots = await getAlertEvidenceSnapshots();
            if (cancelled) return;
            setSnapshots(availableSnapshots);
            setSelectedSnapshotId(availableSnapshots.items[0]?.id ?? "");
          } catch (snapshotError) {
            if (!cancelled) setError(formatError(snapshotError));
          }
          return;
        }
        setError(formatError(caught));
        setLoadState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [
    draft.current_pick?.overall_pick,
    draft.id,
    draft.revision,
    scope,
  ]);

  useEffect(() => {
    if (!alerts?.items[0]?.events[0]) {
      focusedEventIdRef.current = null;
      setFocusedEventId(null);
      return;
    }
    if (!allEvents.some((event) => event.id === focusedEventId)) {
      focusEvent(alerts.items[0].events[0].id);
    }
  }, [alerts, allEvents, focusedEventId]);

  async function inspectEvidence(eventId: string) {
    focusEvent(eventId);
    setDrawerEventId(eventId);
    setDrawerDetail(null);
    setDrawerLoading(true);
    setError(null);
    try {
      setDrawerDetail(await getDraftAlert(draft.id, eventId));
    } catch (caught) {
      setError(formatError(caught));
      setDrawerEventId(null);
    } finally {
      setDrawerLoading(false);
    }
  }

  function closeDrawer() {
    const returnEventId = drawerEventId;
    setDrawerEventId(null);
    setDrawerDetail(null);
    if (returnEventId) {
      requestAnimationFrame(() =>
        eventCardRefs.current.get(returnEventId)?.focus(),
      );
    }
  }

  function closeSnooze() {
    const returnEventId = snoozeEventId;
    setSnoozeEventId(null);
    if (returnEventId) {
      requestAnimationFrame(() =>
        eventCardRefs.current.get(returnEventId)?.focus(),
      );
    }
  }

  async function changeEventStatus(
    event: AlertEvent,
    status: "open" | "snoozed" | "dismissed",
  ) {
    if (!configuration) return;
    setBusy(true);
    setError(null);
    try {
      await updateDraftAlertStatus(draft.id, event.id, {
        configuration_revision: configuration.revision,
        expected_status: event.status,
        status,
      });
      setSnoozeEventId(null);
      await refreshAlertList(configuration, scope);
      const verb =
        status === "open"
          ? "reopened"
          : status === "snoozed"
            ? "snoozed"
            : "dismissed";
      setAnnouncement(`${verb.charAt(0).toUpperCase() + verb.slice(1)} ${kindLabel(event.kind)} for this player.`);
      if (status !== "open") {
        requestAnimationFrame(() => railRef.current?.focus());
      }
    } catch (caught) {
      setError(formatError(caught));
      await loadDecisionSupport(scope);
    } finally {
      setBusy(false);
    }
  }

  async function toggleEnabled() {
    if (!configuration) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateDraftAlertConfiguration(draft.id, {
        draft_revision: draft.revision,
        configuration_revision: configuration.revision,
        enabled: !configuration.enabled,
      });
      setConfiguration(updated);
      await refreshAlertList(updated, scope);
      setAnnouncement(
        updated.enabled
          ? "Decision support enabled."
          : "Decision support disabled. Draft state and alert history are unchanged.",
      );
    } catch (caught) {
      setError(formatError(caught));
      await loadDecisionSupport(scope);
    } finally {
      setBusy(false);
    }
  }

  async function attachSnapshot() {
    if (!selectedSnapshotId) return;
    setBusy(true);
    setError(null);
    try {
      const attached = await attachDraftAlertConfiguration(draft.id, {
        draft_revision: draft.revision,
        evidence_snapshot_id: selectedSnapshotId,
        enabled: true,
        personal_qualifier_mode: "tier_or_favorite",
        eligible_tier_count: 2,
        minimum_conservative_gap: 6,
        snooze_pick_count: 5,
      });
      setConfiguration(attached);
      setScope("current");
      await refreshAlertList(attached, "current");
      setLoadState("ready");
      setAnnouncement("Decision-support evidence attached to this draft.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    function handleAlertShortcut(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (drawerEventId) {
          event.preventDefault();
          closeDrawer();
        } else if (snoozeEventId) {
          event.preventDefault();
          closeSnooze();
        }
        return;
      }
      if (isFormField(event.target)) return;
      const currentFocusedEventId = focusedEventIdRef.current;
      const currentFocusedEvent =
        allEvents.find((item) => item.id === currentFocusedEventId) ?? null;
      if (event.key.toLowerCase() === "a") {
        event.preventDefault();
        railRef.current?.focus();
        return;
      }
      if (event.key.toLowerCase() === "e" && currentFocusedEventId) {
        event.preventDefault();
        void inspectEvidence(currentFocusedEventId);
        return;
      }
      if (
        event.key.toLowerCase() === "s" &&
        currentFocusedEvent?.status === "open"
      ) {
        event.preventDefault();
        setSnoozeEventId(currentFocusedEvent.id);
        return;
      }
    }
    window.addEventListener("keydown", handleAlertShortcut);
    return () => window.removeEventListener("keydown", handleAlertShortcut);
  }, [
    drawerEventId,
    allEvents,
    snoozeEventId,
  ]);

  return (
    <>
      <aside
        className="draft-alert-rail"
        ref={railRef}
        tabIndex={-1}
        aria-label="Decision support"
      >
        <header className="draft-alert-rail-heading">
          <div>
            <p className="eyebrow">Decision support</p>
            <h3>Alert rail</h3>
          </div>
          {configuration && (
            <span className={configuration.enabled ? "is-enabled" : "is-disabled"}>
              {configuration.enabled ? "Enabled" : "Disabled"}
            </span>
          )}
        </header>

        <p className="visually-hidden" aria-live="polite">
          {announcement}
        </p>

        {error && (
          <div className="draft-alert-error" role="alert">
            <strong>{error.message}</strong>
            {error.action && <span>{error.action}</span>}
            <button
              className="text-button"
              type="button"
              onClick={() => void loadDecisionSupport()}
            >
              Retry
            </button>
          </div>
        )}

        {loadState === "loading" && (
          <p className="draft-alert-loading" role="status">
            Reconciling saved evidence…
          </p>
        )}

        {loadState === "missing" && (
          <section className="draft-alert-unconfigured">
            <strong>No evidence attached</strong>
            <p>
              This room works without alerts. Attach a committed local snapshot
              only when you want market-informed decision support.
            </p>
            {snapshots && snapshots.items.length > 0 ? (
              <>
                <label>
                  Evidence snapshot
                  <select
                    value={selectedSnapshotId}
                    onChange={(event) => setSelectedSnapshotId(event.target.value)}
                  >
                    {snapshots.items.map((snapshot) => (
                      <option value={snapshot.id} key={snapshot.id}>
                        {snapshot.source_label} · {titleCase(snapshot.compatibility_state)}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={busy || !selectedSnapshotId}
                  onClick={() => void attachSnapshot()}
                >
                  Attach with defaults
                </button>
              </>
            ) : (
              <p className="draft-alert-empty-note">
                No committed snapshots are available yet.
              </p>
            )}
            <AlertEvidenceImportPanel
              draft={draft}
              onCommitted={(snapshot) => {
                setSnapshots((current) => ({
                  items: [
                    snapshot,
                    ...(current?.items.filter(
                      (item) => item.id !== snapshot.id,
                    ) ?? []),
                  ],
                  total:
                    (current?.items.some((item) => item.id === snapshot.id)
                      ? current.total
                      : (current?.total ?? 0) + 1),
                  limit: current?.limit ?? 100,
                  offset: 0,
                }));
                setSelectedSnapshotId(snapshot.id);
              }}
            />
          </section>
        )}

        {loadState === "ready" && configuration && (
          <>
            <section className="draft-alert-configuration">
              <div>
                <span>Evidence</span>
                <strong>{configuration.evidence_snapshot.source_label}</strong>
              </div>
              <div>
                <span>As of</span>
                <strong>
                  {dateLabel(configuration.evidence_snapshot.source_as_of)}
                </strong>
              </div>
              <div>
                <span>Format</span>
                <strong>{formatCompatibility(configuration)}</strong>
              </div>
              <div>
                <span>Threshold</span>
                <strong>{configuration.minimum_conservative_gap}+ spots</strong>
              </div>
              <button
                className="text-button"
                type="button"
                disabled={busy}
                onClick={() => void toggleEnabled()}
              >
                {configuration.enabled ? "Disable alerts" : "Enable alerts"}
              </button>
            </section>

            <div className="draft-alert-scope" aria-label="Alert scope">
              <button
                type="button"
                aria-pressed={scope === "current"}
                onClick={() => setScope("current")}
              >
                Current
              </button>
              <button
                type="button"
                aria-pressed={scope === "history"}
                onClick={() => setScope("history")}
              >
                History
              </button>
              <span>{alerts?.total ?? 0}</span>
            </div>

            {alerts?.evaluation_state === "stale" && (
              <p className="draft-alert-stale" role="status">
                Draft state changed. Refreshing authoritative alerts.
              </p>
            )}

            {!configuration.enabled && scope === "current" ? (
              <p className="draft-alert-empty-note">
                Alerts are disabled. The draft and saved alert history are
                unchanged.
              </p>
            ) : alerts && alerts.items.length > 0 ? (
              <div className="draft-alert-list">
                {alerts.items.map((group) => {
                  const firstEvent = group.events[0];
                  return (
                    <AlertCard
                      key={group.player.id}
                      group={group}
                      focusedEventId={focusedEventId}
                      busy={busy}
                      onFocus={focusEvent}
                      onInspect={(eventId) => void inspectEvidence(eventId)}
                      onSnooze={(eventId) => {
                        focusEvent(eventId);
                        setSnoozeEventId(eventId);
                      }}
                      onDismiss={(eventId) => {
                        const event = group.events.find(
                          (item) => item.id === eventId,
                        );
                        if (event) void changeEventStatus(event, "dismissed");
                      }}
                      onReopen={(event) =>
                        void changeEventStatus(event, "open")
                      }
                      cardRef={(node) => {
                        if (!firstEvent) return;
                        for (const event of group.events) {
                          if (node) eventCardRefs.current.set(event.id, node);
                          else eventCardRefs.current.delete(event.id);
                        }
                      }}
                    />
                  );
                })}
              </div>
            ) : (
              <p className="draft-alert-empty-note">
                {scope === "current"
                  ? "No current decision points meet your personal and evidence thresholds."
                  : "No saved alert history for this room yet."}
              </p>
            )}

            <p className="draft-alert-shortcuts" aria-label="Alert shortcuts">
              <kbd>A</kbd> Focus · <kbd>E</kbd> Evidence · <kbd>S</kbd> Snooze
            </p>
          </>
        )}
      </aside>

      {snoozeEventId && focusedEvent && (
        <div
          className="draft-alert-snooze"
          role="dialog"
          aria-modal="true"
          aria-labelledby="draft-alert-snooze-title"
        >
          <div>
            <p className="eyebrow" id="draft-alert-snooze-title">
              Snooze alert
            </p>
            <strong>{kindLabel(focusedEvent.kind)}</strong>
            <p>
              Hide this decision point until the earlier of{" "}
              {configuration?.snooze_pick_count ?? 5} saved picks or your next
              turn.
            </p>
            <div>
              <button
                className="quiet-button"
                type="button"
                autoFocus
                onClick={closeSnooze}
              >
                Cancel
              </button>
              <button
                className="secondary-button"
                type="button"
                disabled={busy}
                onClick={() => void changeEventStatus(focusedEvent, "snoozed")}
              >
                Confirm snooze
              </button>
            </div>
          </div>
        </div>
      )}

      {drawerEventId && (
        <EvidenceDrawer
          detail={drawerDetail}
          loading={drawerLoading}
          onClose={closeDrawer}
        />
      )}
    </>
  );
}
