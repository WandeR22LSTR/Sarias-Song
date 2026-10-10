# Saria's Song: status and continuation handoff

Written 2026-10-09 so that a **fresh session can pick up without the earlier chat**. Read this, then
`README.md`, then `docs/stream-privacy.md` (the phase 4 design). The original brief is
`docs/handoffs/saria-song-handoff.md` and is still the source for the working agreements.

## The project in one paragraph

A Windows tray app (green music note) that starts at login and, on click, launches a dark, calm fullscreen
screensaver (soft clock, slow fireflies) as a separate process. It keeps the PC awake while it is up and lets
transfers continue. Python 3.13, `pygame`, `pystray`, `Pillow`. Code is written in a cloud session; **Luca
tests on his Windows PC, Spirit Temple**, and his reports are the ground truth. Repo:
`WandeR22LSTR/Sarias-Song`, working branch `claude/saria-song-handoff-0n1q13` (pushed; there is **no `main`**
yet and no PR, because the remote was empty and Luca has not chosen how to handle it).

## How to work with Luca

- **One step at a time.** He asked for this explicitly. Give a small batch, wait for his result, then move on.
  He is comfortable pasting PowerShell commands and screenshots, but wants short steps and plain explanations.
- **Never claim Windows behaviour is verified until he reports it.** Tick README checklist items only for what he
  actually confirmed (logs or his words).
- **Say so when something is untested.** Several of my PowerShell and Windows-API pieces were wrong the first
  time (the setup script, the keep-awake request). Expect to iterate.
- He streams with **Apollo** (Sunshine fork) from Spirit Temple to the **Artemis/Moonlight client on a Mac**, so
  the Windows key is not reachable from the client.
- He edits his local `config.json` (for example `clock.show_seconds`). **Do not change the tracked
  `config.json` in a commit** without telling him: it would break his `git pull`. New settings must have
  defaults in `src/config.py`; a missing key in his file is fine.
- Working agreements from the brief: do **not** touch the Ice Cavern repo; no secrets, MAC addresses or network
  details in this repo; keep it free, minimal and well documented.
- Push only to the working branch. Do not open a PR unless asked (and there is no base branch to target).
- The cloud VM has no PowerShell, so `.ps1` files cannot be run there; keep them simple.
- Test habit that has paid off: after fixing something, run the new test against the **old** code to prove it can
  fail (stash the fix, or break it on purpose). Several real bugs were found this way.

## Plan (revised 2026-10-09)

| Phase | What | State |
| --- | --- | --- |
| 1 | Tray: icon, menu, autostart | done, confirmed on Spirit Temple |
| 2 | Saver: clock, fireflies, exit rules, multi-monitor | done, confirmed (streaming and the 8-hour soak still open) |
| 3 | Keep-awake, remote sleep, transfers | done, confirmed |
| 4 | **Apollo / Artemis stream awareness** | design stage; the input probe is written and waiting to be run |
| 5 | Packaging, install/uninstall, settings GUI, technical features | not started |
| 6 | Visuals: Zelda theme, light audio, refined visuals, layouts, widgets (absorbs the old text/slideshow modes and transfer rates) | not started |

## What is confirmed on Spirit Temple

Two monitors (1920x1080 left of a 2560x1440 primary, so a negative coordinate), a 12-thread CPU. Tray icon,
menu, Settings, Exit, second-instance guard and autostart (a Startup-folder shortcut to the venv's
`pythonw.exe`); the saver covers both monitors, hides the taskbar, uses Segoe UI Light, starts in about 0.25 s,
exits on key, mouse move or click after a 2 s grace period; the clock does not shift as digits change; no
visible banding; CPU **18% of one core (1.5% of the PC)**, memory 117 to 122 MB and flat over 34 minutes; keep-awake
shows under SYSTEM in `powercfg /requests`; a remote "lullaby" still sleeps the PC with the saver up (the saver
closes itself as the PC sleeps: Windows sends a mouse move during the sleep/lock sequence); a torrent and a Google
Drive upload keep running. Luca's PC is **deliberately set to never sleep**, and the app never changes power
settings.

## Things learned that are easy to forget

- **SDL cancels keep-awake.** SDL2 disables the screensaver by default using `SetThreadExecutionState` with a
  display flag; that is per thread and last-call-wins, so it replaced our request. The saver now sets
  `SDL_VIDEO_ALLOW_SCREENSAVER=1` and `set_allow_screensaver(True)` and re-asserts keep-awake each minute.
- **Dark gradients band.** Anything only a few colour levels high (background, clock glow, firefly sprites) is built in
  floating point at full resolution with noise added **before** rounding. Adding noise after rounding does not work.
- **The clock is laid out on a fixed grid** (each digit in its own slot), because centring the whole string makes
  it change width in fonts with proportional digits.
- **The clock glow is baked into the backdrop**, not blended every frame (halved the CPU on his PC). The baked glow is
  removed by restoring saved pixels, not by subtracting, because a bright custom background would saturate.
- **The app reports its own CPU and memory** to `logs\saver.log` (a `perf:` line each minute) and `logs\tray.log`
  because the saver covers the screen. This is how Luca measures it.
- Windows-only code lives in `src/winapi.py` behind `IS_WINDOWS`, with mocked tests. Tests that touch a real
  Windows mutex or similar must be stubbed (the tray tests do this).

## Phase 4: where it stands

Read `docs/stream-privacy.md`. Decisions from Luca: the use error is that the **client's quit keybind leaks keys
that close the saver**; during a stream **ignore only the client's input** if possible; when a stream ends the saver
**stays up until someone uses the physical mouse or keyboard**; it should run on the physical monitors only, not the
virtual display, on by default with a setting to turn it off.

Everything hinges on two unknowns:

1. **Is Apollo's client input flagged as injected by Windows?** `src/inputprobe.py` answers this (a read-only
   low-level-hook diagnostic, tests written, **not yet run on Windows**). Luca runs
   `.\.venv\Scripts\python.exe .\src\inputprobe.py --seconds 90` and presses keys on the client, then the host. If the
   client's input is `injected` and the host's is `physical`, "ignore the client, stay until the hardware is
   touched" is one rule.
2. **Does the virtual display mirror or extend the physical monitor?** Luca says it mirrors; he is finding out
   why. Mirroring defeats a physical-only saver. Apollo's FAQ says to set Windows to Extend (Win+P) and restart
   Apollo; from the Mac client he cannot press Win, so use Settings > Display > Multiple displays, or
   `DisplaySwitch.exe /extend`.

Proposed slices are in the design doc (4.0 experiments, 4.1 modifier-only keys stopgap, 4.2 ignore injected input,
4.3 physical-only displays with no focus, 4.4 stream detection, 4.5 setting and Apollo setup steps).

## Other open items

- The **8-hour soak** (leave the saver running; afterwards run `.\.venv\Scripts\python.exe .\src\soakreport.py`, steps in the README under "Soak").
- Which of the original handoff's open questions remain: none blocking. Streaming (Apollo, Artemis on a Mac) and
  transfer clients (torrent and Google Drive upload) are answered.
- The optional shortened-sleep-timer test in the README is unrun (the PC is meant to never sleep).
- No `main` branch or PR exists yet.

## Running things

```powershell
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\dev-setup.ps1 -Dev   # creates .venv (Python 3.13), installs pins
.\.venv\Scripts\python.exe -m pytest                                      # about 218 tests, run headless
.\.venv\Scripts\python.exe .\src\tray.py                                  # the tray app
cd src; ..\.venv\Scripts\python.exe -m saver.main /s --windowed           # just the saver, in a window
```

In the cloud VM the equivalent is a venv with `requirements-dev.txt` and `python -m pytest`; tests use SDL's dummy
video driver. Logs on the PC are in `logs\` (`tray.log`, `saver.log`, `saver-stderr.log`, `input-probe.txt`).

## A starter prompt for a new session

> Read `docs/handoffs/saria-song-status-2026-10-09.md`, then `README.md` and `docs/stream-privacy.md`. We are on
> branch `claude/saria-song-handoff-0n1q13` of `WandeR22LSTR/Sarias-Song`, working through phase 4 (Apollo
> stream awareness) one step at a time with Luca, who tests on his Windows PC. Start by asking him for the
> result of the input probe.
