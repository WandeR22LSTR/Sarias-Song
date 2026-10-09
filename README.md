# Saria's Song

A small Windows tray app with a green music-note icon. Click it and a dark, calm,
fullscreen screensaver comes up: a soft clock and slow green fireflies drifting like
the lights in Kokiri Forest. Built to be comfortable on a streamed display.

Part of Luca's Ocarina-of-Time-themed project family. Standalone, with no dependency
on the Ice Cavern hub.

> **Status: phases 1 and 2 are running on Spirit Temple; the checklist is partly ticked.**
> Confirmed so far (Luca, 2026-10-08/09, from screenshots, `logs\*.log` and testing): the tray icon,
> tooltip, menu and Settings; config changes applying on the next launch; the saver covering
> both monitors (one at negative coordinates) and hiding the taskbar; Segoe UI Light; exit on a
> key, mouse move or click, with the 2 s grace period and the tiny-nudge threshold; one saver only
> on a double-click; and, after fixes, no visible banding on the 1440p monitor. Not yet confirmed:
> firefly motion, desktop restored after exit, second-instance guard, Exit, autostart, streaming, CPU
> use and the long soak. See the
> [Manual test checklist](#manual-test-checklist-spirit-temple); ticked items are the confirmed ones.

| Phase | What | State |
| --- | --- | --- |
| 1 | Tray skeleton: icon, menu, autostart | icon, tooltip, menu, Settings confirmed; Exit, second instance and autostart still to test |
| 2 | Minimal saver: clock + ambient animation, exits on input, `/s`, subprocess | working on Spirit Temple; see checklist for what is left |
| 3 | Keep-awake (`SetThreadExecutionState`) and the remote-sleep test | not started |
| 4 | Config modes: `text`, `slideshow`, `mixed` | not started (config file and grace period exist) |
| 5 | PyInstaller exe, startup wiring, install/uninstall steps | not started |
| 6 | Stretch: live transfer rates with `psutil` | not started |

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
| `mode` | `"clock"` | Only `clock` exists so far (`text`, `slideshow`, `mixed` come in phase 4). |
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
  capped at 30 fps. A steady frame takes about 2.4 ms on 1080p, 4 ms on 1440p and 7 ms across
  both together (4480x1440) in headless tests in the cloud, so it is not a measure of Spirit Temple.
  The clock drifts a few pixels over minutes to avoid burn-in.
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
- [ ] Starting `tray.py` a second time does not create a second icon.
- [ ] **Exit** removes the icon and the `pythonw`/`python` process ends.
- [ ] `--install-autostart`, then sign out and in: the icon is back, and "Saria's Song" is listed in
      Task Manager > Startup apps. `--uninstall-autostart` removes it.

**Saver (phase 2)**
- [x] Left-click the icon: the saver is on screen in about a second. (Logs: about 0.25 s from spawn to running, five runs.)
- [x] It covers **every** monitor (clock centred on each) and the taskbar is hidden behind it. (Log: 4480x1440 window at (-1920,0), 2 monitors.)
- [x] Text is sharp, not blurry (DPI scaling is handled). The display scaling % was not reported.
- [x] Clock font: the thin Segoe UI Light look. (Log: `C:\WINDOWS\Fonts\segoeuil.ttf`.)
- [x] Fireflies drift slowly and smoothly; no tearing, stutter or visible trails. (Reported fine.)
- [ ] The clock does not shift or change width when a digit changes (needs the fixed-grid layout; retest).
- [x] Moving the mouse or pressing keys during the first 2 seconds does nothing.
- [x] After 2 seconds a **key press** exits (this checks that the saver really got keyboard focus) and so does a
      **real mouse move**. (Log: `exit on key`, `exit on mouse_move`.)
- [x] A **click** exits, and a tiny 1-2 pixel nudge does not.
- [x] After exit, windows and the taskbar are exactly as before (reported fine), and the saver process ends
      (`logs\tray.log`: `saver exited normally`).
- [x] Double-clicking the tray icon starts only one saver. (The tray is hidden once the saver is up, so
      a second click can only happen in the first fraction of a second.)
- [ ] Streamed via Apollo/Artemis: the saver shows on the stream and input from the client exits it.
- [ ] CPU and memory: run the saver for at least 70 seconds, then send the `perf:` lines from `logs\saver.log`
      (not measured on Windows yet; the design aims for low single digits). Mention your monitor setup.

**Keep-awake and remote sleep (phase 3, not yet written)**
- [ ] With the Windows sleep timer set low (e.g. 1 minute) and a large transfer running, the PC
      stays awake and the transfer finishes with no stall during 30+ minutes of saver.
- [ ] **Remote-sleep test:** with the saver running, send the usual "lullaby" sleep command from the
      Raspberry Pi. The PC must still go to sleep. Then "requiem" wakes it and the saver is still sensible.
      Keep-awake must only block *idle* sleep, never this deliberate command.

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
