import json
from pathlib import Path

from app.main import app


target = Path(__file__).with_name("openapi.json")
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
print(f"OpenAPI gerado em {target}")

