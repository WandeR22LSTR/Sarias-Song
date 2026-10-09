# Saria's Song

A small Windows tray app with a green music-note icon. Click it and a dark, calm,
fullscreen screensaver comes up: a soft clock and slow green fireflies drifting like
the lights in Kokiri Forest. Built to be comfortable on a streamed display.

Part of Luca's Ocarina-of-Time-themed project family. Standalone, with no dependency
on the Ice Cavern hub.

> **Status: phases 1, 2 and 3 are running on Spirit Temple; the checklist is mostly ticked.**
> Confirmed so far (Luca, 2026-10-08/09, from screenshots, `logs\*.log` and testing): the tray icon,
> tooltip, menu and Settings; config changes applying on the next launch; the saver covering
> both monitors (one at negative coordinates) and hiding the taskbar; Segoe UI Light; exit on a
> key, mouse move or click, with the 2 s grace period and the tiny-nudge threshold; one saver only
> on a double-click; and, after fixes, no visible banding on the 1440p monitor and a clock that
> stays put as its digits change; the second-instance guard and Exit; autostart (so phase 1 is done);
> and phase 3: the keep-awake request is held while the saver is up (`powercfg /requests`), a remote
> "lullaby" still puts the PC to sleep with the saver on screen, and a torrent and a Google Drive upload
> keep running. Not yet confirmed: streaming (now phase 4, see `docs/stream-privacy.md`)
> and the 8-hour soak
> (CPU measured: 18% of one core, 1.5% of the whole PC; memory flat over 34 minutes). See the
> [Manual test checklist](#manual-test-checklist-spirit-temple); ticked items are the confirmed ones.

| Phase | What | State |
| --- | --- | --- |
| 1 | Tray skeleton: icon, menu, autostart | **confirmed on Spirit Temple** (icon, tooltip, menu, Settings, Exit, second-instance guard, autostart) |
| 2 | Minimal saver: clock + ambient animation, exits on input, `/s`, subprocess | working on Spirit Temple; see checklist for what is left |
| 3 | Keep-awake (`SetThreadExecutionState`) and the remote-sleep test | **confirmed on Spirit Temple** (request held, remote sleep works, transfers keep running) |
| 4 | **Apollo / Artemis: stream awareness.** While a stream is active the saver runs on the physical monitors only (never on the virtual display), ignores the client's input, never takes focus, and starts and stops by itself. On by default, with a setting to turn it off | brainstorm and design, see [`docs/stream-privacy.md`](docs/stream-privacy.md) |
| 5 | **Packaging and technical features.** PyInstaller exe, install and uninstall, a settings GUI, and the other technical features | not started |
| 6 | **Visuals.** A Zelda-themed rework, light audio, refined visuals, new layouts and a set of widgets (this absorbs the old text, slideshow and mixed modes and the live transfer rates) | not started |

*Plan revised 2026-10-09 at Luca's request. Phases 1 to 3 are unchanged. The old phase 4 (text and slideshow modes)
and old phase 6 (transfer rates) now live inside the new phase 6 as widgets.*

The full brief is in [`docs/handoffs/saria-song-handoff.md`](docs/handoffs/saria-song-handoff.md).

## Requirements

* Windows 10 or 11, 64-bit
* **Python 3.13** (64-bit). The cloud sessions that write the code use 3.13, so use the same
  here. Get it from python.org and tick "Add python.exe to PATH" (or use the `py` launcher).
* Dependencies are pinned in [`requirements.txt`](requirements.txt): `pygame`, `pystray`, `Pillow`.

## Quick start (PowerShell)

Install Python 3.13 first if you have not: `winget install -e --id Python.Python.3.13`, then
**close and reopen PowerShell**. Use a normal (not "Run as administrator") window and a normal
folder such as `$HOME\Projects`, not `C:\Windows\System32`.

```powershell
git clone https://github.com/WandeR22LSTR/Sarias-Song.git
cd Sarias-Song

# Create .venv and install the pinned dependencies (add -Dev to also get pytest).
powershell -ExecutionPolicy Bypass -File .\scripts\dev-setup.ps1

# Run the tray app. A green note appears in the tray (check the ^ overflow area).
.\.venv\Scripts\python.exe .\src\tray.py
```

The script calls the venv's `python.exe` directly, so you never need to "activate" the
venv (which the default Windows execution policy blocks).

Left-click the note to start the saver. Right-click for **Start screensaver / Settings / Exit**.

To try just the saver, in a window instead of fullscreen:

```powershell
cd src
..\.venv\Scripts\python.exe -m saver.main /s --windowed
```

### Start at login

```powershell
.\.venv\Scripts\python.exe .\src\tray.py --install-autostart     # enable
.\.venv\Scripts\python.exe .\src\tray.py --uninstall-autostart   # disable
```

**Why a Startup-folder shortcut and not a Task Scheduler task?** It needs no admin rights;
it is visible and switchable in Task Manager > Startup apps and Settings > Apps > Startup;
removing it is deleting one file; and it avoids Task Scheduler's command-line defaults
("stop after 72 hours", "only on AC power") that would quietly kill a tray app. Task Scheduler's
main extra, restarting on crash, is not needed: the saver is its own process and the tray is tiny.
The shortcut lives in `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Saria's Song.lnk`
and runs `pythonw.exe src\tray.py` (no console window). The packaged exe (phase 5) will use the same mechanism.

## Configuration

`config.json` in the repo root (next to the exe once packaged). Right-click the tray icon >
**Settings** opens it in Notepad. Changes apply the next time the saver starts. A mistake never
stops the saver: bad values fall back to the defaults, and the problem is written to `logs\saver.log`.

| Key | Default | Meaning |
| --- | --- | --- |
| `mode` | `"clock"` | Only `clock` exists so far (`text`, `slideshow`, `mixed` and more come with the phase 6 widgets). |
| `colors.background` / `background_edge` | `#0b1410` / `#040806` | Centre and corners of the backdrop. Deep green-black, not pure black. |
| `colors.accent` | `#7fd48a` | Fireflies and the clock's halo. |
| `colors.text` / `dim` | `#cfe8d4` / `#5f8a68` | Time and date. |
| `font` | `"Segoe UI Light, Segoe UI, Calibri"` | Tried in order; falls back to pygame's built-in font. `logs\saver.log` says which file was picked. |
| `clock.format_24h` / `show_seconds` / `show_date` | `true` / `false` / `true` | |
| `animation_speed` | `1.0` | `0` freezes the fireflies; max `5`. |
| `monitors` | `"all"` | `"all"` covers every display; `"primary"` only the main one. |
| `grace_seconds` | `2.0` | Input is ignored for this long after launch. |
| `exit_on` | `["key","mouse_move","mouse_click"]` | Remove entries to ignore that input. Cannot be empty. |
| `mouse_move_threshold_px` | `12` | Pointer must travel this far to count as movement (ignores jitter). |

## How it works

* **Tray** (`src/tray.py`, `pystray` + `Pillow`): draws its own icon, runs one instance per login,
  and launches the saver with `python -m saver.main /s` as a **separate process**. A saver crash
  cannot take the tray down; the tray logs the exit code.
* **Saver** (`src/saver/`, `pygame`): one borderless window covering the chosen monitors
  ("fake fullscreen": no display-mode switch, so it behaves with streaming capture). It supports
  the Windows screensaver arguments `/s` (run), `/c` (open config), `/p` (preview, exits at once), so it could
  become a real `.scr` later. With no argument it runs, unlike a real `.scr`.
* **Rendering** is built for long runs: a pre-baked background and dirty-rectangle updates,
  capped at 30 fps. The clock's glow is baked into the backdrop and only redone when the time text
  changes or the clock drifts a pixel (it drifts a few pixels over minutes to avoid burn-in), so a
  normal frame only touches the fireflies and the digits and tells the display about each rectangle once.
  Measured headless in the cloud on a two-monitor layout (4480x1440): a frame's work fell from 8-9 ms to
  about 3 ms and the pixels pushed per frame from 5-7 M to 1-1.5 M. Measured on Spirit Temple (two
  monitors, 1080p + 1440p, seconds on, 2026-10-08):

  | | cpu, one core | cpu, whole 12-thread PC | work per frame | memory |
  | --- | --- | --- | --- | --- |
  | before the glow was baked | 36% | 3.0% | 12.7 ms | 108-113 MB |
  | after | 18% | 1.5% | 6.2 ms | 117-122 MB, flat over 34 minutes |

  With seconds on there is still one 80-100 ms frame per second (the glow is rebuilt when the seconds
  digit changes), which is why a minute logs about 1725 frames instead of 1800. It is not visible.
* **No banding.** The background, the clock's glow and the fireflies are all only a few colour levels
  bright, so rounding them to 8 bits leaves visible steps on a panel that shows dark detail. Each is
  computed in floating point and given a little noise *before* the final rounding, which turns the
  steps into fine grain. Each of these was a real bug reported from the 1440p monitor.
* **Logs** go to `logs\tray.log`, `logs\saver.log` and `logs\saver-stderr.log`. When something misbehaves,
  send these.
* **The app reports its own CPU and memory**, because the saver covers the screen and cannot be watched in
  Task Manager. `logs\saver.log` gets a `perf:` line 10 seconds after the saver starts and then one a minute
  (about 480 lines over 8 hours), plus a whole-run total when it exits; `logs\tray.log` gets a `tray perf:`
  line after a minute and then every 5 minutes. A line reads like
  `cpu 4.3% of one core (1.08% of all 4 logical processors, as Task Manager shows), memory 57 MB; 301 frames,
  work avg 1.3 ms, worst 12 ms`. "% of one core" is 100 when a core is fully busy; the bracketed figure is
  the share of the whole PC, which is what Task Manager's CPU column shows. Memory is the working set, as in
  Task Manager. A memory figure that keeps climbing across an 8-hour run would be a leak.
* **The clock is laid out on a fixed grid.** Each digit has its own slot as wide as the widest digit, a
  one-digit hour in 12-hour mode keeps an empty tens slot, and AM/PM share one slot. In a font with
  proportional digits (a "1" narrower than a "0") centring the whole string made the clock change width on
  every tick and shift around the middle; now nothing moves when digits change.

```
src/
  tray.py          tray app entry point
  launcher.py      starts/stops the saver subprocess, opens config.json
  autostart.py     Startup-folder shortcut
  config.py        config.json loading and validation
  icon.py          the note icon, drawn with Pillow (python src/icon.py regenerates assets/)
  winapi.py        every Windows-only ctypes call, behind a platform check
  applog.py        rotating log files
  saver/
    main.py        entry point, window, event loop
    render.py      layout, clock text, fireflies, drawing
    exitpolicy.py  grace period and mouse-jitter rules
assets/            saria-song.ico / .png (generated)
tests/             unit tests (run anywhere)
scripts/           dev-setup.ps1
docs/handoffs/     project brief
```

## Development

Code is written in a cloud session and tested on Spirit Temple: the cloud cannot show a Windows
tray, fullscreen window or startup shortcut, so those are covered by mocked unit tests plus the
checklist below. Luca's test report is the ground truth.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev-setup.ps1 -Dev
.\.venv\Scripts\python.exe -m pytest
```

The tests run headless (SDL's dummy video driver) on any platform.

## Manual test checklist (Spirit Temple)

Only things a unit test cannot see. Tick them off and report back what failed (screenshot,
the relevant `logs\*.log` lines, or just "works").

**Tray (phase 1)**
- [x] A green music note appears in the tray (maybe under the `^` overflow); it is legible on the dark taskbar.
- [x] Hovering shows "Saria's Song".
- [x] Right-click shows **Start screensaver / Settings / Exit**.
- [x] **Settings** opens `config.json` in Notepad.
- [x] Editing `config.json` (e.g. `clock.show_seconds`) changes the next saver launch, with no code edits.
- [x] Starting `tray.py` a second time does not create a second icon. (`tray.log`: `another tray instance is
      already running; exiting`; the guard returns before any icon code runs.)
- [x] **Exit** removes the icon and the `pythonw`/`python` process ends. (`tray.log`: `tray stopped`;
      `Get-Process python, pythonw` printed nothing afterwards.)
- [x] `--install-autostart`, then sign out and in: the icon is back. `--uninstall-autostart` removes it.
      (Reported working. The shortcut was inspected: target `...\.venv\Scripts\pythonw.exe`, arguments
      `"...\src\tray.py"`, working directory = the repo. It points at this repo folder, so moving the repo
      breaks it until `--install-autostart` is run again.)

**Saver (phase 2)**
- [x] Left-click the icon: the saver is on screen in about a second. (Logs: about 0.25 s from spawn to running, five runs.)
- [x] It covers **every** monitor (clock centred on each) and the taskbar is hidden behind it. (Log: 4480x1440 window at (-1920,0), 2 monitors.)
- [x] Text is sharp, not blurry (DPI scaling is handled). The display scaling % was not reported.
- [x] Clock font: the thin Segoe UI Light look. (Log: `C:\WINDOWS\Fonts\segoeuil.ttf`.)
- [x] Fireflies drift slowly and smoothly; no tearing, stutter or visible trails. (Reported fine.)
- [x] The clock does not shift or change width when a digit changes (fixed-grid layout; confirmed on Spirit Temple).
- [x] Moving the mouse or pressing keys during the first 2 seconds does nothing.
- [x] After 2 seconds a **key press** exits (this checks that the saver really got keyboard focus) and so does a
      **real mouse move**. (Log: `exit on key`, `exit on mouse_move`.)
- [x] A **click** exits, and a tiny 1-2 pixel nudge does not.
- [x] After exit, windows and the taskbar are exactly as before (reported fine), and the saver process ends
      (`logs\tray.log`: `saver exited normally`).
- [x] Double-clicking the tray icon starts only one saver. (The tray is hidden once the saver is up, so
      a second click can only happen in the first fraction of a second.)
- [ ] Streamed via Apollo/Artemis: the saver shows on the stream and input from the client exits it.
- [x] CPU and memory, read from the `perf:` lines in `logs\saver.log`: 18% of one core (1.5% of the whole
      PC), 6.2 ms of work per frame, 117-122 MB and flat over 34 minutes (two monitors, seconds on).

**Keep-awake and remote sleep (phase 3, confirmed)**

The saver holds `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` while it is on screen and
clears it on exit (`logs\saver.log`: `keep-awake on` / `keep-awake off`). It blocks idle sleep only. It
does not force the monitors on, and does not touch power plans or the registry. A crash releases it
automatically (Windows drops the request when the thread dies).
- [x] **Quick proof it is in effect.** The saver covers the screen and any input closes it, so you cannot
      type while it is up: start a delayed snapshot first, then launch the saver. In an **administrator**
      PowerShell run `Start-Sleep 25; powercfg /requests | Out-File $HOME\requests-during.txt`, then click the
      tray icon and leave the PC alone for 35 seconds before pressing a key. Afterwards
      `Get-Content $HOME\requests-during.txt` should show a `python.exe` / `pythonw.exe` entry (the `.venv`
      Python) under **SYSTEM**, and **no** entry under DISPLAY. A plain `powercfg /requests` after the saver
      has closed should show neither. (Other programs, such as a torrent client, may add their own entries.)
      *First run on Spirit Temple (2026-10-09) found the entry under DISPLAY and nothing under SYSTEM:
      SDL's own request to keep the display on had replaced keep-awake's. Fixed by telling SDL to allow the
      screensaver (`SDL_VIDEO_ALLOW_SCREENSAVER`, `set_allow_screensaver`) and re-asserting the request every
      minute. **Re-run after the fix, confirmed:** SYSTEM shows the `.venv` `pythonw.exe`, DISPLAY shows
      nothing, and `saver.log` says `keep-awake on (previous state 0x80000000)`.*
- [x] **Transfers keep running with the saver up.** Luca's PC is deliberately set to never sleep, and the app
      never changes that, so no setting needs touching. Start a large torrent download and a large Google Drive
      upload (the Drive app), note their progress, run the saver for 10+ minutes without touching the PC, then
      check that both moved on and neither paused. (Verified by Luca, 2026-10-09: both kept running.)
- [ ] *Optional:* **Windows honours the request.** Only worth doing for extra proof, since the `powercfg` item
      above already shows the request is held. It temporarily shortens the sleep timer and restores it by itself
      (in an administrator PowerShell, after confirming `powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE`
      shows `0x00000000`):
      `try { powercfg /change standby-timeout-ac 1; Start-Sleep 420 } finally { powercfg /change standby-timeout-ac 0 }`
      then start the saver, leave the PC alone for 8 minutes, and check `saver.log` has a `perf:` line each
      minute with no gap and the Kernel-Power event log has no Id 42. If the PowerShell window is closed mid-test
      the restore does not run: put it back with `powercfg /change standby-timeout-ac 0`.
- [x] **Remote-sleep test:** with the saver running, send the usual "lullaby" sleep command from the
      Raspberry Pi. The PC must still go to sleep. Then "requiem" wakes it and note what state the saver is in.
      Keep-awake must only block *idle* sleep, never this deliberate command.
      (Reported by Luca 2026-10-09: the saver was on screen, the PC went to sleep and stayed off for at least a
      minute, and requiem woke it. Kernel-Power logged Id 42 at 11:30:22 PM and Id 107 at 11:30:23 PM; those
      timestamps are one second apart despite the minute-long sleep, which is unexplained and does not affect
      the result. Luca was in bed, not at the PC. After waking: the Windows lock screen, then the normal
      desktop after signing in. The saver had already closed itself as the PC went to sleep:
      `saver.log` has `exit on mouse_move` 60 ms before the sleep event, i.e. Windows sent a mouse move
      during the sleep/lock sequence and the saver treated it as input. This is accepted behaviour: the saver
      does not outlive a sleep or lock. The exit line now also logs the pointer position, so a system-made
      move can be told from a real one.)

**Soak (acceptance criterion)**
- [ ] After 8 hours up: no crash, no visible slowdown. Memory stays flat in the `tray perf:` lines (every 5
      minutes) and, with the saver left running, in the `perf:` lines in `saver.log` (every minute).

## Troubleshooting

* **Nothing happens on click:** read `logs\tray.log`; it records every launch and exit code.
* **Saver flashes and closes:** read `logs\saver.log` and `logs\saver-stderr.log`.
* **Wrong font:** check the `font:` line in `logs\saver.log`; set `font` in `config.json` to an installed font name.
* **Multi-monitor looks wrong** (offset, blurry, wrong scaling on a second display): set `"monitors": "primary"`
  and report your monitor arrangement and scaling.
* **PowerShell refuses to run the script:** use the `powershell -ExecutionPolicy Bypass -File ...` form shown above.
* **"Python was not found; run without arguments to install from the Microsoft Store":** that is Windows'
  placeholder `python.exe`, meaning Python is not installed. Install 3.13 (see Quick start) and reopen PowerShell.
  `dev-setup.ps1` detects this, also looks in Python's default install folders (so a Python installed a
  minute ago works without reopening PowerShell), and lists what it checked if it still finds nothing.
* **`..venv\Scripts\python.exe is not recognized`:** the path lost a backslash. It is
  `.\.venv\Scripts\python.exe` (dot, backslash, dot, `venv`). It also just means setup has not succeeded yet.
