"""
Automated agent evaluation script.

Usage (run inside the langchain_app container):
    python app/tests/eval_agent.py

Exit codes:
    0 — all assertions passed
    1 — one or more assertions failed
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

# Add app/ to sys.path so we can import project modules directly.
sys.path.insert(0, str(Path(__file__).parent.parent))

from executor import run  # noqa: E402  (import after path fix)

METRICS_FILE = Path("/app/logs/metrics.jsonl")
DATA_DIR = Path("/data")

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "id": "write_and_run_python",
        "prompt": (
            "1から5までの2乗を計算するPythonスクリプトを /data/eval_test.py に書いて実行して"
        ),
        # Expected stdout lines that must appear in the execution result
        "expected_output_lines": ["1", "4", "9", "16", "25"],
        # File that must exist after the task
        "expected_file": DATA_DIR / "eval_test.py",
    },
    {
        "id": "get_current_time",
        "prompt": "現在時刻を教えて",
        # The final answer must contain a year (loose check)
        "expected_output_lines": ["202"],
        "expected_file": None,
    },
]


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

def assert_file_exists(path: Path) -> None:
    assert path.exists(), f"FAIL [{path}] が存在しません"
    print(f"  PASS: {path} が存在する")


def assert_file_runs_correctly(path: Path, expected_lines: list[str]) -> None:
    """Run the generated Python file and check its stdout."""
    result = subprocess.run(
        ["python3", str(path)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    stdout = result.stdout.strip()
    for line in expected_lines:
        assert line in stdout, (
            f"FAIL: '{line}' が {path} の出力に含まれていません。\n実際の出力:\n{stdout}"
        )
    print(f"  PASS: {path} の実行結果が期待通り ({expected_lines})")


def assert_answer_contains(answer: str | None, expected_lines: list[str]) -> None:
    answer = answer or ""
    for fragment in expected_lines:
        assert fragment in answer, (
            f"FAIL: '{fragment}' が最終回答に含まれていません。\n実際の回答:\n{answer}"
        )
    print(f"  PASS: 最終回答に期待フラグメント {expected_lines} が含まれる")


# ---------------------------------------------------------------------------
# Metrics summary helper
# ---------------------------------------------------------------------------

def read_latest_metrics(session_count: int) -> list[dict]:
    """Read the last `session_count` records from metrics.jsonl."""
    if not METRICS_FILE.exists():
        return []
    lines = METRICS_FILE.read_text(encoding="utf-8").strip().splitlines()
    records = []
    for line in lines[-session_count:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records


def print_metrics_summary(records: list[dict]) -> None:
    if not records:
        print("\n[metrics] metrics.jsonl にレコードがありません")
        return

    print("\n" + "=" * 60)
    print(" メトリクス集計")
    print("=" * 60)
    header = f"{'session_id':<22} {'model':<16} {'TCA':>6} {'ArgFit':>8} {'StepCR':>8}"
    print(header)
    print("-" * 62)
    for r in records:
        print(
            f"{r.get('session_id',''):<22} "
            f"{r.get('model',''):<16} "
            f"{r.get('tca', 0):>6.3f} "
            f"{r.get('arg_fit_rate', 0):>8.3f} "
            f"{r.get('step_completion_rate', 0):>8.3f}"
        )
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

async def run_evaluations() -> int:
    """Run all test cases. Returns number of failures."""
    failures = 0
    sessions_before = 0
    if METRICS_FILE.exists():
        sessions_before = len(METRICS_FILE.read_text().splitlines())

    for tc in TEST_CASES:
        print(f"\n{'='*60}")
        print(f"[eval] {tc['id']}: {tc['prompt'][:60]}")
        print("=" * 60)

        try:
            answer = await run(tc["prompt"])

            # 1. Check final answer text
            assert_answer_contains(answer, tc["expected_output_lines"])

            # 2. Check generated file exists and runs correctly
            if tc.get("expected_file"):
                path: Path = tc["expected_file"]
                assert_file_exists(path)
                assert_file_runs_correctly(path, tc["expected_output_lines"])

            print(f"[eval] {tc['id']}: PASSED")

        except AssertionError as e:
            print(f"[eval] {tc['id']}: {e}")
            failures += 1
        except Exception as e:
            print(f"[eval] {tc['id']}: EXCEPTION — {e}")
            failures += 1

    # Print metrics for sessions created during this run
    if METRICS_FILE.exists():
        sessions_after = len(METRICS_FILE.read_text().splitlines())
        new_records = read_latest_metrics(sessions_after - sessions_before)
        print_metrics_summary(new_records)

    return failures


if __name__ == "__main__":
    total_failures = asyncio.run(run_evaluations())

    print(f"\n{'='*60}")
    if total_failures == 0:
        print("全テスト PASSED")
    else:
        print(f"{total_failures} 件のテストが FAILED")
    print("=" * 60)

    sys.exit(0 if total_failures == 0 else 1)
