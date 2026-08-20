"""xHCI recovery for the OneXPlayer Apex internal USB hub.

The internal gamepad, the OXP buttons and the internal keyboard all hang off a
single internal USB hub (1A86:8091) behind one xHCI controller. That hub
sometimes drops a few seconds after boot, taking all three devices with it:

    usb 1-1: USB disconnect, device number 2
    usb 1-1.3: USB disconnect, device number 5

Rebinding the xHCI controller brings the whole chain back.

The controller's PCI address is NOT fixed: it depends on the Apex firmware
version, not on the model. The InputPlumber profile shipped by SteamOS
documents both (50-onexplayer_apex.yaml):

    # Original Firmware -> usb-0000:65:00.4-1.3/input0
    # Updated Firmware  -> usb-0000:c5:00.4-1.3/input0

So it is discovered at runtime instead of hardcoded.

This module deliberately knows nothing about the input daemon: recovering the
USB devices and restarting whatever consumes them are separate concerns.
"""

import glob
import logging
import os
import re
import time

logger = logging.getLogger("OXP-xHCIRecovery")

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


_XHCI_DRIVER = "xhci_hcd"
_DRIVER_DIR = f"/sys/bus/pci/drivers/{_XHCI_DRIVER}"
_UNBIND_PATH = f"{_DRIVER_DIR}/unbind"
_BIND_PATH = f"{_DRIVER_DIR}/bind"

_USB_DEVICES = "/sys/bus/usb/devices"
_PCI_RE = re.compile(r"(0000:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9])")

# The internal hub everything else hangs off. Losing it loses the rest.
INTERNAL_HUB = ("1a86", "8091")

# Devices carried by that hub, checked to tell a partial drop from a full one.
INTERNAL_DEVICES = [
    (("045e", "028e"), "gamepad"),
    (("1a2c", "b001"), "OXP buttons"),
    (("1a86", "fe00"), "vendor HID"),
]

# Fallback: the bus the internal hub lives on. Used only to locate the
# controller once the hub itself is gone and cannot point at its parent.
_INTERNAL_BUS = "usb1"


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def find_usb_device(vid, pid):
    """Return the sysfs path of a USB device by VID/PID, or None.

    Reads sysfs directly rather than shelling out to lsusb: no dependency on
    usbutils, and it works before any userspace tooling is up.
    """
    for path in sorted(glob.glob(f"{_USB_DEVICES}/*")):
        if _read(f"{path}/idVendor") == vid and _read(f"{path}/idProduct") == pid:
            return path
    return None


def find_internal_xhci():
    """Find the PCI address of the xHCI controller carrying the internal hub.

    Returns (pci_address, how) — `how` naming the method that found it, so the
    log says which one applied. Returns (None, reason) on failure.
    """
    # 1. The hub is present: walk its sysfs path up to the PCI device.
    hub = find_usb_device(*INTERNAL_HUB)
    if hub:
        found = _PCI_RE.findall(os.path.realpath(hub))
        if found:
            # The last PCI component is the closest ancestor, i.e. the controller
            return found[-1], "resolved from the internal hub"

    # 2. The hub is gone — the failure case. Fall back to the controller that
    #    owns the bus the hub lives on. The controller normally stays bound
    #    when only the hub drops, so its root hub is still there.
    for driver_link in sorted(glob.glob(f"{_DRIVER_DIR}/0000:*")):
        if os.path.isdir(os.path.join(driver_link, _INTERNAL_BUS)):
            return os.path.basename(driver_link), f"owner of {_INTERNAL_BUS}"

    return None, "no xHCI controller could be identified"


def check_devices():
    """Report which internal USB devices are present."""
    hub_present = find_usb_device(*INTERNAL_HUB) is not None
    missing = [label for vid_pid, label in INTERNAL_DEVICES if not find_usb_device(*vid_pid)]
    return {
        "hub_present": hub_present,
        "missing": missing,
        "healthy": hub_present and not missing,
    }


def _rebind(pci_device):
    """Unbind and rebind the xHCI controller to re-enumerate its USB devices."""
    _log_info(f"Rebinding xHCI controller {pci_device}...")

    if os.path.exists(f"/sys/bus/pci/devices/{pci_device}/driver"):
        try:
            with open(_UNBIND_PATH, "w") as f:
                f.write(pci_device)
            _log_info("Unbound xHCI controller")
        except OSError as e:
            _log_warning(f"Unbind failed (may already be unbound): {e}")

    time.sleep(1)

    try:
        with open(_BIND_PATH, "w") as f:
            f.write(pci_device)
        _log_info("Bound xHCI controller")
    except OSError as e:
        _log_error(f"Bind failed: {e}")
        return False

    # Give the hub and its children time to re-enumerate
    time.sleep(2)
    return True


def check_and_recover():
    """Check the internal USB chain; rebind the xHCI controller if it is broken.

    Returns:
      needed     — whether recovery was attempted
      success    — whether the chain was healthy afterwards
      already_ok — True if nothing had to be done
      pci_device — the controller that was rebound, if any
      missing    — devices still missing at the end
    """
    state = check_devices()
    if state["healthy"]:
        _log_info("Internal USB chain present — no recovery needed")
        return {"needed": False, "success": True, "already_ok": True, "missing": []}

    if state["hub_present"]:
        _log_warning(f"Internal hub is up but devices are missing: {', '.join(state['missing'])}")
    else:
        _log_warning("Internal USB hub is gone — the whole chain is down")

    pci_device, how = find_internal_xhci()
    if not pci_device:
        _log_error(f"Cannot recover — {how}")
        return {"needed": True, "success": False, "already_ok": False, "missing": state["missing"]}
    _log_info(f"xHCI controller {pci_device} ({how})")

    for attempt in (1, 2):
        _log_info(f"xHCI recovery attempt {attempt}/2")
        _rebind(pci_device)

        state = check_devices()
        if state["healthy"]:
            _log_info(f"xHCI recovery succeeded on attempt {attempt}")
            return {
                "needed": True,
                "success": True,
                "already_ok": False,
                "pci_device": pci_device,
                "missing": [],
            }

        if attempt == 1:
            _log_warning(f"Still missing: {', '.join(state['missing']) or 'the hub'} — retrying")
            time.sleep(2)

    _log_error(f"xHCI recovery failed — still missing: {', '.join(state['missing']) or 'the hub'}")
    return {
        "needed": True,
        "success": False,
        "already_ok": False,
        "pci_device": pci_device,
        "missing": state["missing"],
    }
