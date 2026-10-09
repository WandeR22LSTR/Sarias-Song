# Stream privacy mode (requirement and design notes)

Status: **requirement captured, design pending facts from Spirit Temple. Nothing is built yet.**

## What Luca wants (2026-10-09)

> "streaming automatically runs the screen saver on the monitor but not the virtual display so I can hook
> into my pc privately. even better would be having that be the default and a setting toggle for the
> alternative."

Context given: with Apollo, a stream used to create a virtual display and switch the physical monitor off;
a recent behaviour change now **mirrors** instead.

So, when an Apollo stream is active:

1. The saver starts by itself on the **physical monitor(s)** so anyone at the PC sees only the saver.
2. It does **not** appear on the **virtual display** (what the Artemis client sees and controls).
3. This is the **default**, with a setting to switch to the alternative (see "Config" below).

## Why this is harder than it sounds

1. **Mirroring defeats it.** If Windows *duplicates* the physical monitor and the virtual display, they are
   one desktop and show the same pixels. A saver over the physical monitor is then also over what the client
   sees. Only an **extended** layout (the virtual display is its own region of the desktop) lets the saver
   cover just the physical monitors. Whether Apollo can be set to extend instead of mirror, and what its
   current setting is, is the first thing to find out.
2. **Input.** Everything the client types or clicks is injected as ordinary input into whatever window has
   focus. The saver today takes the foreground (that is how a key press exits it) and exits on any input. In
   this mode it must **never take focus** (otherwise the game stops receiving the client's keystrokes) and
   must **ignore input** (otherwise the first client key press closes it). It should end only when the
   stream ends or the user asks.
3. **Knowing when a stream is active.** Options, best to worst:
   - *Display topology.* The virtual display appears when a stream starts and (if Apollo is configured so)
     disappears when it ends. The tray could watch for a display whose adapter/device name marks it as
     virtual. Needs no Apollo setup, but depends on the real names Windows reports.
   - *Apollo command preparations.* Apollo can run a command when a stream starts and another when it ends
     (Configuration or per-application "Command Preparations"). They would call something like
     `tray.py --stream-start` / `--stream-end`, which signal the running tray. Reliable, but Luca has to
     paste two commands into Apollo, and the commands' security context (user vs SYSTEM session) has to be
     checked, because a signal across sessions needs a different mechanism.
4. **Which displays are "virtual".** The saver's `monitors` setting is currently `all` or `primary`. It needs
   a third meaning: every display except virtual ones.

## Facts needed from Spirit Temple before building

Run these in Windows PowerShell **twice**: once with no stream, once while connected from Artemis (open a
PowerShell on the host through the stream). Paste both outputs.

```powershell
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Screen]::AllScreens | Format-Table DeviceName, Primary, Bounds -AutoSize
Get-CimInstance Win32_VideoController | Format-Table Name, Status, CurrentHorizontalResolution, CurrentVerticalResolution -AutoSize
Get-PnpDevice -Class Monitor | Format-Table FriendlyName, Status, InstanceId -AutoSize
```

Also needed:

- Apollo version, and the **Display Device** settings in its web UI (Configuration > Audio/Video): whether
  it is set to extend, mirror, or leave the layout alone.
- Does the virtual display disappear when the stream ends, or stay?
- While streaming, does the physical monitor show the same picture as the client (mirrored) or something else?

## Proposed shape (subject to the facts above)

- New config:
  - `"stream_privacy": true` (default). Auto-start the saver on physical displays when a stream starts and
    close it when the stream ends. `false` keeps today's behaviour (the saver only runs when launched).
  - `"monitors": "physical"`: all displays except virtual ones (the setting `stream_privacy` implies).
- In this mode the saver: covers physical displays only; is created without activation or focus; ignores
  input; exits on stream end (and on an explicit tray action).
- The tray owns the detection and the start/stop, and logs every decision to `logs\tray.log`.

## Open questions for Luca

- If Apollo can only mirror, is it acceptable that this mode works only when the virtual display is set to
  extend? (If mirrored is the only option, a saver on the physical monitor would also be on the stream, and
  privacy would need a different approach, such as turning the physical monitor off.)
- Should the saver be allowed to exit if someone touches the physical keyboard or mouse, or never while a
  stream is active?
