SPECIAL EVENING D3 — VISUAL ASSET PACK

Состав:
- apply_special_evening_d3_visual_assets.py
- d3_assets/special-close.png
- d3_assets/special-near.png
- d3_assets/special-quiet-near.png

Канон:
wide                -> существующий special-cozy-wide.png
close               -> special-close.png
near                -> special-near.png
near + idle + quiet -> special-quiet-near.png

SHA-256:
{
  "special-close.png": {
    "sha256": "c92850a96285e4a1795f16f0e269e25a93faff80e807e1a64dab573a2b675574",
    "bytes": 1947241
  },
  "special-near.png": {
    "sha256": "f75f40857d6d0edd13245cde46da0767b805adce8ca3bcb900d79d1d21ed7e11",
    "bytes": 2049022
  },
  "special-quiet-near.png": {
    "sha256": "4feaf21f3d9cd58f8dcc749e4a6e1c74d1e0c0ca9a7bab66f7aad7f7a94c4fc6",
    "bytes": 2023257
  }
}

Установка:
1. Распаковать содержимое архива прямо в C:\masha-home\
2. Запустить:
   .\.venv\Scripts\python.exe .\apply_special_evening_d3_visual_assets.py
3. Проверить:
   node frontend\renderer\special-evening-proximity.test.cjs
   node frontend\renderer\special-evening-visual-assets.test.cjs
   .\.venv\Scripts\python.exe -m pytest tests/test_presentation_runtime.py -q
4. Посмотреть:
   git diff --text
   git status --short

Скрипт не перезаписывает уже существующие authored D3 assets.
