"""Keeps Windows from going to sleep while the lab runs unattended (the night of 20 Oct the PC slept
02:42-05:13 and froze every match). The standard request a long-running program makes
(SetThreadExecutionState) - no power setting is changed; it ends when this process ends.

    python lab/keepawake.py --hours 8
"""
import argparse
import ctypes
import time

ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_DISPLAY_REQUIRED = 0x80000000, 0x1, 0x2

ap = argparse.ArgumentParser()
ap.add_argument("--hours", type=float, default=8)
a = ap.parse_args()
end = time.time() + a.hours * 3600
while time.time() < end:
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
    time.sleep(30)
ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
