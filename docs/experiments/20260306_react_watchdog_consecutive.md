# 実験: react_watchdog_consecutive

**日時**: 2026-03-06
**ステータス**: 完了

---

## 目的

react_loop には exec_loop の watchdog（連続エラー検出 + アプローチ変更誘導）が存在しない。
Task1 (SQLite+Python) で同じ SyntaxError が Turn2・4・5 と3回繰り返されたように、
react モードでは同一エラーが発生し続けても何も介入しない。

`REACT_WATCHDOG=consecutive` で有効になる factory 実装を追加し、
N 回連続エラー時にフィードバックを注入することで SyntaxError ループを脱出させ、
Judge スコアを改善する。

## 仮説

連続エラー検出（consecutive）watchdog を react_loop に追加することで：
- Task1 の SyntaxError ループが中断され、モデルが別アプローチを試みる
- Judge スコア: 5/15（実験⑮）→ 8/15 以上を期待
- TCA は維持（0.8 以上）、AvgSec は text ベースライン（404s）に近づく

根拠：
- Task1 失敗の直接原因は「同じ SyntaxError → 同じ修正試み → 同じ失敗」の繰り返し
- watchdog フィードバックで「別のアプローチ」を促せば計算ロジックを SQL に切り替える等の回避が期待できる
- exec_loop では同様の仕組みが replan トリガーとして機能している

## 設定変更

| 項目 | 変更前 | 変更後 |
|------|--------|--------|
| `REACT_WATCHDOG` env var | なし（未実装） | `"consecutive"`（有効）|
| `app/agent/base/watchdog.py` | 存在しない | 新規作成（ReactWatchdog ABC + factory） |
| `app/config.py` | REACT_WATCHDOG なし | `REACT_WATCHDOG = os.environ.get(...)` 追加 |
| `app/agent/loops/react_loop.py` | watchdog なし | 連続エラー追跡 + フィードバック注入 |
| `scripts/bench.sh` | `--react-watchdog` フラグなし | 追加 |

### 実装設計

```
app/agent/base/watchdog.py
  ReactWatchdog(ABC)
    .check(consecutive_errors: int, last_result: str) -> str | None

  NoopWatchdog       ← REACT_WATCHDOG=none (デフォルト・既存挙動)
  ConsecutiveErrorWatchdog(threshold=2)
                     ← REACT_WATCHDOG=consecutive (実験A)

  get_react_watchdog(name: str) -> ReactWatchdog  ← factory
```

react_loop の変更点：
- `consecutive_errors` カウンタを追加
- ツール実行後 `is_error=True` なら +1、成功なら 0 リセット
- `watchdog.check()` が文字列を返したら `HumanMessage` としてメッセージに追加

## 実験コマンド

```bash
REACT_WATCHDOG=consecutive \
  ./scripts/bench.sh --tier medium --models qwen2.5:14b --prompt zh --mode react
```

比較ベースライン（watchdog なし、実験⑮相当）:
```bash
./scripts/bench.sh --tier medium --models qwen2.5:14b --prompt zh --mode react
```

---

## 結果

**実行日時**: 2026-03-07 00:43
**結果ディレクトリ**: test_results/bench_20260307_004303

### メトリクス

| モデル | TCA | StepCR | ErrRate | Replans | AvgTurns | AvgSec |
|--------|-----|--------|---------|---------|----------|--------|
| qwen2.5:14b | 0.517 | N/A | 0.111 | 0.0 | 3.3 | 757 |

### タスク別結果

| タスク | 結果 | 所要時間 | Judge |
|--------|------|---------|-------|
| タスク1: SQLite INSERT → sales_report.txt | ❌ (tool call ゼロで即終了) | 353s | 0/5 |
| タスク2: Web 検索 → asyncio_notes.txt | ❌ (write_file 引数エラー後にテキスト回答) | 916s | 1/5 |
| タスク3: primes.py + review.txt | ❌ (review を remember() で保存) | 1008s | 2/5 |

**Judge 合計**: 3/15（平均 1.0/5）

### 動作詳細

**タスク1**:
- Turn1 (328s): テキスト回答で即終了（ツール未呼び出し）
- watchdog: エラーなし → 発火なし

**タスク2**:
- Turn1: web_search ✅ → Turn2: fetch_page ✅
- Turn3: `write_file({'value': '...', 'path': '...'})` → MCP error（arg_fixer が `value`→`content` 未対応）
- consecutive_errors=1、閾値 2 未達 → watchdog 発火なし
- Turn4 (378s): テキスト回答 → asyncio_notes.txt 未作成

**タスク3**:
- Turn1-3: write primes.py ✅ → 実行 ✅ → 読み込み ✅
- Turn4: `remember()` でレビューをメモリ保存（write_file 未呼び出し）
- エラーなし → watchdog 発火なし → Turn5: テキスト回答 → review.txt 未作成

### 副次的発見

- **arg_fixer の未対応マッピング**: `write_file` の `value` キーが `content` に変換されない
  → Task2 の MCP エラーの直接原因

## 考察

### 仮説の検証

仮説は**誤っていた**。

「consecutive watchdog が SyntaxError ループに介入する」を期待したが、
今回の3タスクではいずれも watchdog が **1度も発火しなかった**。
失敗パターンが「連続エラー」ではなく「エラーなしの誤ツール選択」または「1回エラーで即テキスト回答」だったため。

### 主な発見

- watchdog 発火: 0回（3タスク全て閾値未達）
- TCA: 0.517（ベースライン比で低下、非決定性による Task1 回帰が主因）
- Judge: 3/15（ベースライン 7/15 より悪化）— watchdog による悪化ではなく非決定性
- **arg_fixer 未対応**: `write_file` の `value`→`content` マッピングが存在しない（副次発見）
- **実際の失敗パターン**: 「連続エラー」ではなく「エラーなし誤ツール選択」と「早期テキスト終了」

### 副作用

- なし（watchdog は発火しなかったため影響ゼロ）
- ただし arg_fixer ギャップという新たな問題が露見

### 結論

**却下（前提条件ミス）** — 今回の medium タスクの失敗は連続エラー起因ではないため、
consecutive watchdog は効果を発揮できない。
適切な介入対象は「エラーなしで誤ツールを使うパターン」であり、
watchdog より**プロンプトレベルのツール選択ガイダンス**が有効と判断。

### 次のアクション

- [ ] arg_fixer に `"value"` → `"content"` マッピングを追加（write_file の引数修正）
- [ ] Experiment B（SyntaxError 特化フィードバック）は SyntaxError が実際に複数回出た時に有効か再評価
- [ ] 実際の失敗パターン（誤ツール選択・早期終了）に対するプロンプト改善を優先検討
