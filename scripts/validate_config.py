from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG = ROOT / "app" / "config"


def load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def check_schedule_uses_integrated_competitions() -> bool:
    competitions: list[dict] = load_json(CONFIG / "competitions.json")  # type: ignore[assignment]
    integrated: set[str] = {c["code"] for c in competitions if c.get("status") == "integrated"}

    schedule: dict = load_json(CONFIG / "editorial_schedule.json")  # type: ignore[assignment]
    weekly_plan: dict[str, list[dict]] = schedule.get("weekly_plan", {})

    unknown: set[str] = set()
    for day, tasks in weekly_plan.items():
        for task in tasks:
            slug = task.get("competition_slug", "")
            if slug and slug not in integrated:
                unknown.add(f"{slug} (day: {day})")

    if unknown:
        for entry in sorted(unknown):
            print(f"[ERROR] editorial_schedule.json references non-integrated competition: {entry}")
        return False

    print("[OK] editorial_schedule.json references only integrated competitions")
    return True


def check_standings_zones_covers_integrated_competitions() -> bool:
    competitions: list[dict] = load_json(CONFIG / "competitions.json")  # type: ignore[assignment]
    integrated: set[str] = {c["code"] for c in competitions if c.get("status") == "integrated"}

    zones: dict = load_json(CONFIG / "standings_zones.json")  # type: ignore[assignment]
    covered: set[str] = set(zones.keys())

    missing: set[str] = integrated - covered
    if missing:
        for code in sorted(missing):
            print(f"[ERROR] standings_zones.json missing integrated competition: {code}")
        return False

    print("[OK] standings_zones.json covers all integrated competitions")
    return True


def main() -> None:
    results = [
        check_schedule_uses_integrated_competitions(),
        check_standings_zones_covers_integrated_competitions(),
    ]
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
