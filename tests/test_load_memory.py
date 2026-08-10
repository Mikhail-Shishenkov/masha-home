import json

from backend.memory.memory_models import Project, Fact


with open("memory/test_memory.json", "r", encoding="utf-8") as file:
    data = json.load(file)


project_data = data["project"]
fact_data = data["facts"][0]


project = Project(**{
    "id": project_data["id"],
    "name": project_data["name"],
    "description": project_data["description"],
    "status": project_data["status"],
})


fact = Fact(**fact_data)


print("PROJECT:")
print(project)

print("\nFACT:")
print(fact)