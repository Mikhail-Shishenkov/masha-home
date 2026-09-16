from array import array
from io import BytesIO
import wave
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from PySide6.QtWidgets import QApplication

from backend.ui.desktop_host import ReminderCuePlayer
from backend.ui.reminder_audio import home_chime_wav
from backend.ui.conversation_bridge import LocalConversationBridge


def test_home_chime_is_short_bounded_pcm():
    with wave.open(BytesIO(home_chime_wav()), "rb") as sound:
        assert (sound.getnchannels(), sound.getsampwidth(), sound.getframerate()) == (1, 2, 22050)
        assert sound.getnframes() / sound.getframerate() == 1.8
        samples = array("h", sound.readframes(sound.getnframes()))
    assert samples[0] == 0
    assert 1000 < max(abs(value) for value in samples) < 32767


def test_reminder_plays_three_pulses_without_duplicate_or_overlap():
    app = QApplication.instance() or QApplication([])
    calls = []
    player = ReminderCuePlayer(cue=lambda: calls.append(True))
    assert player.play_once("one")
    assert len(calls) == 1
    assert not player.play_once("one")
    player._pulse()
    player._pulse()
    player._pulse()
    assert len(calls) == 3 and not player._repeat.isActive()
    assert player.play_once("two")
    player.stop("one")  # An older acknowledgement cannot cancel a new cue.
    player._pulse()
    assert len(calls) == 5
    player.stop("two")
    player._pulse()
    assert len(calls) == 5
    assert not player.play_once("two")
    player.play_once("three")
    player.stop()  # Emergency Stop / window close.
    player._pulse()
    assert len(calls) == 6 and not player._repeat.isActive()


def test_audio_failure_does_not_break_delivery_or_retry_forever():
    app = QApplication.instance() or QApplication([])
    def unavailable():
        raise RuntimeError("no audio device")
    player = ReminderCuePlayer(cue=unavailable)
    assert player.play_once("one")
    player._pulse()
    player._pulse()
    assert not player._repeat.isActive()
    assert not player.play_once("one")


@pytest.mark.parametrize("method", ["resolveProactiveInteraction", "resolveHomeAttentionProactive"])
def test_only_successful_application_resolution_stops_repeats(method):
    item = SimpleNamespace(kind="proactive_interaction", interaction_id="one", allowed_actions=("acknowledge", "dismiss"))
    application = Mock()
    application.proactive_interactions.return_value.items = [item]
    application.home_attention.return_value.attention_items = [item]
    bridge = SimpleNamespace(
        _application=application, _turn_in_flight=False, _conversation_id="home",
        _session_snapshot=Mock(), _emit=Mock(), reminderQuiet=Mock(),
    )
    resolve = getattr(LocalConversationBridge, method)
    resolve(bridge, "one", "invalid")
    bridge.reminderQuiet.emit.assert_not_called()
    application.resolve_proactive.side_effect = ValueError("not available")
    resolve(bridge, "one", "acknowledge")
    bridge.reminderQuiet.emit.assert_not_called()
    application.resolve_proactive.side_effect = None
    resolve(bridge, "one", "acknowledge")
    bridge.reminderQuiet.emit.assert_called_once_with("one")
