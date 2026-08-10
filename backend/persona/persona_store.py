import json
from pathlib import Path

from .persona_models import Persona


class PersonaStore:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.data = self._load()

    def _load(self):
        with open(self.file_path, "r", encoding="utf-8") as file:
            return json.load(file)

    def get_persona(self, persona_id: str):
        if self.data["id"] != persona_id:
            return None

        return Persona(
            id=self.data["id"],
            name=self.data["name"],
            description=self.data["description"],
            personality=self.data["personality"],
            communication_style=self.data["communication_style"]
        )