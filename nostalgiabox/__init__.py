"""NostalgiaBox - a retro TV media player for a Raspberry Pi nostalgia box.

NostalgiaBox turns a Raspberry Pi 4 into an early-2000s style television. It
presents a fixed set of "channels" (each backed by a folder of episodes),
plays them on a continuous randomized shuffle, and drives the whole thing from
a remote control with authentic touches like a channel banner, an on-screen
volume bar, and a burst of static when you change the channel.

The package is split so that the "brains" (channel scanning, shuffle logic,
the application state machine) are pure Python with no hardware dependencies,
while the "hands" (the mpv video player, the remote-control input backends)
are isolated and imported lazily. This makes the interesting logic fully
testable on any machine, not just on the Pi in front of a TV.
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
