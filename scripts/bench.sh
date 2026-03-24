#!/usr/bin/env bash
set -euo pipefail

# Agent ベンチマークスクリプト
#
# Usage: ./bench.sh [options]
#   --tier    quick|easy|medium|hard|all  (default: medium)
#   --prompt  default|v1|v2|zh           (default: default)
#   --models  m1,m2,...                  (default: qwen2.5:3b,qwen2.5:7b,qwen2.5:14b)
#   --mode    plan_exec|react            (default: plan_exec)
#
# Env vars: TIER / PROMPT_VARIANT / MODE — same as --tier / --prompt / --mode flags
#
# Tiers:
#   quick  — 3 tasks: chat routing, single tool, simple multi-step
#            fast sanity check; good for testing new/unknown models
#   easy   — 2 tasks: datetime+file, memory tools
#   medium — 3 tasks: SQLite+Python, websearch+file, write+run+read
#   hard   — 2 tasks: websearch→SQLite→report, write→run→read→modify→run
#   all    — quick + easy + medium + hard
#
# Available models (pull with: docker exec ollama ollama pull <name>):
#   qwen2.5:3b        — Qwen 3B (fast, same family as 7b/14b)
#   qwen2.5:7b        — Qwen 7B (balanced)
#   qwen2.5:14b       — Qwen 14B (best quality, slow on CPU)
#   llama3.2:3b       — Meta 3B (cross-family comparison)
#   lfm2.5-thinking   — 1.2B ultra-light reasoning model
#   # qwen2.5:32b     — too large for CPU (RAM limit)
#   # gemma3:4b       — no tool calling support
#   # phi4            — no tool calling support
#   # deepseek-r1:14b — no tool calling support
#
# Examples:
#   ./bench.sh
#   ./bench.sh --tier quick --models qwen2.5:3b,llama3.2:3b
#   ./bench.sh --tier all --prompt v1
#   PROMPT_VARIANT=v2 ./bench.sh --models qwen2.5:14b
#   ./bench.sh --tier medium --models qwen2.5:14b --prompt zh --mode react
#   ./bench.sh --tier medium --models qwen2.5:14b --prompt zh --mode plan_exec

TIER="${TIER:-medium}"
PROMPT_VARIANT="${PROMPT_VARIANT:-default}"
MODE="${MODE:-plan_exec}"
REACT_TERMINATION="${REACT_TERMINATION:-text}"
REACT_WATCHDOG="${REACT_WATCHDOG:-none}"
MODELS=("qwen2.5:3b" "qwen2.5:7b" "qwen2.5:14b")

while [[ $# -gt 0 ]]; do
    case "$1" in
        --tier)               TIER="$2";                              shift 2 ;;
        --prompt)             PROMPT_VARIANT="$2";                    shift 2 ;;
        --mode)               MODE="$2";                              shift 2 ;;
        --models)             IFS=',' read -r -a MODELS <<< "$2";    shift 2 ;;
        --react-termination)  REACT_TERMINATION="$2";                 shift 2 ;;
        --react-watchdog)     REACT_WATCHDOG="$2";                   shift 2 ;;
        *)                    echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ── Task definitions ─────────────────────────────────────────────────────────
# Quick: lightweight sanity check (chat routing + 1–2 tool tasks)
TASKS_QUICK=(
    "こんにちは"
    "現在時刻を教えて"
    "1から5までの2乗を計算するPythonスクリプトを /data/squares.py に書いて実行して"
)

# Easy: 1–2 tools; covers datetime and memory tools
TASKS_EASY=(
    "今の日時をJSTで取得して /data/now.txt に保存して"
    "「買い物メモ: 牛乳・卵・パン」とメモしておいて。その後メモ一覧を確認して"
)

# Medium: 3–4 tools; core agent capability across tool categories
TASKS_MEDIUM=(
    "salesテーブルに商品名・数量・単価のデータを10件INSERTして、Pythonでsqlite3モジュールを使ってDBに接続し、合計売上・最高売上・最低売上・平均売上を計算して整形したレポートを/data/sales_report.txtに保存して"
    "Webで「Python asyncio tutorial」を検索して上位の結果ページを取得し、asyncioの主要な概念を5点に絞って日本語でまとめたノートを/data/asyncio_notes.txtに保存して"
    "/data/primes.py を作成して（1〜100の素数を求めるスクリプト）、実行して出力を確認、その後ファイルを読み込んでコードレビューしてコメントを /data/review.txt に保存して"
)

# Hard: 5+ tools; complex multi-step chains requiring planning and recovery
TASKS_HARD=(
    "Webで「2024年人気プログラミング言語ランキング」を検索して上位5言語をSQLiteのlanguagesテーブルに保存し、Pythonで集計レポートを /data/lang_rank.txt に作成して"
    "/data/counter.py を作成（1から10をカウントアップして出力）し実行して動作確認、ファイルを読み込んでコードを確認したあとカウント範囲を1から20に変更して再実行し、変更前後の比較レポートを /data/counter_report.txt に保存して"
)

case "$TIER" in
    quick)  TASKS=("${TASKS_QUICK[@]}") ;;
    easy)   TASKS=("${TASKS_EASY[@]}") ;;
    medium) TASKS=("${TASKS_MEDIUM[@]}") ;;
    hard)   TASKS=("${TASKS_HARD[@]}") ;;
    all)    TASKS=("${TASKS_QUICK[@]}" "${TASKS_EASY[@]}" "${TASKS_MEDIUM[@]}" "${TASKS_HARD[@]}") ;;
    *)      echo "Unknown tier: $TIER  (quick|easy|medium|hard|all)" >&2; exit 1 ;;
esac

# ── Setup ────────────────────────────────────────────────────────────────────
RUN_DIR="test_results/bench_$(date '+%Y%m%d_%H%M%S')"
mkdir -p "$RUN_DIR"
RESULTS_FILE="$RUN_DIR/results.txt"

echo "# Agent ベンチマーク  $(date '+%Y-%m-%d %H:%M')" | tee "$RESULTS_FILE"
echo "# tier=$TIER  prompt=$PROMPT_VARIANT  mode=$MODE  react-termination=$REACT_TERMINATION  react-watchdog=$REACT_WATCHDOG  models=${MODELS[*]}" | tee -a "$RESULTS_FILE"
echo "" | tee -a "$RESULTS_FILE"

METRICS_LINES_BEFORE=$(docker exec langchain_app sh -c \
    'wc -l < /app/logs/metrics.jsonl 2>/dev/null || echo 0')

# ── Run ──────────────────────────────────────────────────────────────────────
_run_task() {
    local MODEL="$1" TASK="$2" TASK_IDX="$3" LOG_FILE="$4"
    docker exec \
        -e OLLAMA_MODEL="$MODEL" \
        -e PROMPT_VARIANT="$PROMPT_VARIANT" \
        -e AGENT_MODE="$MODE" \
        -e REACT_TERMINATION="$REACT_TERMINATION" \
        -e REACT_WATCHDOG="$REACT_WATCHDOG" \
        -e TASK_TIER="$TIER" \
        -e TASK_ID="$((TASK_IDX+1))" \
        -e LOG_LEVEL=DEBUG \
        langchain_app python main.py "$TASK" 2>"$LOG_FILE" || echo "[ERROR]"
}

for MODEL in "${MODELS[@]}"; do
    echo "" | tee -a "$RESULTS_FILE"
    echo "========================================" | tee -a "$RESULTS_FILE"
    echo " MODEL: $MODEL  [tier=$TIER]" | tee -a "$RESULTS_FILE"
    echo "========================================" | tee -a "$RESULTS_FILE"

    echo "  [warmup] $MODEL ..."
    docker exec ollama ollama run "$MODEL" "hi" > /dev/null 2>&1 || true

    TASK_IDX=0
    for TASK in "${TASKS[@]}"; do
        echo "" | tee -a "$RESULTS_FILE"
        echo "  --- タスク$((TASK_IDX+1)) [${TIER}]: ${TASK:0:40}... ---" \
            | tee -a "$RESULTS_FILE"

        LOG_FILE="$RUN_DIR/${MODEL//[:.]/_}_${TIER}_task${TASK_IDX}.log"

        START=$(date +%s)
        OUTPUT=$(_run_task "$MODEL" "$TASK" "$TASK_IDX" "$LOG_FILE")
        ELAPSED=$(( $(date +%s) - START ))

        # Retry once on non-deterministic pydantic/MCP import errors
        if [ "$OUTPUT" = "[ERROR]" ] && grep -q "KeyError" "$LOG_FILE" 2>/dev/null; then
            echo "  [retry] pydantic import エラー検出、リトライ..."
            START=$(date +%s)
            OUTPUT=$(_run_task "$MODEL" "$TASK" "$TASK_IDX" "$LOG_FILE")
            ELAPSED=$(( $(date +%s) - START ))
        fi

        echo "  結果: $OUTPUT"         | tee -a "$RESULTS_FILE"
        echo "  所要時間: ${ELAPSED}秒" | tee -a "$RESULTS_FILE"

        TASK_IDX=$(( TASK_IDX + 1 ))

        docker exec langchain_app sh -c 'rm -rf /data/* 2>/dev/null || true'
    done
done

# ── Summary ──────────────────────────────────────────────────────────────────
echo "" | tee -a "$RESULTS_FILE"
echo "========================================" | tee -a "$RESULTS_FILE"
echo "テスト完了" | tee -a "$RESULTS_FILE"
echo "========================================" | tee -a "$RESULTS_FILE"

METRICS_SNAPSHOT="$RUN_DIR/metrics_snapshot.jsonl"
docker exec langchain_app sh -c \
    "tail -n +$(( METRICS_LINES_BEFORE + 1 )) /app/logs/metrics.jsonl 2>/dev/null || true" \
    > "$METRICS_SNAPSHOT"

if [ -s "$METRICS_SNAPSHOT" ]; then
    SUMMARY=$(python3 - "$METRICS_SNAPSHOT" <<'PYEOF'
import sys, json, collections

records = []
with open(sys.argv[1], encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except Exception:
                pass

stats = collections.defaultdict(lambda: {
    "tca": [], "err_rate": [], "step_cr": [],
    "replans": [], "turns": [], "elapsed": [], "count": 0
})
for r in records:
    m = r.get("model", "unknown")
    stats[m]["tca"].append(r.get("tca", 0))
    stats[m]["err_rate"].append(r.get("error_rate", 0))
    stats[m]["step_cr"].append(r.get("step_completion_rate"))  # may be None (react mode)
    stats[m]["replans"].append(r.get("replan_count", 0))
    stats[m]["turns"].append(r.get("total_turns", 0))
    stats[m]["elapsed"].append(r.get("elapsed_sec", 0))
    stats[m]["count"] += 1

avg = lambda lst: round(sum(lst) / len(lst), 3) if lst else 0.0
avg_nullable = lambda lst: (lambda v: round(v, 3) if v is not None else None)(
    (lambda vals: sum(vals) / len(vals) if vals else None)([x for x in lst if x is not None])
)

print(f"\n{'Model':<20} {'Runs':>4} {'StepCR':>7} {'TCA':>6} "
      f"{'ErrRate':>8} {'Replans':>8} {'AvgTurns':>9} {'AvgSec':>8}")
print("-" * 80)
for model, d in sorted(stats.items()):
    scr = avg_nullable(d['step_cr'])
    scr_str = f"{scr:.3f}" if scr is not None else "  N/A"
    print(f"{model:<20} {d['count']:>4} {scr_str:>7} {avg(d['tca']):>6.3f} "
          f"{avg(d['err_rate']):>8.3f} {avg(d['replans']):>8.1f} "
          f"{avg(d['turns']):>9.1f} {avg(d['elapsed']):>8.0f}")
print("=" * 80)
PYEOF
)
    echo "$SUMMARY" | tee -a "$RESULTS_FILE"
fi

echo ""
echo "保存先: $RUN_DIR"
