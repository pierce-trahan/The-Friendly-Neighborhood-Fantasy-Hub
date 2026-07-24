from __future__ import annotations

import json
from pathlib import Path

from friendly_hub.main import create_app


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    output_path = project_root / "contracts" / "openapi.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {output_path.relative_to(project_root)}")


if __name__ == "__main__":
    main()
