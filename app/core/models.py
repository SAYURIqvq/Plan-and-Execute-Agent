import re
from dataclasses import dataclass


@dataclass
class Step:
    number: int
    text: str
    status: str = "pending"   # pending | done | failed
    note: str = ""            # 結果の要約 or エラーメッセージ


def parse_steps(plan: str) -> list[Step]:
    steps = []
    for line in plan.splitlines():
        line = line.strip()
        m = re.match(r"^(\d+)\.", line)
        if m:
            steps.append(Step(number=int(m.group(1)), text=line))
    return steps


def format_checklist(steps: list[Step]) -> str:
    icons = {"pending": "⏳", "done": "✅", "failed": "❌"}
    lines = []
    for s in steps:
        icon = icons[s.status]
        note = f"  → {s.note}" if s.note else ""
        lines.append(f"{icon} {s.text}{note}")
    return "\n".join(lines)
