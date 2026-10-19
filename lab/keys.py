"""Key presses for the game window (scan codes through SendInput - the game reads raw keyboard input),
and a picture of the window (Windows Graphics Capture, whatever is in front of it). Used to work the
diagnostic build's Diag Menu, e.g. Cheats > "DTime multiplier" for a faster solo match.

    python lab/keys.py shot out.jpg                 # the game window now
    python lab/keys.py press down down right        # keys, one after another
    python lab/keys.py hold lwin+lalt down right    # keys while holding others (the Diag Menu)
    python lab/keys.py holdshot lwin+lalt down out.jpg   # the same, and a picture before letting go
"""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
import watch_loop  # noqa: E402

# name: (scan code, extended)
SCAN = {
    "lwin": (0x5B, True), "lalt": (0x38, False), "lctrl": (0x1D, False), "lshift": (0x2A, False),
    "up": (0x48, True), "down": (0x50, True), "left": (0x4B, True), "right": (0x4D, True),
    "enter": (0x1C, False), "esc": (0x01, False), "space": (0x39, False), "pgup": (0x49, True), "pgdn": (0x51, True),
    "home": (0x47, True), "end": (0x4F, True),
}
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x1
KEYEVENTF_KEYUP = 0x2
KEYEVENTF_SCANCODE = 0x8


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def key(name: str, up: bool) -> None:
    code, ext = SCAN[name]
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if ext else 0) | (KEYEVENTF_KEYUP if up else 0)
    i = INPUT(type=INPUT_KEYBOARD)
    i.ki = KEYBDINPUT(0, code, flags, 0, 0)
    ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def tap(name: str) -> None:
    key(name, False)
    time.sleep(0.06)
    key(name, True)
    time.sleep(0.15)


def game_hwnd():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process -Filter \"Name='ArmaReforgerSteamDiag.exe'\" | Select-Object -ExpandProperty ProcessId"],
                         capture_output=True, text=True).stdout.split()
    return watch_loop.game_window(int(out[0])) if out else None


def front(hwnd) -> None:
    u = ctypes.windll.user32
    u.ShowWindow(hwnd, 9)
    u.SetForegroundWindow(hwnd)
    time.sleep(0.4)


def shot(hwnd, out: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-filter_complex",
                    f"gfxcapture=hwnd={int(hwnd)}:max_framerate=10:capture_cursor=0,hwdownload,format=bgra,scale=1280:-2",
                    "-frames:v", "1", out], timeout=30)


def main() -> int:
    hwnd = game_hwnd()
    if not hwnd:
        print("no game window")
        return 1
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "shot":
        shot(hwnd, rest[0])
        return 0
    front(hwnd)
    if cmd == "press":
        for k in rest:
            tap(k)
    elif cmd in ("hold", "holdshot"):
        # holdshot: also a picture before letting go (the Diag Menu shows only while held).
        held = rest[0].split("+")
        keys = rest[1:-1] if cmd == "holdshot" else rest[1:]
        for k in held:
            key(k, False)
            time.sleep(0.05)
        time.sleep(0.3)
        for k in keys:
            tap(k)
        if cmd == "holdshot":
            time.sleep(0.3)
            shot(hwnd, rest[-1])
        for k in reversed(held):
            key(k, True)
            time.sleep(0.05)
    return 0


if __name__ == "__main__":
    sys.exit(main())
