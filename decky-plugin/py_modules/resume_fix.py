"""Resume recovery fix for OneXPlayer Apex.

Installs a oneshot systemd unit ordered after the sleep targets, so systemd
itself runs the recovery script once per resume. The script rebinds the xHCI
USB controller when the internal chain did not come back on its own.

Originally based on the xpad-fix3 package from the Korean OXP community, which
kept a dbus-monitor daemon running to catch the resume signal.

The xHCI controller's PCI address depends on the Apex firmware version, so the
generated script discovers it on every resume rather than having it baked in at
install time — that way the service survives a firmware update.
"""

import logging
import os
import subprocess

logger = logging.getLogger("OXP-ResumeFix")

# Shared with xhci_recovery so the two modules cannot disagree on which
# controller is the internal one. Optional: this module still works without it.
try:
    from xhci_recovery import find_internal_xhci
except Exception:  # pragma: no cover
    find_internal_xhci = None

_log_info_cb = None
_log_error_cb = None
_log_warning_cb = None


def set_log_callbacks(info_fn, error_fn, warning_fn):
    global _log_info_cb, _log_error_cb, _log_warning_cb
    _log_info_cb = info_fn
    _log_error_cb = error_fn
    _log_warning_cb = warning_fn


def _log_info(msg):
    if _log_info_cb:
        _log_info_cb(msg)
    else:
        logger.info(msg)


def _log_error(msg):
    if _log_error_cb:
        _log_error_cb(msg)
    else:
        logger.error(msg)


def _log_warning(msg):
    if _log_warning_cb:
        _log_warning_cb(msg)
    else:
        logger.warning(msg)


def _clean_env():
    env = os.environ.copy()
    for var in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        env.pop(var, None)
    return env


_SCRIPT_PATH = "/usr/local/sbin/apex-resume-recover.sh"
_SERVICE_NAME = "apex-resume-recover.service"
_SERVICE_PATH = f"/etc/systemd/system/{_SERVICE_NAME}"

# Not an f-string: every brace below is literal shell.
_SCRIPT_CONTENT = r"""#!/bin/bash
# OneXPlayer Apex — Gamepad recovery after sleep
# Run once per resume by apex-resume-recover.service, which systemd orders
# after the sleep targets. Rebinds the xHCI controller when the internal USB
# chain did not come back.
# Based on xpad-fix3 from the Korean OXP community.
#
# The controller's PCI address depends on the Apex firmware version, not on the
# model, so it is resolved on every resume rather than hardcoded. That also
# means the service keeps working across a firmware update.

# The internal hub the gamepad, buttons and keyboard all hang off
HUB_VID=1a86
HUB_PID=8091
# The bus that hub lives on, used only once the hub itself is gone
HUB_BUS=usb1
# The gamepad itself, the device a user actually notices going missing
GAMEPAD_VID=045e
GAMEPAD_PID=028e

log() { logger -t apex-resume-recover "$1"; }

find_usb() {
    local d
    for d in /sys/bus/usb/devices/*/; do
        [ "$(cat "$d/idVendor" 2>/dev/null)" = "$1" ] || continue
        [ "$(cat "$d/idProduct" 2>/dev/null)" = "$2" ] || continue
        printf '%s' "$d"
        return 0
    done
    return 1
}

chain_healthy() {
    find_usb "$HUB_VID" "$HUB_PID" >/dev/null || return 1
    find_usb "$GAMEPAD_VID" "$GAMEPAD_PID" >/dev/null || return 1
    return 0
}

# How long to give the chain to come back after a bind
SETTLE_TIMEOUT=10

# Sets SETTLED_AFTER to the number of quarter seconds spent waiting, so the
# caller can report it either way.
SETTLED_AFTER=0

wait_for_chain() {
    # bash cannot compare floats, so count in quarter seconds
    local quarters=0 limit=$((SETTLE_TIMEOUT * 4))
    while ! chain_healthy; do
        if [ "$quarters" -ge "$limit" ]; then
            SETTLED_AFTER=$quarters
            return 1
        fi
        sleep 0.25
        quarters=$((quarters + 1))
    done
    SETTLED_AFTER=$quarters
    return 0
}

find_xhci() {
    local d hub

    # 1. The hub is present: walk its sysfs path up to the controller
    if hub=$(find_usb "$HUB_VID" "$HUB_PID"); then
        readlink -f "$hub" | grep -oE '0000:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9]' | tail -1
        return
    fi

    # 2. The hub is gone: fall back to the controller owning its bus, which
    #    stays bound when only the hub drops
    for d in /sys/bus/pci/drivers/xhci_hcd/0000:*/; do
        if [ -d "$d$HUB_BUS" ]; then
            basename "$d"
            return
        fi
    done
}

recover_gamepad() {
    local xhci_pci xhci_driver

    # Most resumes are fine. Rebinding one that worked tears down a healthy
    # controller for no reason, so look before touching anything.
    if chain_healthy; then
        log "Internal USB chain is healthy — nothing to do"
        return
    fi
    log "Internal chain is down — recovering gamepad"

    xhci_pci=$(find_xhci)
    if [ -z "$xhci_pci" ]; then
        log "No xHCI controller found — cannot recover"
        return
    fi
    log "Using xHCI controller $xhci_pci"
    xhci_driver="/sys/bus/pci/devices/$xhci_pci/driver"

    if [ -e "$xhci_driver" ]; then
        log "Unbinding $xhci_pci"
        echo "$xhci_pci" > "$xhci_driver/unbind" 2>/dev/null
        log "Unbind returned"
        sleep 1
    fi
    log "Binding $xhci_pci"
    echo "$xhci_pci" > /sys/bus/pci/drivers/xhci_hcd/bind 2>/dev/null
    log "Bind returned"

    # The devices come back one by one over two to three seconds, and how long
    # exactly varies between resumes, so wait for them rather than guessing.
    if wait_for_chain; then
        log "Internal chain is back after $((SETTLED_AFTER * 250))ms"
    else
        log "Chain did not come back within ${SETTLE_TIMEOUT}s"
    fi
}

recover_gamepad
"""

# systemd reaches suspend.target on the way *out* of sleep, so a oneshot unit
# ordered after it runs once per resume with no daemon in between.
_SLEEP_TARGETS = "suspend.target hibernate.target suspend-then-hibernate.target"

_SERVICE_CONTENT = f"""[Unit]
Description=OneXPlayer Apex gamepad resume recovery
After={_SLEEP_TARGETS}

[Service]
Type=oneshot
ExecStart={_SCRIPT_PATH}

[Install]
WantedBy={_SLEEP_TARGETS}
"""


def _find_pci_device():
    """Locate the internal xHCI controller, for status reporting only.

    The generated script does its own discovery at resume time; this is just so
    the UI can show which controller was found.
    """
    if not find_internal_xhci:
        return None
    try:
        pci_device, _how = find_internal_xhci()
        return pci_device
    except Exception:
        return None


def is_applied():
    """Check current status of the resume recovery fix."""
    service_exists = os.path.exists(_SERVICE_PATH)
    script_exists = os.path.exists(_SCRIPT_PATH)
    pci_device = _find_pci_device()

    # No is-active check: the unit is Type=oneshot, so it reads as "inactive"
    # at all times except the second or two it spends recovering.
    service_enabled = False
    if service_exists:
        try:
            r = subprocess.run(
                ["systemctl", "is-enabled", _SERVICE_NAME],
                capture_output=True, text=True, timeout=10, env=_clean_env()
            )
            service_enabled = r.stdout.strip() == "enabled"
        except Exception:
            pass

    applied = service_enabled and script_exists

    return {
        "applied": applied,
        "service_enabled": service_enabled,
        "script_exists": script_exists,
        "pci_device_exists": pci_device is not None,
        "pci_device": pci_device,
    }


def apply():
    """Install and start the resume recovery service."""
    steps = []
    _log_info("=== Resume Fix Apply Start ===")

    status = is_applied()
    if status.get("applied"):
        return {"success": True, "message": "Already applied", "steps": ["Already applied"]}

    pci_device = _find_pci_device()
    if pci_device:
        _log_info(f"Internal xHCI controller found at {pci_device}")
        steps.append(f"xHCI controller: {pci_device}")
    else:
        _log_warning("No internal xHCI controller found — service may not work")
        steps.append("Warning: no internal xHCI controller found")

    # Write recovery script
    try:
        os.makedirs(os.path.dirname(_SCRIPT_PATH), exist_ok=True)
        with open(_SCRIPT_PATH, "w") as f:
            f.write(_SCRIPT_CONTENT)
        os.chmod(_SCRIPT_PATH, 0o755)
        steps.append("Created recovery script")
        _log_info(f"Created {_SCRIPT_PATH}")
    except Exception as e:
        return {"success": False, "error": f"Failed to write script: {e}", "steps": steps}

    # Write systemd service
    try:
        with open(_SERVICE_PATH, "w") as f:
            f.write(_SERVICE_CONTENT)
        steps.append("Created systemd service")
        _log_info(f"Created {_SERVICE_PATH}")
    except Exception as e:
        return {"success": False, "error": f"Failed to write service: {e}", "steps": steps}

    # Enable and start
    try:
        subprocess.run(
            ["systemctl", "daemon-reload"],
            capture_output=True, text=True, timeout=30, env=_clean_env()
        )
        # enable, never `--now`: the unit is oneshot, so starting it here would
        # rebind a perfectly healthy controller the moment the toggle is flipped.
        r = subprocess.run(
            ["systemctl", "enable", _SERVICE_NAME],
            capture_output=True, text=True, timeout=30, env=_clean_env()
        )
        if r.returncode == 0:
            steps.append("Hooked the service onto the sleep targets")
            _log_info("Resume fix service enabled")
        else:
            _log_error(f"systemctl enable failed: {r.stderr.strip()}")
            return {"success": False, "error": f"Failed to enable service: {r.stderr.strip()}", "steps": steps}
    except Exception as e:
        return {"success": False, "error": f"systemctl failed: {e}", "steps": steps}

    _log_info("Resume fix applied successfully")
    return {"success": True, "message": "Resume recovery service installed", "steps": steps}


def revert():
    """Stop and remove the resume recovery service."""
    steps = []
    _log_info("=== Resume Fix Revert Start ===")

    # Disable and stop service
    if os.path.exists(_SERVICE_PATH):
        try:
            subprocess.run(
                ["systemctl", "disable", _SERVICE_NAME],
                capture_output=True, text=True, timeout=30, env=_clean_env()
            )
            steps.append("Disabled resume recovery service")
        except Exception as e:
            _log_warning(f"Failed to disable service: {e}")

    # Remove service file
    if os.path.exists(_SERVICE_PATH):
        try:
            os.remove(_SERVICE_PATH)
            steps.append("Removed service file")
        except Exception as e:
            _log_warning(f"Failed to remove service file: {e}")

    # Remove script
    if os.path.exists(_SCRIPT_PATH):
        try:
            os.remove(_SCRIPT_PATH)
            steps.append("Removed recovery script")
        except Exception as e:
            _log_warning(f"Failed to remove script: {e}")

    # Reload systemd
    try:
        subprocess.run(
            ["systemctl", "daemon-reload"],
            capture_output=True, text=True, timeout=30, env=_clean_env()
        )
    except Exception:
        pass

    _log_info("Resume fix reverted")
    return {"success": True, "message": "Resume recovery service removed", "steps": steps}
