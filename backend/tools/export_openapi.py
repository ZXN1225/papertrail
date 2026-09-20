import json
from pathlib import Path

from app.common.config import Settings
from app.main import create_app

app = create_app(Settings(_env_file=None, app_env="test", database_url="", redis_url=""))
path = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
path.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Exported docs/openapi.json")
