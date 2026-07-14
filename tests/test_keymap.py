from nostalgiabox.actions import Action
from nostalgiabox.input.keymap import (
    cec_key_to_event,
    evdev_key_to_event,
    stdin_char_to_event,
    stdin_escape_to_event,
)


def test_evdev_channel_and_volume():
    assert evdev_key_to_event("KEY_CHANNELUP").action == Action.CHANNEL_UP
    assert evdev_key_to_event("KEY_PAGEUP").action == Action.CHANNEL_UP
    assert evdev_key_to_event("KEY_UP").action == Action.CHANNEL_UP
    assert evdev_key_to_event("KEY_VOLUMEDOWN").action == Action.VOLUME_DOWN
    assert evdev_key_to_event("KEY_MUTE").action == Action.MUTE


def test_evdev_digits():
    ev = evdev_key_to_event("KEY_5")
    assert ev.action == Action.DIGIT and ev.value == 5
    ev = evdev_key_to_event("KEY_KP0")
    assert ev.action == Action.DIGIT and ev.value == 0


def test_evdev_unknown_key():
    assert evdev_key_to_event("KEY_FLIBBERTIGIBBET") is None


def test_stdin_chars():
    assert stdin_char_to_event("+").action == Action.VOLUME_UP
    assert stdin_char_to_event("-").action == Action.VOLUME_DOWN
    assert stdin_char_to_event("m").action == Action.MUTE
    assert stdin_char_to_event("q").action == Action.QUIT
    assert stdin_char_to_event("3").value == 3
    assert stdin_char_to_event("\r").action == Action.ENTER


def test_stdin_arrows():
    assert stdin_escape_to_event("[A").action == Action.CHANNEL_UP
    assert stdin_escape_to_event("[B").action == Action.CHANNEL_DOWN
    assert stdin_escape_to_event("[C").action == Action.VOLUME_UP
    assert stdin_escape_to_event("[D").action == Action.VOLUME_DOWN
    assert stdin_escape_to_event("[Z") is None


def test_cec_keys():
    assert cec_key_to_event("channel up").action == Action.CHANNEL_UP
    assert cec_key_to_event("Volume Down").action == Action.VOLUME_DOWN
    assert cec_key_to_event("select").action == Action.ENTER
    assert cec_key_to_event("number 4").value == 4
    assert cec_key_to_event("power").action == Action.POWER
    assert cec_key_to_event("nonsense") is None
