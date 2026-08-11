# Навыки Masha Home

Каждый добавляемый навык располагается в отдельной папке:

```text
skills/<skill_id>/
  skill.json
  SKILL.md
  ...future implementation files
```

`skill.json` описывает запрашиваемые возможности, риск, области данных,
максимальный уровень автономности и способ проверки результата. Это декларация,
а не разрешение. `SKILL.md` объясняет процедуру навыка человеку и будущему
исполнителю.

Stage 16.1 умеет только обнаруживать, валидировать и регистрировать пакет с
SHA-256 всего содержимого. Registry не импортирует entrypoint и не выполняет
код. Изменение файлов после регистрации переводит пакет в состояние `modified`.

Пример manifest:

```json
{
  "schema_version": "1.0",
  "skill_id": "project_observer",
  "name": "Project Observer",
  "version": "1.0.0",
  "description": "Читает состояние разрешённого локального проекта без изменений.",
  "entrypoint": null,
  "instructions_file": "SKILL.md",
  "capabilities": ["local_read"],
  "requested_scopes": ["workspace:masha-home"],
  "risk_level": "observe",
  "maximum_autonomy_level": 1,
  "supports_dry_run": true,
  "supports_rollback": false,
  "verification": "Возвращает список прочитанных источников и не меняет их hashes."
}
```

Команды:

```powershell
.\masha.ps1 skills list
.\masha.ps1 skills show project_observer
.\masha.ps1 skills verify project_observer
.\masha.ps1 skills register project_observer
```

Выдача разрешений, исполнение entrypoint, agent loop и установка внешних пакетов
в Stage 16.1 отсутствуют.

Stage 16.2 добавляет отдельную policy постоянных разрешений, но всё ещё ничего
не исполняет:

```powershell
.\masha.ps1 skills policy status
.\masha.ps1 skills policy on
.\masha.ps1 skills policy level 2
.\masha.ps1 skills permissions
.\masha.ps1 skills grant project_observer local_read workspace:masha-home 2 observe
.\masha.ps1 skills check project_observer local_read workspace:masha-home 1
.\masha.ps1 skills revoke 1
```

Grant действует только для точного сочетания skill + capability + scope и не
может расширить manifest. `check` показывает решение policy, но не запускает
действие.
