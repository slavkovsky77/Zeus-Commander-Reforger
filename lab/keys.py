"""Key presses for the game window (scan codes through SendInput - the game reads raw keyboard input),
and a picture of the window (Windows Graphics Capture, whatever is in front of it). Used to work the
diagnostic build's Diag Menu, e.g. Cheats > "DTime multiplier" for a faster solo match.

    python lab/keys.py shot out.jpg                 # the game window now
    python lab/keys.py size 2400 1350               # a large window, still windowed
    python lab/keys.py window                       # a normal window (borders), maximised
    python lab/keys.py speed 2                      # solo match at 2x (once, on a fresh game)
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
    if u.IsIconic(hwnd):          # only un-minimise; never change its size or mode
        u.ShowWindow(hwnd, 9)
    u.SetForegroundWindow(hwnd)
    time.sleep(0.4)


def normal_maximised(hwnd) -> None:
    """A normal window - title bar, borders - maximised (the game opens borderless). Martin watches it
    remotely and wants a window, at full resolution."""
    u = ctypes.windll.user32
    u.GetWindowLongW.restype = ctypes.c_long
    st = u.GetWindowLongW(hwnd, -16) & 0xFFFFFFFF
    new = (st & ~0x80000000) | 0x00CF0000          # WS_POPUP off, WS_OVERLAPPEDWINDOW on
    u.SetWindowLongW(hwnd, -16, ctypes.c_long(new - (1 << 32) if new >= 1 << 31 else new))
    u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0001 | 0x0002 | 0x0004)   # frame changed
    u.ShowWindow(hwnd, 3)


def set_speed(hwnd, speed: float) -> None:
    """The diagnostic build's Diag Menu (held Win+Alt), freshly opened: Cheats (12th) > "DTime
    multiplier" (7th) on, then its value (8th) from 1 in steps of 0.01. Only where the game hosts the
    match (solo); measured 2.0x at a steady 60 fps (19 Oct)."""
    front(hwnd)
    # Windows takes Win+arrow as "snap the window": with ~200 presses the game window was thrown
    # between the screen halves (Martin, 19 Oct). Window snapping is off while the menu is worked,
    # and put back as it was (read back, retried) - also if this fails half way.
    u = ctypes.windll.user32
    was = ctypes.c_int()
    u.SystemParametersInfoW(0x0082, 0, ctypes.byref(was), 0)          # SPI_GETWINARRANGING
    u.SystemParametersInfoW(0x0083, 0, None, 0x2)                       # SPI_SETWINARRANGING off
    for k in ("lwin", "lalt"):
        key(k, False)
        time.sleep(0.05)
    time.sleep(0.4)
    try:
        for k in ["down"] * 11 + ["right"] + ["down"] * 6 + ["right", "down"] + ["right"] * round((speed - 1) * 100):
            tap(k)
    finally:
        for k in ("lalt", "lwin"):
            key(k, True)
            time.sleep(0.05)
        for _ in range(3):
            u.SystemParametersInfoW(0x0083, 1 if was.value else 0, ctypes.c_void_p(1) if was.value else None, 0x2)
            now = ctypes.c_int()
            u.SystemParametersInfoW(0x0082, 0, ctypes.byref(now), 0)
            if now.value == was.value:
                break
            time.sleep(0.2)


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
    if cmd == "speed":
        set_speed(hwnd, float(rest[0]))
        return 0
    if cmd == "window":
        normal_maximised(hwnd)
        return 0
    if cmd == "size":
        # A large window, still windowed (Martin watches it remotely): W H, centred on the screen.
        u = ctypes.windll.user32
        w, h = int(rest[0]), int(rest[1])
        sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
        u.ShowWindow(hwnd, 9)
        u.SetWindowPos(hwnd, 0, max(0, (sw - w) // 2), max(0, (sh - h) // 2 - 20), w, h, 0x0004)
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
