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
Installs a service that listens for resume events and rebinds the xHCI controller after sleep.

> Whether this is needed on SteamOS is **not yet established** — the sleep/wake test has not been run. Treat it as opt-in.

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
