# Saria's Song

A small Windows tray app with a green music-note icon. Click it and a dark, calm,
fullscreen screensaver comes up: a soft clock and slow green fireflies drifting like
the lights in Kokiri Forest. Built to be comfortable on a streamed display.

Part of Luca's Ocarina-of-Time-themed project family. Standalone, with no dependency
on the Ice Cavern hub.

> **Status: phases 1 and 2 are written, not yet tested on Windows.** Everything that can
> run anywhere is unit-tested; the Windows-only behaviour (tray, fullscreen window,
> startup shortcut) has never been seen on a real Windows machine yet. See
> [Manual test checklist](#manual-test-checklist-spirit-temple).

| Phase | What | State |
| --- | --- | --- |
| 1 | Tray skeleton: icon, menu, autostart | written, awaiting Windows test |
| 2 | Minimal saver: clock + ambient animation, exits on input, `/s`, subprocess | written, awaiting Windows test |
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
* **Rendering** is built for long runs: a pre-baked, dithered background and dirty-rectangle
  updates, capped at 30 fps. A steady frame takes about 2 ms on 1080p and 5 ms across 4480x1440
  in headless tests here. The clock drifts a few pixels over minutes to avoid burn-in.
* **Logs** go to `logs\tray.log`, `logs\saver.log` and `logs\saver-stderr.log`. When something misbehaves,
  send these.

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
- [ ] A green music note appears in the tray (maybe under the `^` overflow); it is legible on the dark taskbar.
- [ ] Hovering shows "Saria's Song".
- [ ] Right-click shows **Start screensaver / Settings / Exit**.
- [ ] **Settings** opens `config.json` in Notepad.
- [ ] Starting `tray.py` a second time does not create a second icon.
- [ ] **Exit** removes the icon and the `pythonw`/`python` process ends.
- [ ] `--install-autostart`, then sign out and in: the icon is back, and "Saria's Song" is listed in
      Task Manager > Startup apps. `--uninstall-autostart` removes it.

**Saver (phase 2)**
- [ ] Left-click the icon: the saver is on screen in about a second.
- [ ] It covers **every** monitor (clock centred on each) and the taskbar is hidden behind it.
- [ ] Text is sharp, not blurry (DPI scaling is handled). Note your display scaling %.
- [ ] Clock font: is it the thin Segoe UI Light look? (`logs\saver.log` shows the font file chosen.)
- [ ] Fireflies drift slowly and smoothly; no tearing, stutter or visible trails.
- [ ] Moving the mouse or pressing keys during the first 2 seconds does nothing.
- [ ] After 2 seconds: a **key press** exits (this checks that the saver really got keyboard focus), as does a
      **click** and a **real mouse move**. A tiny 1-2 pixel nudge does not.
- [ ] After exit, windows and the taskbar are exactly as before, and no `python` process remains in Task Manager.
- [ ] Clicking the tray icon again while the saver is up does not stack a second saver.
- [ ] Streamed via Apollo/Artemis: the saver shows on the stream and input from the client exits it.
- [ ] Note the saver's CPU % in Task Manager after a minute (not measured on Windows yet; the design
      aims for low single digits, but please report the real number and your monitor setup).

**Keep-awake and remote sleep (phase 3, not yet written)**
- [ ] With the Windows sleep timer set low (e.g. 1 minute) and a large transfer running, the PC
      stays awake and the transfer finishes with no stall during 30+ minutes of saver.
- [ ] **Remote-sleep test:** with the saver running, send the usual "lullaby" sleep command from the
      Raspberry Pi. The PC must still go to sleep. Then "requiem" wakes it and the saver is still sensible.
      Keep-awake must only block *idle* sleep, never this deliberate command.

**Soak (acceptance criterion)**
- [ ] After 8 hours up: no crash, no visible slowdown; tray memory modest (Task Manager).

## Troubleshooting

* **Nothing happens on click:** read `logs\tray.log`; it records every launch and exit code.
* **Saver flashes and closes:** read `logs\saver.log` and `logs\saver-stderr.log`.
* **Wrong font:** check the `font:` line in `logs\saver.log`; set `font` in `config.json` to an installed font name.
* **Multi-monitor looks wrong** (offset, blurry, wrong scaling on a second display): set `"monitors": "primary"`
  and report your monitor arrangement and scaling.
* **PowerShell refuses to run the script:** use the `powershell -ExecutionPolicy Bypass -File ...` form shown above.
* **"Python was not found; run without arguments to install from the Microsoft Store":** that is Windows'
  placeholder `python.exe`, meaning Python is not installed. Install 3.13 (see Quick start) and reopen PowerShell.
  `dev-setup.ps1` detects this and tells you.
