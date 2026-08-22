# Changelog

The `## vX.Y.Z` heading of each version is what the release workflow publishes as
the GitHub release body, so keep the headings exactly in that form.

## Unreleased

## v0.2.0

First release of the SteamOS fork. If you are on Bazzite, use
[the upstream plugin](https://github.com/srsholmes/onexplayer-apex-bazzite-fixes) instead —
this one targets SteamOS and refuses to act on anything else.

### The volume buttons work again

They were doing nothing at all. The buttons emit ordinary volume keys on the built-in
keyboard, but InputPlumber claims that keyboard for the Apex and grabs it exclusively —
and Steam replaces its output devices with a Steam Deck controller, which has no way to
emit a keyboard event. The presses arrived and stopped there.

The fix tells InputPlumber to read that one keyboard without confiscating it, which is
already how SteamOS treats the AYANEO KUN and the MSI Claw. Turn on **Volume Buttons** in
the plugin; no reboot needed.

### Gamepad recovery now works on current firmware

The recovery button could never have worked on an Apex with updated firmware. The USB
controller's address was written into the code as `65:00.4`, which is the address on the
original firmware only — on firmware 2.17 it is `c5:00.4`, and SteamOS's own InputPlumber
profile documents both. The plugin now finds the controller at runtime, in two steps, so it
also survives a future firmware change.

Two further defects went with it. Recovery waited a fixed two seconds and then checked once,
but the four internal devices take between 2.3 and 3.0 seconds to come back and the exact
delay varies between attempts — so a rebind that had actually worked was reported as failed.
The retry then tore down the chain that had just recovered. Recovery now waits for the
devices instead of guessing, and the retry only fires after a real timeout.

### Resume recovery, rebuilt

- **It installs on SteamOS now.** It wrote to `/usr/local/sbin`, which is on the read-only
  root, so enabling it failed unless you ran `steamos-readonly disable`. Worse, that path is
  replaced on every OS update, so the script would have vanished at the next update with the
  toggle still reading as enabled. It goes to `/var/lib` instead.
- **No more background daemon.** It kept a `dbus-monitor` running for the whole session just
  to notice resumes. systemd already reaches its sleep target on the way out of sleep, so a
  one-shot unit does the same job with nothing running in between.
- **It no longer rebinds on every resume.** It checked nothing before acting, so a healthy
  controller was torn down and four working devices re-enumerated after every single sleep.
- **It waits for the resume to finish** before touching anything, and restarts InputPlumber
  afterwards so the gamepad is picked back up.

The failure it addresses is real: twice in 14 recorded resumes, the USB controller did not
come back from sleep and the kernel dropped the gamepad along with it. Sleep length is not
the trigger — it happened on a 26-minute sleep and on a 15-second one.

> **Still opt-in.** The trigger fires correctly on a real failure, about 19 ms after the
> resume. The recovery itself has not yet completed successfully during one: the first attempt
> acted too early and locked the machine up, which is why it now waits first. That wait is a
> safety margin chosen from two data points, not a measured threshold.

### SteamOS-only, and much smaller

Six of the nine original fixes are gone, because the SteamOS kernel and InputPlumber do
their jobs natively: fan control, the Turbo and Home buttons, the back paddles, the joystick
ring LEDs and the sleep workarounds are all handled in-tree. Keeping stubs for them would
only have added ways to fight the drivers. Their code, docs and diagnostic scripts went with
them, along with a 6.8 MB third-party binary that had no business in an MIT repository.

What is left is the three fixes above plus the speaker EQ, and a platform guard: on anything
that is not a SteamOS Apex the plugin logs why and takes no automatic action.

### Known limitations

- **The speaker EQ also affects headphones.** SteamOS exposes one `analog-stereo` sink for
  the whole card, with no separate speaker sink as on Bazzite. A port-aware version is next.
- **Resume recovery is unproven under a real failure** — see the note above.
- **Verified on one machine only**, an Apex on firmware 2.17 running SteamOS 3.7.

### Installation

Download the zip below, extract it into `~/homebrew/plugins/`, then restart Decky:

```
sudo systemctl restart plugin_loader.service
```
