import { useEffect, useState } from "react";

import {
  ApiError,
  type AppConfiguration,
  type HealthResponse,
  type LeagueProfileSummary,
  getConfiguration,
  getHealth,
  getLeagueProfiles,
  loadEntropySample,
  saveConfiguration,
} from "../api/client";
import { PlayerWorkspace } from "../features/players/PlayerWorkspace";

type LoadState = "loading" | "ready" | "error";
type AppSection = "overview" | "players";

function formatError(error: unknown): { message: string; action?: string } {
  if (error instanceof ApiError) {
    return { message: error.message, action: error.action };
  }
  return {
    message: "The Hub could not finish loading.",
    action: "Restart the local application and try again.",
  };
}

export function App() {
  const [section, setSection] = useState<AppSection>("overview");
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [configuration, setConfiguration] = useState<AppConfiguration | null>(
    null,
  );
  const [profiles, setProfiles] = useState<LeagueProfileSummary[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<{ message: string; action?: string } | null>(
    null,
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getHealth(), getConfiguration(), getLeagueProfiles()])
      .then(([healthResult, configurationResult, profileResult]) => {
        if (cancelled) return;
        setHealth(healthResult);
        setConfiguration(configurationResult);
        setProfiles(profileResult);
        setLoadState("ready");
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(formatError(caught));
        setLoadState("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function importSample() {
    if (!configuration) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const profile = await loadEntropySample();
      const updatedConfiguration = {
        ...configuration,
        active_league_season_id: profile.id,
      };
      const savedConfiguration = await saveConfiguration(updatedConfiguration);
      setConfiguration(savedConfiguration);
      setProfiles(await getLeagueProfiles());
      setNotice("Entropy is loaded locally and selected as the active league.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setSaving(false);
    }
  }

  async function savePreferences() {
    if (!configuration) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      setConfiguration(await saveConfiguration(configuration));
      setNotice("Settings saved. They will be restored the next time the Hub opens.");
    } catch (caught) {
      setError(formatError(caught));
    } finally {
      setSaving(false);
    }
  }

  if (loadState === "loading") {
    return (
      <main className="centered-state">
        <div className="loading-mark" aria-hidden="true">
          FN
        </div>
        <p>Opening your local front office…</p>
      </main>
    );
  }

  if (loadState === "error" || !configuration || !health) {
    return (
      <main className="centered-state">
        <p className="eyebrow">Startup check</p>
        <h1>The Hub could not open safely.</h1>
        <p>{error?.message}</p>
        {error?.action && <p>{error.action}</p>}
      </main>
    );
  }

  const activeProfile = profiles.find(
    (profile) => profile.id === configuration.active_league_season_id,
  );

  return (
    <main
      className={`app-shell ${section === "players" ? "app-shell-players" : ""}`}
    >
      <header className="hero">
        <div>
          <p className="eyebrow">Local Draft Lab · Phase 1</p>
          <h1>Friendly Neighborhood Fantasy Hub</h1>
          <p className="hero-copy">
            Your private draft room foundation is running locally. Judgment stays
            yours; the Hub keeps the board, rules, and reasoning organized.
          </p>
        </div>
        <div className="status-pill" role="status">
          <span aria-hidden="true" />
          Local database connected
        </div>
      </header>

      <nav className="app-navigation" aria-label="Primary">
        <button
          type="button"
          aria-current={section === "overview" ? "page" : undefined}
          onClick={() => setSection("overview")}
        >
          Overview
        </button>
        <button
          type="button"
          aria-current={section === "players" ? "page" : undefined}
          onClick={() => setSection("players")}
        >
          Players
        </button>
      </nav>

      {section === "overview" && error && (
        <section className="notice notice-error" role="alert">
          <strong>{error.message}</strong>
          {error.action && <span>{error.action}</span>}
        </section>
      )}
      {section === "overview" && notice && (
        <section className="notice notice-success" role="status">
          {notice}
        </section>
      )}

      {section === "players" ? (
        <PlayerWorkspace />
      ) : (
        <section className="dashboard-grid">
        <article className="card league-card">
          <div className="card-heading">
            <div>
              <p className="eyebrow">Active league</p>
              <h2>{activeProfile?.name ?? "No league loaded yet"}</h2>
            </div>
            {activeProfile && <span className="tag">Sanitized sample</span>}
          </div>

          {activeProfile ? (
            <div className="league-facts">
              <div>
                <strong>{activeProfile.team_count}</strong>
                <span>Teams</span>
              </div>
              <div>
                <strong>SF</strong>
                <span>Superflex</span>
              </div>
              <div>
                <strong>TE+</strong>
                <span>First-down premium</span>
              </div>
              <div>
                <strong>24</strong>
                <span>Startup rounds</span>
              </div>
            </div>
          ) : (
            <>
              <p>
                Load the privacy-safe Entropy profile to prove that league rules
                can be used without a network connection.
              </p>
              <button
                className="primary-button"
                type="button"
                onClick={importSample}
                disabled={saving}
              >
                {saving ? "Loading…" : "Load Entropy sample"}
              </button>
            </>
          )}
        </article>

        <article className="card">
          <p className="eyebrow">System check</p>
          <h2>Ready for the next phase</h2>
          <dl className="system-list">
            <div>
              <dt>Application</dt>
              <dd>v{health.app_version}</dd>
            </div>
            <div>
              <dt>Database migration</dt>
              <dd>{health.database_schema_version}</dd>
            </div>
            <div>
              <dt>Network requirement</dt>
              <dd>None for this proof</dd>
            </div>
          </dl>
        </article>

        <article className="card settings-card">
          <div className="card-heading">
            <div>
              <p className="eyebrow">Application settings</p>
              <h2>Local preferences</h2>
            </div>
          </div>
          <div className="form-grid">
            <label>
              Display timezone
              <select
                value={configuration.display.timezone}
                onChange={(event) =>
                  setConfiguration({
                    ...configuration,
                    display: {
                      ...configuration.display,
                      timezone: event.target.value,
                    },
                  })
                }
              >
                <option value="America/Chicago">Central time</option>
                <option value="America/New_York">Eastern time</option>
                <option value="America/Denver">Mountain time</option>
                <option value="America/Los_Angeles">Pacific time</option>
              </select>
            </label>
            <label>
              Theme
              <select
                value={configuration.display.theme}
                onChange={(event) =>
                  setConfiguration({
                    ...configuration,
                    display: {
                      ...configuration.display,
                      theme: event.target.value as "system" | "light" | "dark",
                    },
                  })
                }
              >
                <option value="system">Match computer</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
          </div>
          <button
            className="secondary-button"
            type="button"
            onClick={savePreferences}
            disabled={saving}
          >
            {saving ? "Saving…" : "Save settings"}
          </button>
        </article>
        </section>
      )}
    </main>
  );
}
