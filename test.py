"""A basic test module for pyslobs that listens on the pyslobskbd named pipe
for keyboard inputs. I will later link this up to a proper luamacros script,
but for now it can be done through fake_luamacros.py, where you can send key
identifiers through the named pipe. In this example, `1` and `2` correspond
to the scenes titled "Desktop" and "Game", and `m` toggles the muted property
of the microphone input. You might need to change the scene names and microphone
id search to get it to work.
"""

import pyslobs
import asyncio
import win32pipe, win32file, pywintypes

slobs = pyslobs.Slobs()

mic = None
scenes = {"desktop": None, "game": None}

key_pipe = win32pipe.CreateNamedPipe(
    r"\\.\pipe\pyslobskbd",
    win32pipe.PIPE_ACCESS_DUPLEX,
    win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
    1, 65536, 65536,
    0,
    None
)

async def on_key_press(key):
    print("Key pressed:", key)
    if key == "1":
        if scenes["desktop"]:
            print("Switched to Desktop scene" if await scenes["desktop"].set_active() else "Scene switch failed")
    elif key == "2":
        if scenes["game"]:
            print("Switched to Game scene" if await scenes["game"].set_active() else "Scene switch failed")
    elif key == "m":
        if mic:
            await mic.set_muted(not mic.muted)
            print("Mic is now", "muted" if mic.muted else "unmuted")

@slobs.on_ready
async def on_ready():
    # this is probably not very good practice but it works so eh
    global mic
    global scenes

    # from my experience the microphone should have a source id that starts with wasapi_input_capture
    mic = await slobs.get_audio_source(key=(lambda s: s.source_id.startswith("wasapi_input_capture")))

    scenes["desktop"] = await slobs.get_scene(key=(lambda s: s.name == "Desktop"))
    scenes["game"] = await slobs.get_scene(key=(lambda s: s.name == "Game"))

    try:
        print("Waiting for luamacros script...")
        win32pipe.ConnectNamedPipe(key_pipe, None)
        print("Successfully connected to luamacros script through named pipe.")

        while True:
            raw = b""
            while win32pipe.PeekNamedPipe(key_pipe, 0)[1] != 0:
                raw += win32file.ReadFile(key_pipe, 1024)[1]
            for key in raw.split(b"\n"):
                if key != b"":
                    await on_key_press(str(key, "ascii"))
            await asyncio.sleep(0.1)
    except pywintypes.error as e:
        if e.winerror == 109:
            print("Luamacros script closed.")
        else:
            print("Error:", e.funcname, "-", e.strerror)
    finally:
        win32file.CloseHandle(key_pipe)

if __name__ == "__main__":
    slobs.run()