from backend.memory.memory_store import MemoryStore
from backend.memory.memory_retriever import MemoryRetrievalRequest, MemoryRetriever
from backend.memory.working_memory import WorkingMemory


class MemoryManager:
    def __init__(
        self,
        store: MemoryStore,
        retriever: MemoryRetriever,
        working_memory: WorkingMemory,
    ):
        self.store = store
        self.retriever = retriever
        self.working_memory = working_memory

    def load_working_memory(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ):
        memories = self.retriever.retrieve(
            MemoryRetrievalRequest(query=query, project_id=project_id, limit=limit)
        )

        self.working_memory.load(memories)

        return self.working_memory.get_all()

    def forget(
        self,
        memory_type: str,
        memory_id: str,
    ) -> bool:
        result = self.store.forget(
            memory_type,
            memory_id,
        )

        if not result:
            return False

        self.working_memory.remove(memory_id)

        self.store.save()

        return True

    def restore(
        self,
        memory_type: str,
        memory_id: str,
        project_id: str,
        limit: int = 10,
    ) -> bool:
        result = self.store.restore(
            memory_type,
            memory_id,
        )

        if not result:
            return False

        self.store.save()

        collection = self.store._find_collection(memory_type)
        restored = next(
            (
                item
                for item in self.store.data.get(collection or "", [])
                if item.get("id") == memory_id
            ),
            None,
        )
        query = "" if restored is None else self.retriever.searchable_text(memory_type, restored)
        memories = self.retriever.retrieve(
            MemoryRetrievalRequest(query=query, project_id=project_id, limit=limit)
        )

        for memory in memories:
            if memory["data"].get("id") == memory_id:
                self.working_memory.add(memory)
                return True

        return True

    def get_working_memory(self):
        return self.working_memory.get_all()
