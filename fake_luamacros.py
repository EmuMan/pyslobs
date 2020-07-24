"""A simple module that allows you to send strings through the
pyslobskbd named pipe created by test.py
"""

import win32file
import pywintypes

try:
    pipe_handle = win32file.CreateFile(
        r'\\.\pipe\pyslobskbd',
        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
        0,
        None,
        win32file.OPEN_EXISTING,
        0,
        None
    )
except pywintypes.error:
    print("Error: the pyslobs script must be running for this to work.")
    exit(1)

while(1):
    win32file.WriteFile(pipe_handle, bytes(input(), "ascii"))
