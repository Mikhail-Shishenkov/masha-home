from backend.conversation.conversation_models import ConversationRole
from backend.conversation.conversation_store import ConversationStore


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
