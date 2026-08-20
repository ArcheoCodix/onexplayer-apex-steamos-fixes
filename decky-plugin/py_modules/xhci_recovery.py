"""xHCI boot recovery for OneXPlayer Apex.

The internal gamepad (1A86:FE00 + 045E:028E) hangs off an internal USB hub
(1A86:8091) behind one xHCI controller. That chain sometimes dies during boot:

    xhci_hcd: xHCI host not responding to stop endpoint command
    xhci_hcd: HC died; cleaning up

or with the hub simply dropping and taking its children with it:

    usb 1-1: USB disconnect, device number 2
    usb 1-1.3: USB disconnect, device number 5

Either way the gamepad disappears and HHD can't create a virtual controller.
This module detects the broken chain and rebinds the controller on startup.

The controller's PCI address is NOT fixed: it depends on the Apex firmware
version, not on the model. The InputPlumber profile shipped by SteamOS
documents both, which is the clearest published evidence of it:

    # Original Firmware -> usb-0000:65:00.4-1.3/input0
    # Updated Firmware  -> usb-0000:c5:00.4-1.3/input0

So it is discovered at runtime instead of hardcoded.
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

_PCI_RE = re.compile(r"(0000:[0-9a-f]{2}:[0-9a-f]{2}\.[0-9])")

# The internal hub the gamepad and vendor HID hang off
_INTERNAL_HUB_ID = "1a86:8091"

# Fallback: the bus the internal hub lives on. Used only to locate the
# controller once the hub itself is gone and cannot point at its parent.
_INTERNAL_BUS = "usb1"

# USB devices that should be present when xHCI is healthy
_VENDOR_HID_ID = "1a86:fe00"
_XBOX_GAMEPAD_ID = "045e:028e"


_USB_DEVICES = "/sys/bus/usb/devices"


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def find_usb_device(vid_pid):
    """Return the sysfs path of an enumerated USB device, or None.

    Reads sysfs directly rather than shelling out to lsusb: no dependency on
    usbutils, and it works before any userspace tooling is up.
    """
    vid, pid = vid_pid.split(":")
    for path in sorted(glob.glob(f"{_USB_DEVICES}/*")):
        if _read(f"{path}/idVendor") == vid and _read(f"{path}/idProduct") == pid:
            return path
    return None


def _usb_device_present(vid_pid):
    """Check if a USB device with the given VID:PID is enumerated."""
    return find_usb_device(vid_pid) is not None


def find_internal_xhci():
    """Find the PCI address of the xHCI controller carrying the internal hub.

    Returns (pci_address, how) — `how` naming the method that found it, so the
    log says which one applied. Returns (None, reason) on failure.
    """
    # 1. The hub is present: walk its sysfs path up to the PCI device.
    hub = find_usb_device(_INTERNAL_HUB_ID)
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


def _rebind_xhci(pci_device):
    """Unbind and rebind the xHCI controller to recover USB devices."""
    _log_info(f"Rebinding xHCI controller {pci_device}...")

    # Unbind if currently bound (may be in a dead state)
    if os.path.exists(f"/sys/bus/pci/devices/{pci_device}/driver"):
        try:
            with open(_UNBIND_PATH, "w") as f:
                f.write(pci_device)
            _log_info("Unbound xHCI controller")
        except OSError as e:
            _log_warning(f"Unbind failed (may already be unbound): {e}")

    time.sleep(1)

    # Bind
    try:
        with open(_BIND_PATH, "w") as f:
            f.write(pci_device)
        _log_info("Bound xHCI controller")
    except OSError as e:
        _log_error(f"Bind failed: {e}")
        return False

    # Wait for USB enumeration
    time.sleep(2)
    return True


def check_and_recover():
    """Check if the internal gamepad is present; rebind xHCI if not.

    Returns a dict with recovery status:
      - needed: whether recovery was attempted
      - success: whether the gamepad was found after recovery
      - already_ok: True if no recovery was needed
    """
    # Check if gamepad USB devices are already present
    if _usb_device_present(_VENDOR_HID_ID) and _usb_device_present(_XBOX_GAMEPAD_ID):
        _log_info("Internal gamepad USB devices present — no recovery needed")
        return {"needed": False, "success": True, "already_ok": True}

    _log_warning("Internal gamepad USB devices missing — attempting xHCI recovery")

    pci_device, how = find_internal_xhci()
    if not pci_device:
        _log_error(f"Cannot recover — {how}")
        return {"needed": True, "success": False, "already_ok": False}
    _log_info(f"xHCI controller {pci_device} ({how})")

    # Try up to 2 rebind attempts
    for attempt in range(1, 3):
        _log_info(f"xHCI recovery attempt {attempt}/2")
        _rebind_xhci(pci_device)

        if _usb_device_present(_VENDOR_HID_ID) and _usb_device_present(_XBOX_GAMEPAD_ID):
            _log_info(f"xHCI recovery succeeded on attempt {attempt}")
            return {"needed": True, "success": True, "already_ok": False, "pci_device": pci_device}

        if attempt < 2:
            _log_warning("Gamepad not yet detected, retrying...")
            time.sleep(2)

    _log_error("xHCI recovery failed — gamepad not detected after 2 attempts")
    return {"needed": True, "success": False, "already_ok": False, "pci_device": pci_device}
