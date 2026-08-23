"""Resume recovery fix for OneXPlayer Apex.

Installs a oneshot systemd unit ordered after the sleep targets, so systemd
itself runs the recovery script once per resume. The script waits for the resume
to stop producing device events, then rebinds the xHCI USB controller if the
internal chain still has not come back. InputPlumber re-attaches the recovered
devices by itself, so it is only restarted if its controller target is missing
once the chain is stable.

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


# /usr/local lives inside the read-only root subvolume on SteamOS: writing there
# needs `steamos-readonly disable`, and the subvolume is replaced wholesale on
# every OS update, so the script would silently vanish. /var is a separate
# filesystem and /etc an overlay whose upper dir sits on it, so both are
# writable as root and both survive an update.
_STATE_DIR = "/var/lib/onexplayer-apex"
_SCRIPT_PATH = f"{_STATE_DIR}/apex-resume-recover.sh"
_LEGACY_SCRIPT_PATH = "/usr/local/sbin/apex-resume-recover.sh"
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
# model, so it is resolved on every resume rather than baked in at install time.

set -u

# The internal hub the gamepad, buttons and keyboard all hang off
HUB_VID=1a86
HUB_PID=8091
# The bus that hub lives on, used only once the hub itself is gone
HUB_BUS=usb1
GAMEPAD_VID=045e
GAMEPAD_PID=028e
# The other two devices behind the hub. Not part of the health test — the
# gamepad is the last to enumerate and the one a user notices — but logged, so
# a device that keeps re-enumerating is visible instead of inferred afterwards.
BUTTONS_VID=1a2c
BUTTONS_PID=b001
VENDORHID_VID=1a86
VENDORHID_PID=fe00

# How long to give the chain to come back after a bind
SETTLE_TIMEOUT=10
# Never touch the controller sooner than this after a resume. A rebind 190ms
# into a resume once hung the machine hard; the same rebind 8s in worked. The
# floor is a margin over the known-bad point, not a measured threshold.
QUIET_FLOOR=3
# Act anyway past this, quiet or not, rather than never recovering
QUIET_CEILING=10
# Consecutive quiet polls required before acting
QUIET_REQUIRED=2
# How many one-second snapshots to take once the chain is back, so a device that
# re-enumerates after the fact is on record instead of inferred later
AFTER_POLLS=4
# Consecutive checks with all four devices present before concluding there is
# nothing to do. One look is not enough: see the comment in recover_gamepad.
INTACT_REQUIRED=2

START=$(date +%s%N)

elapsed_ms() { echo $(( ($(date +%s%N) - START) / 1000000 )); }
log() { logger -t apex-resume-recover "[$(elapsed_ms)ms] $1"; }

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

# "1-1.1/7" or "-". The device number changes on every re-enumeration, so a
# device that disappears and comes back is distinguishable from one that never
# moved — which is exactly what could not be told apart from inside the script.
device_state() {
    local d
    for d in /sys/bus/usb/devices/*/; do
        [ "$(cat "$d/idVendor" 2>/dev/null)" = "$1" ] || continue
        [ "$(cat "$d/idProduct" 2>/dev/null)" = "$2" ] || continue
        printf '%s/%s' "$(basename "$d")" "$(cat "$d/devnum" 2>/dev/null || echo '?')"
        return 0
    done
    printf '%s' '-'
    return 1
}

# What Steam actually consumes.
#   deck-uhid : InputPlumber's virtual Steam Deck Controller, a uhid device
#   steaminput: Steam Input's own virtual pad, present once Steam has bound one
# Both survive the internal chain disappearing, so neither proves events are
# flowing — but they do show whether our own actions destroyed them.
steam_state() {
    local e n found=-
    if grep -lqs 'Generic Steam Controller' /sys/class/hidraw/*/device/uevent; then
        printf 'deck-uhid=yes'
    else
        printf 'deck-uhid=no'
    fi
    for e in /sys/class/input/event*; do
        n=$(cat "$e/device/name" 2>/dev/null) || continue
        case "$(readlink -f "$e")" in
            */virtual/input/*) case "$n" in *X-Box*) found="$n";; esac ;;
        esac
    done
    printf ' steaminput=%s' "$found"
}

snapshot() {
    local s
    s="hub=$(device_state "$HUB_VID" "$HUB_PID")"
    s="$s buttons=$(device_state "$BUTTONS_VID" "$BUTTONS_PID")"
    s="$s hid=$(device_state "$VENDORHID_VID" "$VENDORHID_PID")"
    s="$s pad=$(device_state "$GAMEPAD_VID" "$GAMEPAD_PID")"
    s="$s $(steam_state)"
    log "state[$1] $s"
}

# The pair that matters once a rebind is under way: the hub plus the gamepad,
# which is the last of the four to enumerate and the one a user notices.
chain_healthy() {
    find_usb "$HUB_VID" "$HUB_PID" >/dev/null || return 1
    find_usb "$GAMEPAD_VID" "$GAMEPAD_PID" >/dev/null || return 1
    return 0
}

# The stricter test, used to decide there is nothing wrong at all. Any of the
# four missing means something is off, and a chain caught mid-teardown fails it
# where chain_healthy can still pass.
chain_intact() {
    find_usb "$HUB_VID" "$HUB_PID" >/dev/null || return 1
    find_usb "$BUTTONS_VID" "$BUTTONS_PID" >/dev/null || return 1
    find_usb "$VENDORHID_VID" "$VENDORHID_PID" >/dev/null || return 1
    find_usb "$GAMEPAD_VID" "$GAMEPAD_PID" >/dev/null || return 1
    return 0
}

XHCI=""
XHCI_HOW=""

find_xhci() {
    local d hub
    XHCI=""; XHCI_HOW=""

    # 1. The hub is present: walk its sysfs path up to the controller
    if hub=$(find_usb "$HUB_VID" "$HUB_PID"); then
        XHCI=$(readlink -f "$hub" | grep -oE '0000:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9]' | tail -1)
        if [ -n "$XHCI" ]; then
            XHCI_HOW="resolved from the internal hub"
            return 0
        fi
    fi

    # 2. The hub is gone: fall back to the controller still owning its bus. It
    #    stays bound to the driver even when the host controller itself died.
    for d in /sys/bus/pci/drivers/xhci_hcd/0000:*/; do
        if [ -d "$d$HUB_BUS" ]; then
            XHCI=$(basename "$d")
            XHCI_HOW="owner of $HUB_BUS"
            return 0
        fi
    done

    XHCI_HOW="no xHCI controller could be identified"
    return 1
}

# The kernel's own account of what just happened, so one
# `journalctl -t apex-resume-recover` explains an occurrence without having to
# cross-reference the kernel log by hand.
kernel_verdict() {
    local dm
    dm=$(dmesg 2>/dev/null) || return
    # Two separate greps on purpose: a single pattern with tail -3 kept only the
    # PM error lines and dropped the controller's own verdict, which is the half
    # that says *why*.
    printf '%s\n' "$dm" | grep -E 'xhci_hcd .*(not responding|HC died)' | tail -2 \
        | while IFS= read -r line; do log "kernel: $line"; done
    printf '%s\n' "$dm" | grep -E 'usb 1-1: PM:' | tail -2 \
        | while IFS= read -r line; do log "kernel: $line"; done
}

# The kernel's global uevent counter. A plain sysfs read that cannot go
# missing, which is why the decision rests on it rather than on udevadm: gating
# on a tool that may be absent would silently make every resume wait for the
# ceiling instead of acting when things go quiet.
seqnum() { cat /sys/kernel/uevent_seqnum 2>/dev/null || echo 0; }

# Corroboration only, never a gate: udev can still be running rules after the
# kernel has stopped emitting events, and it is worth seeing whether that lags
# behind the counter.
udev_state() {
    command -v udevadm >/dev/null 2>&1 || { printf 'n/a'; return; }
    if udevadm settle --timeout=0 >/dev/null 2>&1; then printf 'idle'; else printf 'busy'; fi
}

# Wait until the resume has stopped producing device events, rather than
# sleeping a fixed amount and hoping. Returns 0 when it is time to act, 1 when
# the chain came back on its own and there is nothing to do.
wait_until_settled() {
    local secs=0 quiet=0 intact=0 last='' seq udev
    while :; do
        seq=$(seqnum)
        udev=$(udev_state)
        if [ "$seq" = "$last" ]; then
            quiet=$((quiet + 1))
        else
            quiet=0
        fi
        last=$seq
        if chain_intact; then intact=$((intact + 1)); else intact=0; fi

        snapshot "t+${secs}s seq=$seq udev=$udev quiet=$quiet intact=$intact"

        # Both signals, not either: all four devices there *and* the kernel no
        # longer emitting device events. A chain that is still tearing down can
        # show devices present for a moment while events are still flowing.
        if [ "$intact" -ge "$INTACT_REQUIRED" ] && [ "$quiet" -ge 1 ]; then
            log "Chain intact on $intact consecutive checks and quiet — nothing to do"
            return 1
        fi
        if [ "$secs" -ge "$QUIET_FLOOR" ] && [ "$quiet" -ge "$QUIET_REQUIRED" ]; then
            log "Device activity quiet for ${quiet}s — acting after ${secs}s"
            return 0
        fi
        if [ "$secs" -ge "$QUIET_CEILING" ]; then
            log "Still not quiet after ${secs}s — acting anyway"
            return 0
        fi
        sleep 1
        secs=$((secs + 1))
    done
}

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

recover_gamepad() {
    local driver_link drv rs

    # No decision from a single reading, not even the "nothing is wrong" one.
    # A resume where the controller died logged this:
    #
    #   20:19:08.116  HC died; usb 1-1, 1-1.1, 1-1.2 disconnect
    #   20:19:08.167  PM: suspend exit
    #   20:19:08.251  usb 1-1.3 disconnect          <- the gamepad, 135ms later
    #
    # A check 250ms in still found the hub and the gamepad in sysfs while the
    # other two were already gone, called the chain healthy and returned. The
    # gamepad stayed dead until it was recovered by hand. There was no instant
    # at which one look was reliable, so the loop decides instead.
    snapshot start
    kernel_verdict
    log "Watching for the resume to settle"
    # `return 0` explicitly: bare `return` would propagate the 1 that means
    # "nothing to do", and systemd would mark the unit failed on every normal
    # resume.
    wait_until_settled || return 0

    if ! find_xhci; then
        log "$XHCI_HOW — cannot recover"
        return
    fi
    driver_link="/sys/bus/pci/devices/$XHCI/driver"
    drv=absent; [ -e "$driver_link" ] && drv=bound
    rs=$(cat "/sys/bus/pci/devices/$XHCI/power/runtime_status" 2>/dev/null || echo '?')
    log "Using xHCI controller $XHCI ($XHCI_HOW) driver=$drv runtime=$rs"

    if [ "$drv" = bound ]; then
        log "Unbinding $XHCI"
        echo "$XHCI" > "$driver_link/unbind" 2>/dev/null
        log "Unbind returned"
        sleep 1
    fi
    log "Binding $XHCI"
    echo "$XHCI" > /sys/bus/pci/drivers/xhci_hcd/bind 2>/dev/null
    log "Bind returned"

    # The devices come back one by one over two to three seconds, and how long
    # exactly varies between resumes, so wait for them rather than guessing.
    if wait_for_chain; then
        log "Internal chain is back after $((SETTLED_AFTER * 250))ms"
    else
        log "Chain did not come back within ${SETTLE_TIMEOUT}s"
    fi

    # Snapshot for a few seconds rather than once. A single reading taken
    # immediately after the bind says nothing: user space has not had time to
    # react, and a device can still re-enumerate a second later — which is
    # exactly what was missed before.
    #
    # This window is also what InputPlumber needs. It re-attaches recovered
    # source devices to its existing composite device on its own, starting about
    # 70ms after they reappear — and an unconditional restart here killed it
    # mid-way, about 100ms in, in three occurrences out of four:
    #
    #   22:47:34.885  Found missing input device  -> existing composite device
    #   22:47:34.908  Found missing hidraw device -> existing composite device
    #   22:47:34.989  Received SIGTERM
    #
    # So leave it alone and watch. The restart stays only as a fallback for the
    # case the watching is there to catch: InputPlumber's target actually gone.
    local i=0
    while [ "$i" -lt "$AFTER_POLLS" ]; do
        sleep 1
        i=$((i + 1))
        snapshot "after t+${i}s"
    done

    if grep -lqs 'Generic Steam Controller' /sys/class/hidraw/*/device/uevent; then
        log "InputPlumber still has its controller target — not restarting it"
        return
    fi
    log "InputPlumber has no controller target after ${AFTER_POLLS}s — restarting it"
    if systemctl restart inputplumber.service 2>/dev/null; then
        log "Restarted inputplumber.service"
    else
        log "Failed to restart inputplumber.service"
    fi
    sleep 2
    snapshot "after inputplumber restart"
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
ExecStart=/bin/bash {_SCRIPT_PATH}

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
        os.makedirs(_STATE_DIR, mode=0o755, exist_ok=True)
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

    # Older builds wrote the script to /usr/local/sbin, which needed
    # `steamos-readonly disable`. Clean it up if it is still lying around;
    # failing is expected on a read-only root and is not an error.
    if os.path.exists(_LEGACY_SCRIPT_PATH):
        try:
            os.remove(_LEGACY_SCRIPT_PATH)
            steps.append(f"Removed legacy script at {_LEGACY_SCRIPT_PATH}")
        except Exception as e:
            _log_info(f"Left legacy script in place ({e})")

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
