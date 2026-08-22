"""OneXPlayer Apex Tools — Decky Loader plugin backend.

Exposes methods for gamepad recovery, resume recovery, the volume buttons and
speaker DSP to the frontend via Decky's RPC bridge.

Each async method in the Plugin class becomes an RPC endpoint that
the React frontend can call via @decky/api's `callable()`.
"""

import asyncio
import os
import subprocess
import sys

# Official Decky module — injected by the loader at runtime.
# Provides DECKY_PLUGIN_DIR, DECKY_PLUGIN_LOG_DIR, and logger.
import decky

# Add py_modules to path so we can import our helper modules
sys.path.insert(0, os.path.join(decky.DECKY_PLUGIN_DIR, "py_modules"))

# Import helper modules with error handling so a single broken module
# doesn't crash the entire plugin on load.

try:
    import speaker_dsp as _speaker_dsp_mod
    from speaker_dsp import (
        enable as enable_speaker_dsp_impl,
        disable as disable_speaker_dsp_impl,
        set_profile as set_dsp_profile_impl,
        get_status as speaker_dsp_status,
        list_profiles as list_dsp_profiles_impl,
        get_preset_bands as get_preset_bands_impl,
        get_custom_profiles as get_custom_profiles_impl,
        save_custom_profile as save_custom_profile_impl,
        delete_custom_profile as delete_custom_profile_impl,
        play_test_sound as play_test_sound_impl,
        stop_test_sound as stop_test_sound_impl,
        bypass as bypass_speaker_dsp_impl,
        unbypass as unbypass_speaker_dsp_impl,
        is_bypassed as is_bypassed_speaker_dsp_impl,
    )
except Exception as e:
    decky.logger.error(f"Failed to import speaker_dsp: {e}")
    _speaker_dsp_mod = None
    enable_speaker_dsp_impl = None
    disable_speaker_dsp_impl = None
    set_dsp_profile_impl = None
    speaker_dsp_status = None
    list_dsp_profiles_impl = None
    get_preset_bands_impl = None
    get_custom_profiles_impl = None
    save_custom_profile_impl = None
    delete_custom_profile_impl = None
    play_test_sound_impl = None
    stop_test_sound_impl = None
    bypass_speaker_dsp_impl = None
    unbypass_speaker_dsp_impl = None
    is_bypassed_speaker_dsp_impl = None

try:
    import resume_fix as _resume_fix_mod
    from resume_fix import (
        apply as apply_resume_fix_impl,
        revert as revert_resume_fix_impl,
        is_applied as resume_fix_status,
    )
except Exception as e:
    decky.logger.error(f"Failed to import resume_fix: {e}")
    _resume_fix_mod = None
    apply_resume_fix_impl = None
    revert_resume_fix_impl = None
    resume_fix_status = None

try:
    import volume_buttons as _volume_buttons_mod
    from volume_buttons import (
        apply as apply_volume_buttons_impl,
        revert as revert_volume_buttons_impl,
        is_applied as volume_buttons_status,
        refresh_if_stale as refresh_volume_buttons_impl,
    )
except Exception as e:
    decky.logger.error(f"Failed to import volume_buttons: {e}")
    _volume_buttons_mod = None
    apply_volume_buttons_impl = None
    revert_volume_buttons_impl = None
    volume_buttons_status = None
    refresh_volume_buttons_impl = None

try:
    import xhci_recovery as _xhci_recovery_mod
    from xhci_recovery import check_and_recover as xhci_check_and_recover
except Exception as e:
    decky.logger.error(f"Failed to import xhci_recovery: {e}")
    _xhci_recovery_mod = None
    xhci_check_and_recover = None


def _get_user_home():
    """Get the real (non-root) user's home directory.

    Decky runs as root, so os.path.expanduser("~") returns /root.
    We find the actual user by checking SUDO_USER, the plugin dir path,
    or falling back to the first user in /home.
    """
    # Check SUDO_USER first
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and sudo_user != "root":
        home = f"/home/{sudo_user}"
        if os.path.isdir(home):
            return home

    # Infer from Decky plugin dir path (e.g. /home/deck/homebrew/plugins/...)
    plugin_dir = decky.DECKY_PLUGIN_DIR
    if plugin_dir.startswith("/home/"):
        parts = plugin_dir.split("/")
        if len(parts) >= 3:
            home = f"/home/{parts[2]}"
            if os.path.isdir(home):
                return home

    # Fallback: first non-root user in /home
    try:
        for name in sorted(os.listdir("/home")):
            path = f"/home/{name}"
            if os.path.isdir(path) and name != "root":
                return path
    except OSError:
        pass

    return os.path.expanduser("~")


# This plugin targets SteamOS on the OneXPlayer Apex only. On Bazzite, use the
# upstream plugin instead — it ships the HHD-era fixes this fork removed.
_EXPECTED_OS_ID = "steamos"
_EXPECTED_PRODUCT = "ONEXPLAYER APEX"


def _read_first_line(path):
    try:
        with open(path) as f:
            return f.readline().strip()
    except OSError:
        return ""


def _read_os_id():
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("ID="):
                    return line[3:].strip().strip('"')
    except OSError:
        pass
    return ""


def check_platform():
    """Check that we are on SteamOS on an Apex.

    Returns a dict with `supported`, plus the values read so the frontend can
    show what was actually detected.
    """
    os_id = _read_os_id()
    product = _read_first_line("/sys/devices/virtual/dmi/id/product_name")

    if os_id != _EXPECTED_OS_ID:
        reason = f"This plugin targets SteamOS; detected '{os_id or 'unknown'}'"
    elif product != _EXPECTED_PRODUCT:
        reason = f"This plugin targets the {_EXPECTED_PRODUCT}; detected '{product or 'unknown'}'"
    else:
        reason = None

    return {"supported": reason is None, "reason": reason, "os_id": os_id, "product": product}


# Log file path — write to Decky's plugin log directory
LOG_FILE = os.path.join(decky.DECKY_PLUGIN_LOG_DIR, "oxp-apex.log")


def _log_to_file(msg: str):
    """Append a message to our log file (in addition to decky.logger)."""
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            from datetime import datetime
            f.write(f"{datetime.now().isoformat()} [OXP-Apex] {msg}\n")
    except Exception:
        pass


def _log_info(msg: str):
    decky.logger.info(msg)
    _log_to_file(msg)


def _log_error(msg: str):
    decky.logger.error(msg)
    _log_to_file(f"ERROR: {msg}")


def _log_warning(msg: str):
    decky.logger.warning(msg)
    _log_to_file(f"WARN: {msg}")


# Wire log callbacks into helper modules so their logs appear in oxp-apex.log
if _speaker_dsp_mod:
    _speaker_dsp_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _resume_fix_mod:
    _resume_fix_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _volume_buttons_mod:
    _volume_buttons_mod.set_log_callbacks(_log_info, _log_error, _log_warning)
if _xhci_recovery_mod:
    _xhci_recovery_mod.set_log_callbacks(_log_info, _log_error, _log_warning)


_INPUTPLUMBER_UNIT = "inputplumber.service"


def _clean_env():
    """Strip Decky's LD_LIBRARY_PATH/LD_PRELOAD for subprocess calls."""
    env = os.environ.copy()
    for var in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        env.pop(var, None)
    return env


def _restart_inputplumber():
    """Restart InputPlumber so it re-attaches to the recovered source devices.

    InputPlumber does pick devices back up on its own, but only for the sources
    it is still watching; after the whole controller is rebound a restart is the
    reliable way to get a clean composite device.
    """
    try:
        r = subprocess.run(
            ["systemctl", "is-active", _INPUTPLUMBER_UNIT],
            capture_output=True, text=True, timeout=10, env=_clean_env()
        )
        if r.stdout.strip() != "active":
            _log_info(f"{_INPUTPLUMBER_UNIT} is not active — nothing to restart")
            return
        r = subprocess.run(
            ["systemctl", "restart", _INPUTPLUMBER_UNIT],
            capture_output=True, text=True, timeout=30, env=_clean_env()
        )
        if r.returncode == 0:
            _log_info(f"Restarted {_INPUTPLUMBER_UNIT}")
        else:
            _log_error(f"Failed to restart {_INPUTPLUMBER_UNIT}: {r.stderr.strip()}")
    except Exception as e:
        _log_error(f"InputPlumber restart failed: {e}")


class Plugin:
    async def _main(self):
        """Plugin entry point — called by Decky on load."""
        try:
            from build_info import BUILD_ID
        except ImportError:
            BUILD_ID = "unknown"
        _log_info(f"OneXPlayer Apex SteamOS Tools starting ({BUILD_ID})")
        _log_info(f"Plugin dir: {decky.DECKY_PLUGIN_DIR}")
        _log_info(f"Log dir: {decky.DECKY_PLUGIN_LOG_DIR}")

        platform = check_platform()
        if not platform["supported"]:
            _log_error(f"Unsupported platform — {platform['reason']}. Skipping all automatic actions.")
            return
        _log_info(f"Platform OK: {platform['os_id']} on {platform['product']}")

        # Rebuild the InputPlumber override if SteamOS has shipped a new Apex
        # config since it was installed, so our copy cannot mask theirs.
        if refresh_volume_buttons_impl:
            try:
                refreshed = await asyncio.to_thread(refresh_volume_buttons_impl)
                if refreshed.get("refreshed"):
                    _log_info("Rebuilt the volume button override against the new InputPlumber config")
            except Exception as e:
                _log_error(f"Volume button override refresh failed: {e}")

        # Recover the xHCI controller if the internal gamepad USB devices are
        # missing (the internal hub sometimes drops during boot on the Apex)
        if xhci_check_and_recover:
            try:
                result = await asyncio.to_thread(xhci_check_and_recover)
                if result.get("needed") and result.get("success"):
                    _log_info("xHCI recovered — restarting InputPlumber")
                    await asyncio.to_thread(_restart_inputplumber)
                elif result.get("needed") and not result.get("success"):
                    _log_error("xHCI recovery failed — gamepad may not work")
            except Exception as e:
                _log_error(f"xHCI recovery check failed: {e}")

    async def _unload(self):
        """Plugin teardown — called by Decky on unload."""
        _log_info("OneXPlayer Apex SteamOS Tools unloading")
        # Stop test sound if playing
        if stop_test_sound_impl:
            try:
                stop_test_sound_impl()
            except Exception:
                pass

    # -- Status overview --

    async def get_status(self):
        """Get combined status of all features — called by the frontend on load."""
        return {
            "platform": check_platform(),
            "speaker_dsp": speaker_dsp_status() if speaker_dsp_status else {"enabled": False, "profile": None, "speaker_node": None},
            "resume_fix": resume_fix_status() if resume_fix_status else {"applied": False, "error": "module not loaded"},
            "volume_buttons": volume_buttons_status() if volume_buttons_status else {"applied": False, "error": "module not loaded"},
        }

    # -- Logs --

    async def get_logs(self, lines=20):
        """Return the last N lines from the log file."""
        try:
            with open(LOG_FILE) as f:
                all_lines = f.readlines()
            tail = [l.rstrip("\n") for l in all_lines[-lines:]]
            return {"lines": tail, "log_file": LOG_FILE}
        except Exception as e:
            return {"lines": [], "log_file": LOG_FILE, "error": str(e)}

    async def save_logs(self):
        """Copy the log file to the user's ~/Downloads/ with a timestamp."""
        import shutil
        from datetime import datetime
        try:
            user_home = _get_user_home()
            downloads = os.path.join(user_home, "Downloads")
            os.makedirs(downloads, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = os.path.join(downloads, f"oxp-apex-logs_{ts}.log")
            shutil.copy2(LOG_FILE, dest)
            _log_info(f"Logs saved to {dest}")
            return {"success": True, "path": dest}
        except Exception as e:
            _log_error(f"Failed to save logs: {e}")
            return {"success": False, "error": str(e)}

    # -- Speaker DSP --

    async def get_speaker_dsp_status(self):
        if not speaker_dsp_status:
            return {"enabled": False, "profile": None, "speaker_node": None}
        return speaker_dsp_status()

    async def enable_speaker_dsp(self, profile="balanced"):
        if not enable_speaker_dsp_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        _log_info(f"Enabling speaker DSP ({profile})...")
        try:
            result = await asyncio.to_thread(enable_speaker_dsp_impl, profile)
            if result.get("success"):
                _log_info(f"Speaker DSP enabled: {result.get('message', 'OK')}")
            else:
                _log_error(f"Speaker DSP enable failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Speaker DSP enable exception: {e}")
            return {"success": False, "error": str(e)}

    async def disable_speaker_dsp(self):
        if not disable_speaker_dsp_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        _log_info("Disabling speaker DSP...")
        try:
            result = await asyncio.to_thread(disable_speaker_dsp_impl)
            if result.get("success"):
                _log_info(f"Speaker DSP disabled: {result.get('message', 'OK')}")
            else:
                _log_error(f"Speaker DSP disable failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Speaker DSP disable exception: {e}")
            return {"success": False, "error": str(e)}

    async def set_dsp_profile(self, profile):
        if not set_dsp_profile_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        _log_info(f"Setting DSP profile to {profile}...")
        try:
            result = await asyncio.to_thread(set_dsp_profile_impl, profile)
            if result.get("success"):
                _log_info(f"DSP profile set: {result.get('message', 'OK')}")
            else:
                _log_error(f"DSP profile set failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"DSP profile exception: {e}")
            return {"success": False, "error": str(e)}

    async def list_dsp_profiles(self):
        if not list_dsp_profiles_impl:
            return []
        return list_dsp_profiles_impl()

    async def get_preset_bands(self, profile_name):
        if not get_preset_bands_impl:
            return {"error": "speaker_dsp module not loaded"}
        return get_preset_bands_impl(profile_name)

    async def get_custom_profiles(self):
        if not get_custom_profiles_impl:
            return {"profiles": {}}
        return get_custom_profiles_impl()

    async def save_custom_profile(self, name, gains):
        if not save_custom_profile_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(save_custom_profile_impl, name, gains)
        except Exception as e:
            _log_error(f"Save custom profile exception: {e}")
            return {"success": False, "error": str(e)}

    async def delete_custom_profile(self, name):
        if not delete_custom_profile_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(delete_custom_profile_impl, name)
        except Exception as e:
            _log_error(f"Delete custom profile exception: {e}")
            return {"success": False, "error": str(e)}

    async def play_test_sound(self):
        if not play_test_sound_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(play_test_sound_impl)
        except Exception as e:
            _log_error(f"Play test sound exception: {e}")
            return {"success": False, "error": str(e)}

    async def stop_test_sound(self):
        if not stop_test_sound_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(stop_test_sound_impl)
        except Exception as e:
            _log_error(f"Stop test sound exception: {e}")
            return {"success": False, "error": str(e)}

    async def bypass_speaker_dsp(self):
        if not bypass_speaker_dsp_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(bypass_speaker_dsp_impl)
        except Exception as e:
            _log_error(f"Bypass speaker DSP exception: {e}")
            return {"success": False, "error": str(e)}

    async def unbypass_speaker_dsp(self):
        if not unbypass_speaker_dsp_impl:
            return {"success": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(unbypass_speaker_dsp_impl)
        except Exception as e:
            _log_error(f"Unbypass speaker DSP exception: {e}")
            return {"success": False, "error": str(e)}

    async def is_bypassed_speaker_dsp(self):
        if not is_bypassed_speaker_dsp_impl:
            return {"bypassed": False, "error": "speaker_dsp module not loaded"}
        try:
            return await asyncio.to_thread(is_bypassed_speaker_dsp_impl)
        except Exception as e:
            _log_error(f"Is bypassed speaker DSP exception: {e}")
            return {"bypassed": False, "error": str(e)}

    # -- Resume Recovery --

    async def get_resume_fix_status(self):
        if not resume_fix_status:
            return {"applied": False, "error": "module not loaded"}
        return resume_fix_status()

    async def apply_resume_fix(self):
        if not apply_resume_fix_impl:
            return {"success": False, "error": "resume_fix module not loaded"}
        _log_info("Installing resume recovery fix...")
        try:
            result = await asyncio.to_thread(apply_resume_fix_impl)
            if result.get("success"):
                _log_info(f"Resume fix applied: {result.get('message', 'OK')}")
            else:
                _log_error(f"Resume fix failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Resume fix exception: {e}")
            return {"success": False, "error": str(e)}

    async def revert_resume_fix(self):
        if not revert_resume_fix_impl:
            return {"success": False, "error": "resume_fix module not loaded"}
        _log_info("Removing resume recovery fix...")
        try:
            result = await asyncio.to_thread(revert_resume_fix_impl)
            if result.get("success"):
                _log_info(f"Resume fix reverted: {result.get('message', 'OK')}")
            else:
                _log_error(f"Resume fix revert failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Resume fix revert exception: {e}")
            return {"success": False, "error": str(e)}

    # -- Volume Buttons --

    async def get_volume_buttons_status(self):
        if not volume_buttons_status:
            return {"applied": False, "error": "module not loaded"}
        return volume_buttons_status()

    async def apply_volume_buttons(self):
        if not apply_volume_buttons_impl:
            return {"success": False, "error": "volume_buttons module not loaded"}
        _log_info("Enabling the volume buttons...")
        try:
            result = await asyncio.to_thread(apply_volume_buttons_impl)
            if result.get("success"):
                _log_info(f"Volume buttons applied: {result.get('message', 'OK')}")
            else:
                _log_error(f"Volume buttons failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Volume buttons exception: {e}")
            return {"success": False, "error": str(e)}

    async def revert_volume_buttons(self):
        if not revert_volume_buttons_impl:
            return {"success": False, "error": "volume_buttons module not loaded"}
        _log_info("Reverting the volume buttons fix...")
        try:
            result = await asyncio.to_thread(revert_volume_buttons_impl)
            if result.get("success"):
                _log_info(f"Volume buttons reverted: {result.get('message', 'OK')}")
            else:
                _log_error(f"Volume buttons revert failed: {result.get('error', 'unknown')}")
            return result
        except Exception as e:
            _log_error(f"Volume buttons revert exception: {e}")
            return {"success": False, "error": str(e)}

    # -- xHCI Recovery (manual trigger) --

    async def recover_gamepad(self):
        """Manually trigger an xHCI rebind to recover the internal gamepad."""
        if not xhci_check_and_recover:
            return {"success": False, "error": "xhci_recovery module not loaded"}
        _log_info("Manual gamepad recovery triggered")
        try:
            result = await asyncio.to_thread(xhci_check_and_recover)
            if result.get("already_ok"):
                return {"success": True, "message": "Gamepad already connected"}
            if result.get("success"):
                await asyncio.to_thread(_restart_inputplumber)
                pci = result.get("pci_device", "controller")
                return {"success": True, "message": f"Gamepad recovered (rebound {pci})"}
            missing = ", ".join(result.get("missing") or []) or "the internal hub"
            return {"success": False, "error": f"Recovery failed — still missing: {missing}"}
        except Exception as e:
            _log_error(f"Gamepad recovery exception: {e}")
            return {"success": False, "error": str(e)}
