# pyslobs

An object-based Python wrapper for the Streamlabs OBS (SLOBS) API

---

## How it works

This module was designed to provide easy accessibility to the Streamlabs OBS API through an object structure. Pretty much everything is asynchronous and built with flexibility in mind.

This is still very much a work in progress, and although it is technically functional, only a portion of the API is covered and there are still a few problems here and there. Use with caution.

This unfortunately only works on Windows because it utilizes calls to the Windows API through `pywin32`. I might try to expand it to macOS later (Streamlabs OBS isn't available for Linux as of now), but it's not really a priority.

---

## How to use it

First, make sure you're using at least Python 3.8. It will not work on earlier versions.

Next, make sure to install all of the requirements through the provided `requirements.txt` using `pip install -r requirements.txt` or something of the sort. Or you can just install `pywin32` on its own, since that's the only thing in there.

Open up Streamlabs OBS and make sure you have two scenes in the current collection, one named "Desktop" and the other "Game". You should then be able to open up `test.py` and then `fake_luamacros.py` (in that order) without everything falling apart.

To see the results, just type in `1` or `2` to switch between the two scenes, and type `m` to mute the microphone.

To stop the programs, you kinda just have to either close the consoles/terminals or press `Ctrl + C` to force stop them. If a bunch of errors pop up don't worry, they should be harmless and I will probably try to cut down on them later somehow.

You can maybe dig around and pull something together on your own, although I plan to make documentation that covers everything later once it's more finalized.

---

## Stuff I still have to do

* 100% coverage of the API
* Include support for event subscriptions through decorators
* Handle all exceptions and errors properly
* Possibly look into Windows' OVERLAPPED thing to maybe make pipe I/O even more asynchronous?
* Make proper documentation
