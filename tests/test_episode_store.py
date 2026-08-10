from backend.memory.episode_store import EpisodeStore


def test_get_episode(memory_path: str):
    episode = EpisodeStore(memory_path).get_episode("episode_001")

    assert episode is not None
    assert episode.title == "Спроектировали Memory v0.3"


def test_get_episodes_by_project(memory_path: str):
    episodes = EpisodeStore(memory_path).get_episodes_by_project(
        "project_masha_home"
    )

    assert [item.id for item in episodes] == ["episode_001"]
