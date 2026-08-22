# OneXPlayer Apex — SteamOS Fixes

A [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader) plugin for the **OneXPlayer Apex** (AMD Ryzen AI Max+ 395 "Strix Halo") running **SteamOS**.

> **On Bazzite, use the [upstream plugin](https://github.com/srsholmes/onexplayer-apex-bazzite-fixes) instead.** This is a SteamOS-only fork: it removes the HHD-era fixes, which SteamOS does not need and which would conflict with its kernel drivers. The plugin refuses to run automatically on anything that is not SteamOS on an Apex.

## What SteamOS already handles

Most of what the upstream plugin fixes on Bazzite is shipped in-tree by SteamOS (verified on kernel `6.18.42-valve2-neptune` with InputPlumber 0.78.0). **You do not need a plugin for any of this:**

| Feature | Provided by |
|---|---|
| EC sensors, fan RPM & PWM | `oxpec` in-tree, autoloads via DMI modalias → `hwmon` `oxp_ec` |
| Face buttons, Turbo, KB, Orange button | `hid-oxp` + `/usr/share/inputplumber/capability_maps/onexplayer_type8.yaml` |
| Back paddles (L4/R4) | same — reported as `Left`/`RightPaddle1`, mapped to the virtual controller |
| Joystick ring RGB | `hid-oxp` → `/sys/class/leds/oxp:rgb:joystick_rings` |
| Light sleep (s2idle) | `amd_iommu=off` already in the cmdline, `mem_sleep` defaults to `s2idle` |

Do **not** install the upstream plugin's back paddle fix on SteamOS: it writes a persistent `0xB4` firmware remap that `hid-oxp` does not expect.

## Features

### Gamepad Recovery
The Apex's internal gamepad, OXP buttons and internal keyboard all hang off a single internal USB hub (`1a86:8091`) behind one xHCI controller. That hub sometimes drops a few seconds after boot, taking all three with it. InputPlumber has usually already published its virtual controller by then, so Steam shows a gamepad that answers nothing.

- **Automatic:** checked on every plugin load, rebinds the xHCI controller if the internal devices are missing
- **Manual:** a *Recover Gamepad* button for when the controller goes silent mid-session

### Resume Recovery
Installs a `Type=oneshot` systemd unit ordered after the sleep targets, so systemd runs the
recovery once per resume with no daemon in between. The script checks the chain first, waits for
the resume to finish, rebinds only if needed, then restarts InputPlumber.

The failure it addresses is real and reproducible: the xHCI controller sometimes does not come
back from s2idle, and the kernel drops the internal hub and everything behind it.

```
xhci_hcd 0000:c5:00.4: xHCI host controller not responding, assume dead
xhci_hcd 0000:c5:00.4: HC died; cleaning up
usb 1-1: PM: dpm_run_callback(): usb_dev_resume returns -22
```

Observed twice in 14 recorded resumes on firmware 2.17, on sleeps of 26 minutes and 15 seconds —
duration is not the trigger. Both times the GPU had thrown a warning out of
`amdgpu_dm_atomic_commit_tail` in the same resume; the internal xHCI is function 4 of the same
PCI device whose function 0 is the GPU.

> The trigger has fired correctly on a real failure, ~19 ms after the resume. The **recovery**
> under a real failure has not yet completed successfully: the first attempt rebound too early
> and hung the machine, which is why the script now waits before touching the controller. That
> wait is a margin, not a measured threshold. Treat this one as opt-in until it has been through
> a real `HC died` on this version.

### Volume Buttons
Makes the volume buttons work again. They emit `KEY_VOLUMEUP` / `KEY_VOLUMEDOWN` (scancodes
`0xb0` / `0xae`) on the built-in AT keyboard, which InputPlumber lists as an Apex source device
and grabs exclusively — while Steam replaces the profile's `target_devices` with `deck-uhid`
alone, leaving no keyboard target able to re-emit them. The presses reach InputPlumber and stop
there.

The fix adds `passthrough: true` to that one source device, documented in InputPlumber's schema
as *"events will be read from this device, but the source device will not be hidden or
grabbed"*. It is how SteamOS already handles the AYANEO KUN and the MSI Claw.

The override is written to `/etc/inputplumber/devices.d/` and **derived** from whatever config
InputPlumber currently ships, with the source file's hash recorded in the generated header. The
plugin rebuilds it on start if a SteamOS update has changed the original, so our copy cannot
silently mask theirs.

### Speaker DSP (EQ Enhancement)
Applies a parametric EQ to the internal speakers using PipeWire's built-in filter-chain. The Apex's speakers sound tinny and lack bass out of the box.

- **3 built-in presets**: Balanced, Bass Boost, Treble — tuned at 100% volume without clipping
- **Custom profiles**: copy a preset and tweak the 7-band EQ (64 Hz to 16 kHz, +/-15 dB per band)
- **Original Sound toggle**: A/B your EQ against the raw output
- **Test Sound**: plays a bundled track ([NCS](https://ncs.io/) licensed)

> **Known limitation on SteamOS.** SteamOS exposes a single `analog-stereo` sink for the card — there is no dedicated speaker sink as on Bazzite's UCM profile. The EQ therefore applies to headphones as well. A port-aware version is the next planned change.

![EQ Sliders](screenshots/eq-sliders.png)

## Installation

Requires [Decky Loader](https://github.com/SteamDeckHomebrew/decky-loader).

```bash
cd decky-plugin
bun install
bun run package
sudo unzip -o OneXPlayer_Apex_SteamOS_Tools.zip -d ~/homebrew/plugins/
sudo systemctl restart plugin_loader.service
```

Or install the zip through Decky's **Developer mode → Install Plugin from ZIP File**.

## Notes

- **Requires root.** The plugin runs with the `root` flag.
- **Writable paths.** On SteamOS `/` (and so `/usr`) is read-only and replaced on update, while `/etc` is an overlay backed by `/var` and `/var` is a separate filesystem — both writable without `steamos-readonly disable`. Persistent state belongs in `/var`, units in `/etc/systemd/system`.
- **Platform guard.** The plugin checks `ID=steamos` in `/etc/os-release` and the DMI product name. On a mismatch it logs and performs no automatic action.

## Relationship to upstream

Forked from [srsholmes/onexplayer-apex-bazzite-fixes](https://github.com/srsholmes/onexplayer-apex-bazzite-fixes). The HHD-era modules (button fix, back paddles, home button, oxpec loader, sleep kargs, fan control) were removed rather than made conditional — every module that would have needed a platform switch is one SteamOS does not need.

Fixes that are not SteamOS-specific are contributed back upstream on their own branches rather than carried here. The first is the hardcoded xHCI PCI address (`0000:65:00.4`): that address depends on the Apex's **firmware version**, not the distribution — SteamOS's own InputPlumber profile documents both `65:00.4` (original firmware) and `c5:00.4` (updated firmware) — so Bazzite users on recent firmware hit the same silent failure.

## Hardware Reference

| Component | Detail |
|---|---|
| **APU** | AMD Ryzen AI Max+ 395 (16C/32T Zen 5, RDNA 3.5 40 CUs) |
| **Display** | 8" 1920x1200, 120 Hz VRR |
| **Internal USB hub** | `1a86:8091` (QinHeng) |
| **Internal gamepad** | `045e:028e` (Xbox 360 pad, `xpad`) |
| **OXP buttons / RGB** | `1a2c:b001` (`hid-oxp`) |
| **Vendor HID / keyboard** | `1a86:fe00` (`hid-oxp`) |
| **Audio card** | `alsa_card.pci-0000_c5_00.6` |

## Acknowledgments

Upstream plugin and the original fix work by [srsholmes](https://github.com/srsholmes), built on fix packages shared by **스트로바쿠다스 (drama8448)** from the Korean OneXPlayer community on DCInside UMPC Gallery. The `oxpec` driver is by Joaquín Ignacio Aramendía and Antheas Kapenekakis, now in-tree.

## License

MIT
