"""Is this computer running on battery? Best effort, and ``False`` whenever it cannot tell.

Used by the desktop app so that background work (analysis) does not drain a laptop that is
not plugged in. A desktop PC, a server or an unknown platform reports ``False``: not on battery.
"""

import ctypes
import glob
import subprocess
import sys


def on_battery() -> bool:
    try:
        if sys.platform == "win32":
            return _windows()
        if sys.platform == "darwin":
            return _macos()
        return _linux()
    except Exception:  # noqa: BLE001 - not knowing is not a reason to stop working
        return False


def _windows() -> bool:
    class Status(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_ubyte),
            ("BatteryFlag", ctypes.c_ubyte),
            ("BatteryLifePercent", ctypes.c_ubyte),
            ("SystemStatusFlag", ctypes.c_ubyte),
            ("BatteryLifeTime", ctypes.c_ulong),
            ("BatteryFullLifeTime", ctypes.c_ulong),
        ]

    status = Status()
    ok = ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
    return bool(ok) and status.ACLineStatus == 0  # 0 offline, 1 online, 255 unknown


def _macos() -> bool:
    out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
    return "Battery Power" in out


def _linux() -> bool:
    mains = glob.glob("/sys/class/power_supply/A*/online")
    for path in mains:
        with open(path, encoding="ascii") as f:
            return f.read().strip() == "0"
    return False
