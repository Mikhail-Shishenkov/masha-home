from backend.memory.episode_store import EpisodeStore


store = EpisodeStore("tests/fixtures/test_memory.json")

episode = store.get_episode("episode_001")

print("EPISODE:")
print(episode)

print("\nEPISODES BY PROJECT:")

episodes = store.get_episodes_by_project("project_masha_home")

for item in episodes:
    print("-", item.title)
    print(" ", item.summary)