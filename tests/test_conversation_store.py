from backend.conversation.conversation_models import ConversationRole
from backend.conversation.conversation_store import ConversationStore
import pytest


def test_history_persists_and_reloads(tmp_path):
    path = tmp_path / "conversations.json"
    store = ConversationStore(path)
    conversation = store.create()
    store.append(conversation.id, ConversationRole.USER, "Привет")
    store.append(conversation.id, ConversationRole.ASSISTANT, "Привет, Миша")

    restored = ConversationStore(path)

    assert restored.get(conversation.id) == conversation
    assert [message.content for message in restored.messages(conversation.id)] == ["Привет", "Привет, Миша"]


def test_latest_returns_most_recent_conversation(tmp_path):
    store = ConversationStore(tmp_path / "conversations.json")
    first = store.create()
    second = store.create()

    assert store.latest() == second
    assert first != second


def test_spaces_delete_and_reload_preserve_unrelated_history(tmp_path):
    path = tmp_path / "history.json"
    store = ConversationStore(path)
    ordinary = store.create()
    evening = store.create(space="special_evening")
    store.append(ordinary.id, ConversationRole.USER, "Ordinary")
    store.append(evening.id, ConversationRole.USER, "PRIVATE EVENING")
    assert store.latest_message(space="ordinary").conversation_id == ordinary.id
    restored = ConversationStore(path)
    assert restored.get(evening.id).space == "special_evening"
    restored.delete(evening.id)
    assert "PRIVATE EVENING" not in path.read_text(encoding="utf-8")
    assert ConversationStore(path).recent() == (ordinary,)
    with pytest.raises(KeyError):
        restored.get(evening.id)


def test_failed_delete_write_preserves_in_memory_history(tmp_path, monkeypatch):
    store = ConversationStore(tmp_path / "history.json")
    item = store.create()
    def fail():
        raise OSError("disk failure")
    monkeypatch.setattr(store, "_save", fail)
    with pytest.raises(OSError):
        store.delete(item.id)
    assert store.get(item.id) == item
