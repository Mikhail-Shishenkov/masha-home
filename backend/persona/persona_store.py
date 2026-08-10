import json
from pathlib import Path

from .persona_models import Persona, VisualIdentity


class PersonaStore:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.data = self._load()

    def _load(self):
        with open(
            self.file_path,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    def get_persona(self, persona_id: str):
        if self.data["id"] != persona_id:
            return None

        visual_data = self.data.get("visual_identity")

        visual_identity = None

        if visual_data is not None:
            visual_identity = VisualIdentity(
                name=visual_data["name"],
                description=visual_data["description"],
                reference_image=visual_data.get(
                    "reference_image"
                ),
                generation_notes=visual_data.get(
                    "generation_notes",
                    [],
                ),
            )

        return Persona(
            id=self.data["id"],
            name=self.data["name"],
            description=self.data["description"],
            personality=self.data["personality"],
            communication_style=self.data[
                "communication_style"
            ],
            visual_identity=visual_identity,
        )