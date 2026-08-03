# Friendly Hub V1 Draft-Night Guide

This is the short call sheet for using the Hub on one Windows computer. The Hub
runs privately on that computer; its core draft-night workflows do not need a
cloud service.

## First-Time Setup

Setup needs an internet connection once so Python and frontend packages can be
installed.

1. Open PowerShell in the repository folder.
2. Run `powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1`.
3. Wait for `Setup complete`.
4. Double-click `Launch Friendly Hub.cmd`.

The normal browser should open to `http://127.0.0.1:8765`. Keep the launcher
window open while using the Hub.

## Routine Launch

Double-click `Launch Friendly Hub.cmd`. Before the browser opens, the launcher
creates and verifies a private backup if a local database already exists. The
10 newest backups are retained by default.

The green `Local database connected` status means the service, migrations, and
local database opened successfully. The Overview shows `v1.0.2` for the release
build.

## Before the Draft

1. Open **Players** and confirm the intended player pool is local.
2. Open **Boards**, select the authoritative Personal Board, and click
   **Export CSV**. Keep that file somewhere easy to find.
3. Open **Mock lab** and rehearse the Entropy startup shape: 10 teams, 24
   rounds, third-round reversal, your slot 1. Confirm the control strip says
   **Dynasty Superflex expert consensus** and shows the July 31 source date.
4. Open **Draft room**, create the live room, and confirm the team names and
   first pick before the real clock starts.
5. Keep the exported board available as the no-network fallback.

## During the Draft

- An accepted pick is saved immediately; wait for the updated pick and revision
  before entering another.
- **Undo latest** safely reverses the most recent pick.
- Select a recorded pick and use correction when an earlier player was entered
  incorrectly.
- **Pause** preserves the exact current pick. **Resume** continues from it.
- Use Blind view when you do not want Personal Board context exposed onscreen.
- Click **Export CSV** in Draft room after meaningful checkpoints and at the
  end of the draft.

## If the Browser or Launcher Closes

1. Do not create a replacement room.
2. Double-click `Launch Friendly Hub.cmd` again.
3. Open **Draft room** and select the saved session.
4. Confirm its current pick, saved pick count, and revision, then continue.

The database—not the browser tab—is authoritative. A closed tab does not erase
accepted picks.

## Backups and Recovery

Production data lives at:

`%LOCALAPPDATA%\FriendlyNeighborhoodFantasyHub\`

Verified private backups live in its `backups` folder and use names such as:

`friendly-hub-backup-v1-20260803-134500.zip`

To create another backup while the Hub is closed, run:

`powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1`

For an ordinary interruption, relaunch first; a full database restore should
not be the first move. If the database cannot open:

1. Close the launcher.
2. Copy the entire data folder somewhere safe. Do not delete or overwrite it.
3. Preserve the newest backup ZIP unchanged.
4. Restore only after confirming which backup predates the problem.

A backup ZIP contains a verified `hub.sqlite3` plus `manifest.json`. Recovery
is intentionally not automatic because choosing the wrong older backup could
replace newer picks. The untouched current database and backup should both be
preserved before any restore.

## Offline Fallback

After setup, the saved player pool, Entropy profile, Personal Boards, Gut ELO,
Draft room, Mock lab, alerts using already imported evidence, reports, and
exports work locally. If an external source is unavailable, keep the last saved
timestamp visible and continue from local data rather than refreshing.

If the Hub itself cannot be recovered during a live clock, use the latest
Personal Board CSV as the board and the latest Draft room CSV as the pick
scorebook. The Hub never replaces commissioner or provider draft records.

## Normal Shutdown

Finish any visible action, then close the launcher window or press `Ctrl+C` in
it. The next launch will create a fresh safety backup before opening the app.
