# Phase 4: Apollo / Artemis stream awareness (design notes)

Status: **brainstorm, nothing built.** Last updated 2026-10-09. This is a working document: it is meant to be
argued with and revised as Luca runs the experiments below.

## What Luca wants

> "streaming automatically runs the screen saver on the monitor but not the virtual display so I can hook
> into my pc privately. even better would be having that be the default and a setting toggle for the
> alternative."

### The use error that started this

> "you need to hit a keybind to exit streaming in moonlight, which turns the saver off"

My reading, **to be confirmed with Luca**: the saver is up on the host; Luca is connected from a client; he
ends the stream with the client's quit keybind; the keys of that chord reach the host as ordinary keyboard
input, so the saver (which closes on any key) closes. The program is doing exactly what it was designed to do
("any input exits"), but not what Luca would want, because he is leaving the PC unattended and the saver was
the thing hiding the desktop.

### Goals

| | Goal |
| --- | --- |
| G1 | Input coming from a streaming client never dismisses the saver on the physical monitors. |
| G2 | While a stream is active the saver covers the **physical** monitors only, never the virtual display the client sees. |
| G3 | It starts by itself when a stream starts. What happens when the stream ends is an open decision (see below). |
| G4 | On by default, with a setting for the alternative (today's behaviour). |
| G5 | It never takes keyboard focus from the game, or the client's keystrokes would go to the saver instead. |

## What is known, and what is not

**From documentation (links are the sources):**

- Apollo shows a virtual display built on SudoVDA, which it creates when a stream begins. If a stream shows
  the same picture as the main screen, Windows may be in *mirror* mode; the Apollo FAQ's fix is Win+P, pick
  *Extended*, then fully exit and restart Apollo, once.
  ([Apollo FAQ](https://github.com/ClassicOldSong/Apollo/wiki/FAQ))
- The built-in virtual display entry is described as a special "safe mode" entry that does not run commands,
  and individual apps have an "Always use Virtual Display" option. If prep commands are used for detection,
  they must be attached to a real app entry. (Same FAQ; **verify in Luca's Apollo UI.**)
- Sunshine and Apollo run **do/undo command pairs** around an app, with an `elevated` flag
  ([Sunshine prep_cmd](https://docs.lizardbyte.dev/projects/sunshine/master/structconfig_1_1prep__cmd__t.html)).
  Apollo reworked elevated commands so that, when installed as a service, they launch as the current user
  ([Apollo commit](https://izackpgit.duckdns.org/izackp/Apollo/commit/430a43969892098f40e18d378c9e9a30fed11e0f)).
  **Which user and session a non-elevated command runs in is not confirmed.**
- Windows marks injected input. A low-level keyboard hook receives `LLKHF_INJECTED` (0x10)
  ([KBDLLHOOKSTRUCT](https://learn.microsoft.com/windows/win32/api/winuser/ns-winuser-kbdllhookstruct)), and a
  low-level mouse hook receives `LLMHF_INJECTED` (0x1)
  ([MSLLHOOKSTRUCT](https://learn.microsoft.com/windows/win32/api/winuser/ns-winuser-msllhookstruct)).
- Raw Input is **not** a reliable way to spot injected input: a NULL `hDevice` is only documented for precision
  touchpads ([RAWINPUTHEADER](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-rawinputheader)).

**Not verified, and each could change the plan:**

- That Apollo injects the client's keyboard and mouse with `SendInput` (so they would carry the injected flag).
- That the client's quit chord leaks its modifier keys to the host. (My explanation of the use error.)
- Whether prep commands run in Luca's user session, and which environment variables they receive.
- Whether, in Luca's setup, the virtual display disappears when the stream ends.
- Whether the "mirroring" Luca sees is Windows' Win+P state, or something Apollo sets.

## Ideas

**1. Know where input came from (injected vs physical).** A low-level hook in the saver can tell client input
from hardware input. If Apollo's input is flagged, G1 is solved without any Apollo integration at all.
Costs: Windows-only code that cannot be tested in the cloud; the hook must answer quickly or Windows drops it;
and some antivirus products dislike keyboard hooks, so it should record only the injected bit, never what was
typed. Needs experiment E2.

**2. Cheap stopgaps while we find out.**
(a) Log which key or button ended the saver (we already log the pointer position for mouse exits).
(b) Treat modifier-only key presses (Shift, Ctrl, Alt) as not enough to exit. If the quit chord only leaks
modifiers, this alone fixes the use error. Trade-off: tapping Shift would no longer wake the saver locally.

**3. Know when a stream is active.**

| Way | For | Against |
| --- | --- | --- |
| The virtual display appears (monitor list or display change) | No Apollo setup | Depends on the virtual adapter's name and on the display really disappearing afterwards |
| Apollo runs a command on start and end (`tray.py --stream-start` / `--stream-end`) | Exact | Luca must add them in Apollo, only on a real app entry, and the tray must receive the signal across sessions |
| Reading Apollo's log | No setup | Breaks if the wording or path changes |

Likely answer: support the display-appearance method by default and the command method as an explicit
override, if experiment E1 shows the names are stable.

**4. A saver that is safe to leave beside a game.** Physical monitors only (a new `monitors: "physical"`);
created without activation (`WS_EX_NOACTIVATE`) and never brought to the front, so the game keeps focus (G5);
optionally click-through so a client pointer that strays onto a physical monitor does nothing.

**5. Input policy while streaming.** Ignore all input, or ignore only injected input, or ignore all input but
allow a deliberate local override (for example holding Esc for three seconds). Open decision.

**6. After the stream ends.** Either the saver stays until physical input (protects an unattended PC), or it
exits at once. Whichever it is, ignore input for a short *tail grace* after the stream ends, so the quit chord
cannot leak in just before the end.

## The prerequisite: an extended layout

A saver on the physical monitors that is not on the stream only works if the virtual display is its own part of
the desktop (*extended*). If Windows mirrors the physical monitor and the virtual display, they show the same
pixels and the saver is on the stream too. So the first fact needed is what Luca's layout really is while
streaming, and whether Apollo can be made to extend. If it can only mirror, privacy needs a different tool, such as
Apollo's old behaviour of turning the physical monitor off.

## Proposed slices

| Slice | What | Needs |
| --- | --- | --- |
| 4.0 | Experiments and logging only, no behaviour change | Luca runs E1, E2, E3 |
| 4.1 | Stopgap: modifier-only keys do not exit (setting) | Confirmation of the chord theory |
| 4.2 | Ignore injected input (setting) | E2 |
| 4.3 | `monitors: "physical"`, no focus, click-through | E1 |
| 4.4 | Stream detection, auto start and stop, tail grace | E1, E3 |
| 4.5 | Setting `stream_mode: "private"` (default) or `"off"`, a tray toggle, and the Apollo setup steps | The rest |

## Experiments

**E1: display facts.** In Windows PowerShell, once with no stream and once while connected from Artemis (open a
PowerShell on the host through the stream). These commands only read information:

```powershell
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Screen]::AllScreens | Format-Table DeviceName, Primary, Bounds -AutoSize
Get-CimInstance Win32_VideoController | Format-Table Name, Status, CurrentHorizontalResolution, CurrentVerticalResolution -AutoSize
Get-PnpDevice -Class Monitor | Format-Table FriendlyName, Status, InstanceId -AutoSize
```

Also: Apollo's version; its Display Device settings; whether the virtual display disappears when the stream
ends; and what Win+P shows while streaming.

**E2: input provenance.** A small read-only diagnostic (to be written) that prints whether each key and mouse
event is injected, while Luca types on the client and then on the physical keyboard. Answers whether Apollo's
input is flagged, and what the quit chord sends.

**E3: prep-command probe.** A harmless command in Apollo that appends the time, the user name and the session
to a file at stream start and end. Answers where commands run and what they receive.

## Risks

- Mirroring may make the headline feature impossible without changing how Apollo is set up.
- Injected-input detection depends on how Apollo injects input.
- A keyboard hook may attract antivirus attention, especially in the packaged exe.
- Apollo's behaviour has changed between versions already (monitor off, then mirror), and may again.
- Lock screens and sleep interact with all of this: the saver already closes itself when the PC sleeps.

## Decisions for Luca

1. Is my reading of the use error right?
2. While streaming, should the saver ignore all input, or only the client's?
3. When a stream ends, should the saver stay until someone touches the physical mouse or keyboard, or exit?
4. If Apollo can only mirror, what is acceptable instead?
