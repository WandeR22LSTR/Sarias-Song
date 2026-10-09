# Handoff: Saria's Song

Written: 2026-10-08 (updates and supersedes the earlier "Tray-Launched Custom Screensaver" handoff)
For: Claude Code, running on Spirit Temple (Luca's Windows PC, Windows user `Luca`)
Parallel session: Ice Cavern hub (see `ice-cavern-handoff.md`). It runs at the same time in a separate repo. Do not touch it.
Put this file at: `docs/handoffs/saria-song-handoff.md` in this project's repo.

> Transcribed into the repo from the session message. Wording is unchanged; list numbering was normalised
> (the original continued numbering across sections).

## 0. Before you start: repo, docs and environment check (do this first)

This session may run as a Claude Code cloud session (an Anthropic-hosted VM that clones from GitHub), so Luca may not be at the machine. Before writing code, check each item below. If anything is missing or unclear, stop and ask Luca in the session. Do not guess.

1. **Repo.** Is this directory a git repo with a GitHub remote? If not, ask Luca for the repo name (suggest `saria-song`), whether it already exists on GitHub (private is fine), and whether the Claude GitHub App is installed on it. Do not create or invent remotes.
2. **Handoff placement.** Confirm this file is committed at `docs/handoffs/saria-song-handoff.md`. The Ice Cavern handoff is reference material only: ask Luca whether to keep a copy in `docs/handoffs/` or just ignore it, and never edit it. If a file is in the repo root or elsewhere, ask before moving it.
3. **Docs layout.** Default: README in the repo root, everything else under `docs/`. Ask Luca to confirm.
4. **Push access and branching.** Confirm you can push. Work on a feature branch (not `main`) and open a PR unless Luca says otherwise.
5. **Hybrid workflow (decided by Luca).** The repo lives in two places: a cloud session where you write the code, and a local clone on Spirit Temple (Windows) where Luca runs and tests it. You code, Luca tests, and the loop repeats. The Windows-only pieces cannot be run or seen in the cloud VM: the tray icon, `SetThreadExecutionState`, the fullscreen saver, startup registration, and the remote-sleep test. So:
   * Never claim visuals or Windows behavior are verified when you could not run them. Luca's test report is the ground truth.
   * Put Windows-specific code behind a clear platform check and mock the `ctypes` calls in tests.
   * Write unit tests for everything that runs anywhere (config loading, mode selection, render math, grace-period logic), and run them in the cloud.
   * Push at the end of every phase (section 6) so there is always a branch Luca can test. Do not move on to the next phase until Luca reports back, unless the next phase is clearly independent.
   * End each phase with a "Test on Spirit Temple" block in your message and in the PR description, written for PowerShell: the exact commands to fetch the branch (`git fetch`, `git checkout <branch>`, `git pull`), create or update the venv, `pip install -r requirements.txt`, and run the app, plus a short checklist of what to look for and what to report back (screenshot, error text, or "works").
   * Keep dependencies pinned in `requirements.txt` and state the Python version in the README so the local setup matches the cloud one. Add a `scripts/dev-setup.ps1` that creates the venv and installs requirements.
   * Keep a Manual test checklist in the README covering every Windows-only behavior, including the remote-sleep test from section 4.
   * When Luca reports a failure, reproduce what you can in tests, fix it on the same branch, and push again.
   * Do not merge to `main` until Luca confirms the phase passed on Spirit Temple.

Cloud-session notes: commit and push at sensible milestones so Luca can review diffs from his phone, and if you are blocked on an answer, ask in the session and continue with anything non-blocking.

## 1. Context

Luca names his devices and projects after Ocarina of Time. Saria's Song is one project in a family of themed personal projects, all organized under a hub called Ice Cavern. Saria's Song is standalone: its own repo, no dependency on the hub. The hub only lists it.

Relevant machine facts:

* Spirit Temple is a Windows PC. It is also a game-streaming host: Luca streams games from it with Apollo (a Sunshine fork) to other devices using Artemis (Moonlight client).
* Spirit Temple is woken and put to sleep remotely over the LAN by a Raspberry Pi (Temple of Time). Wake is "requiem" and sleep is "lullaby". Sleep uses Sleep-on-LAN (`sol.exe`, installed as a Windows service via NSSM from `C:\Tools\Sleep-On-Lan`).
* The PC is configured not to idle-sleep on its own.

## 2. Goal

A small Windows tray app that:

1. Lives in the system tray with a green music-note icon and starts automatically at login.
2. On click, launches a custom, themed, fullscreen screensaver, dark-ish in tone (comfortable for use while streaming).
3. Keeps the PC awake and lets downloads and uploads continue while the screensaver is up.
4. Optionally shows live transfer activity (stretch goal, see phase 6).

## 3. Decisions made

* Hybrid workflow: code in a cloud session, test on Spirit Temple (see section 0, item 5).
* Python only. This replaces the earlier AutoHotkey launcher plus Python saver split. Keep the old AHK snippet only as historical reference, do not use it.
* Tray: `pystray` with `Pillow`. Saver: `pygame` (or `tkinter` if you can justify it).
* Transfer-activity display is a nice-to-have. Luca is fine dropping it if the saver takes real effort.
* Packaging: PyInstaller, windowed (no console), with a proper icon.
* "Windows service" in Luca's description means "background tray app". A real Windows Service cannot show UI in the user session, so build a user-session tray app that starts at login, not an actual service. Autostart via a Startup folder shortcut or a Task Scheduler "at logon" task, whichever is more robust (your call, document it).

## 4. Design

### Tray app

* Left-click: start screensaver. Right-click menu: Start screensaver, Settings (opens the config file or a small dialog), Exit.
* Draw the green note icon programmatically with Pillow (a simple eighth or quarter note, Saria/Kokiri green) so no external asset is needed, and export an `.ico` for the exe.
* Run the saver as a separate subprocess so a saver crash never kills the tray app.

### Screensaver

* Dark-ish background (deep green-black, not pure black), soft green accents, restrained animation.
* Modes via config: `clock`, `text`, `slideshow`, `mixed`. Start with a polished default (clock plus a slow ambient animation) before adding the rest.
* Grace period of about 2 seconds after launch so a mouse twitch does not instantly exit.
* Exit on any key or mouse movement by default (configurable).
* Support `/s`, `/c`, `/p` arguments so it could become a real `.scr` later if Luca wants.
* Multi-monitor: cover all monitors, or at least the primary. Ask Luca which.

### Keep-awake

* While the saver runs, call `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` via `ctypes`, and clear it on exit.
* Do not change power plans or the registry.
* Interaction with remote sleep: Luca sleeps this PC on purpose from the Pi through Sleep-on-LAN. Keep-awake should only block idle sleep and must not stop that deliberate sleep command. Verify this by testing a remote sleep while the saver is running, and report the result to Luca.

### Config

* `config.json` next to the executable: colors, font, mode, text, image folder, slide seconds, animation speed, exit behavior. Use `pathlib` and keep paths relative to the exe so the folder can move.

## 5. Suggested layout

```
saria-song/
├── src/
│   ├── tray.py
│   ├── saver/
│   │   ├── main.py
│   │   ├── render.py
│   │   └── keepawake.py
│   └── config.py
├── assets/            # generated icon, fonts if any
├── build/             # PyInstaller spec, build script
├── tests/
├── docs/handoffs/
├── config.json
└── README.md
```

## 6. Phases

1. Tray skeleton. Green-note icon, menu, autostart approach decided and documented.
2. Minimal saver. Fullscreen pygame window with the dark default look, clock only, exits on input, honors `/s`, launched as a subprocess.
3. Keep-awake. `SetThreadExecutionState` handling. Test with a large transfer running for 30+ minutes with the Windows sleep timer set low. Also run the remote-sleep test from section 4.
4. Config and modes. `config.json`, text and slideshow modes, grace period.
5. Packaging. PyInstaller exe, startup wiring, README with install and uninstall steps.
6. Stretch: transfer activity. Show upload/download rates using `psutil` network counters. Skip if it slows the rest down.

## 7. Acceptance criteria

* Tray icon appears at login, and a click starts the saver within about 1 second.
* Any input exits and the desktop returns with no lost windows.
* A download or upload started before launch finishes while the saver runs, with no stall.
* A remote sleep command from the Pi still puts the PC to sleep while the saver is running.
* Config changes apply on the next launch without code edits.
* No crash or visible slowdown after 8 hours of running, and the tray app uses modest memory.

## 8. Open questions (ask Luca)

* Is "streaming" here Apollo/Moonlight-style remote play (assumed), or broadcasting to an audience? This changes how the saver should behave on the streamed display.
* Should the saver cover all monitors or only the primary?
* Lock the PC on exit, or just return to the desktop?
* Which transfer clients matter most (browser, torrent client, Syncthing, game launchers)? Some pause on lock or sleep.
* Repo name (suggest `Saria-s-Song` or `saria-song`).

## 9. Working agreements

* Do not touch the Ice Cavern hub repo. The hub's project registry will get an entry for this project, and Luca will update its status when you are done.
* If you need more context about Luca's setup or the wider project family, ask for a handoff instead of guessing.
* No secrets, MAC addresses or network details in the repo.
* Keep it free, minimal, and well-documented: a README in the repo root, comments where the Windows API calls are non-obvious.
* Run the saver and look at it before calling the visuals done. Luca cares about how it looks.

---

## Decisions recorded in the first session (2026-10-08)

Answers Luca gave to the section 0 / section 8 questions:

| Question | Answer |
| --- | --- |
| Repo | `WandeR22LSTR/Sarias-Song` (existed on GitHub, empty). Work happens on `claude/saria-song-handoff-0n1q13`. |
| Docs layout | Default: README in the repo root, everything else under `docs/`. |
| Ice Cavern handoff | Ignore it. Not copied into this repo. |
| Monitors | Cover **all** monitors. |
| Lock on exit | **No.** Return to the desktop only. |
| Streaming | Apollo to Artemis (confirmed 2026-10-09). New requirement: while a stream is active the saver should run automatically on the **physical** monitor(s) but **not** on the virtual display, so Luca can use the PC privately; default on, with a setting for the alternative. Apollo recently changed from switching the physical monitor off to mirroring. Not built yet; see `docs/stream-privacy.md`. |
| Transfer clients | Everything if possible; the main cases are **torrenting** and **uploading to Google Drive** with the Drive app (2026-10-09). |
| Plan revised (2026-10-09) | Phases 1 to 3 are done as written. From here: **phase 4 = Apollo/Artemis stream awareness**; **phase 5 = packaging, install/uninstall, a settings GUI and the technical features**; **phase 6 = visuals**: a Zelda-themed rework, light audio, refined visuals, new layouts and a set of widgets. The original phase 4 (text/slideshow/mixed modes) and phase 6 (transfer rates) are absorbed into the new phase 6 as widgets. The brief's section 6 above is left as originally written. |
