# 実験: react_finish_tool

**日時**: 2026-03-06
**ステータス**: 完了

---

## 目的

react モードの TCA 低下（実験⑪: 0.472）の原因である「thinking テキストで早期終了」パターンを
`finish_tool` 終了戦略で排除し、Judge スコアを改善する。

現状: モデルが "まず〜します" というテキストを出力した瞬間にループが終了してしまい、
実際のツール実行に至らない（SQLite タスクが tool call 0回で 0/5）。

## 仮説

`REACT_TERMINATION=finish_tool` にすることで:
- テキスト応答 → 終了ではなく、フィードバック注入してループ継続
- モデルは `finish()` を明示的に呼ぶまで作業を続けざるを得ない
- 結果: TCA 改善 / Judge スコア 7/15 → 10/15 以上を期待

副作用リスク:
- ループが終わらずタイムアウトになる可能性（finish() を呼ばずフィードバックループに入る）
- プロンプトに `finish()` の説明がないため呼び方を知らない可能性

## 設定変更

| 項目 | 変更前 | 変更後 |
|------|--------|--------|
| `REACT_TERMINATION` | `text` | `finish_tool` |
| `AGENT_MODE` | `react` | `react` (変更なし) |
| `PROMPT_VARIANT` | `zh` | `zh` (変更なし) |
| モデル | `qwen2.5:14b` | `qwen2.5:14b` (変更なし) |

## 実験コマンド

```bash
REACT_TERMINATION=finish_tool \
  ./scripts/bench.sh --tier medium --models qwen2.5:14b --prompt zh --mode react
```

比較用（前回ベースライン、実験⑪相当）:
```bash
./scripts/bench.sh --tier medium --models qwen2.5:14b --prompt zh --mode react
```

---

## 結果

**実行日時**: 2026-03-06 02:45
**結果ディレクトリ**: test_results/bench_20260306_024521

### ⚠️ 実験設定の問題

`bench.sh` の `docker exec` に `-e REACT_TERMINATION` が含まれておらず、
コンテナ側はデフォルトの `text` 戦略で動作した。
本実験は実質的に **text 戦略のベースライン追加計測** となった。

### メトリクス

| モデル | TCA | StepCR | ErrRate | Replans | AvgTurns | AvgSec |
|--------|-----|--------|---------|---------|----------|--------|
| qwen2.5:14b | 0.933 | N/A | 0.067 | 0.0 | 4.3 | 1163 |

### タスク別結果

| タスク | 結果 | 所要時間 | Judge |
|--------|------|---------|-------|
| タスク1: SQLite + Python レポート | ❌ (timeout) | 1254s | 1/5 |
| タスク2: Web 検索 → asyncio_notes.txt | ❌ (timeout) | 1301s | 1/5 |
| タスク3: primes.py + review.txt | ❌ (成果物不完全) | 1020s | 2/5 |

**Judge 合計**: 4/15（平均 1.3/5）

---

## 結果②（実際の finish_tool 実験）

**実行日時**: 2026-03-06 09:31
**結果ディレクトリ**: test_results/bench_20260306_093100

### メトリクス（3タスク分のみ）

| モデル | TCA | StepCR | ErrRate | Replans | AvgTurns | AvgSec |
|--------|-----|--------|---------|---------|----------|--------|
| qwen2.5:14b | 0.333 | N/A | 0.0 | 0.0 | 2.0 | 948 |

※ metrics_snapshot に前回ベンチ残留3件が混入。この表は本ベンチ3タスク分のみを集計。

### タスク別結果

| タスク | 結果 | 所要時間 | Judge |
|--------|------|---------|-------|
| タスク1: SQLite INSERT → sales_report.txt | ❌ (timeout) | 1237s | 1/5 |
| タスク2: Web 検索 → asyncio_notes.txt | ❌ (timeout) | 1248s | 1/5 |
| タスク3: primes.py + review.txt | ❌ (LLM EOF エラー) | 359s | 0/5 |

**Judge 合計**: 2/15（平均 0.7/5）

### 動作詳細

**タスク1**:
- Turn1 (432s): INSERT 10件 ✅ → "OK: 10 rows affected"
- Turn2 (340s): テキスト応答 → フィードバック注入（finish_tool 動作）
- Turn3 (390s): テキスト応答 → フィードバック注入
- Turn4: EXEC_TIMEOUT (1200s)
- finish() 未呼び出し、sales_report.txt 未作成

**タスク2**:
- Turn1 (324s): web_search ✅ ("Python asyncio tutorial")
- Turn2 (398s): fetch_page ✅ (realpython.com)
- Turn3 (311s): テキスト応答 → フィードバック注入
- Turn4: EXEC_TIMEOUT (1200s)
- finish() 未呼び出し、asyncio_notes.txt 未作成

**タスク3**:
- Turn1 (350s): LLM ResponseError: unexpected EOF (status code: -1)
- Ollama プロセスがクラッシュ、何も実行できず

### 結論

仮説の副作用リスクが両方とも顕在化した:
1. **finish() を呼ばずフィードバックループに入る** → タスク1・2でタイムアウト
2. **finish() の説明がなく呼び方を知らない** → モデルが finish ツールの存在を認識しないため
3. タスク3はモデル崩壊（EOF エラー）

finish_tool 戦略は現状のプロンプト（finish ツールの説明なし）では機能しない。

## 考察

### 仮説の検証

仮説は**部分的に正しく、部分的に誤っていた**。

「テキスト応答をループ継続のトリガーにする」メカニズム自体は正常に動作した（Turn2・3でフィードバック注入を確認）。
しかし「モデルが finish() を呼んでループを終了する」という根本前提が崩れた。
プロンプトに finish ツールの説明がないため、モデルはその存在を認識できず、テキスト→フィードバック→テキストの無限ループに陥った。

### 主な発見

- finish_tool 戦略のフィードバック注入ロジック自体は正しく動作する（text→continue が機能）
- Judge スコア: text 戦略 4/15 → finish_tool 2/15（悪化）
- TCA: 0.472（text, 実験⑪）→ 0.333（finish_tool）— ツール呼び出し総量が減少
- タスク1・2: finish() 未呼び出しのまま EXEC_TIMEOUT=1200s に到達
- タスク3: 長時間 CPU 負荷の蓄積で Ollama プロセスが EOF クラッシュ

### 副作用

- **EOF クラッシュリスク**: 長時間ループを強制することで、CPU 推論環境では Ollama プロセスがクラッシュする可能性がある
- **フィードバックがコンテキストを肥大化させる**: ループを継続するほどプロンプトが長くなり prefill コストが増加する

### 結論

**却下** — finish ツールの説明がプロンプトにない状態では finish_tool 戦略は機能しない。
必要条件は「react_zh バリアントに finish ツールの存在・呼び方・呼ぶべきタイミングを明記すること」であり、それなしに戦略だけを有効化しても無限ループに陥る。

### 次のアクション

- [ ] `react_zh` プロンプトバリアントに `finish()` ツールの説明を追記（「すべてのタスクが完了したら必ず finish() を呼ぶこと」）
- [ ] finish ツールを MCP ツールとして明示的に登録し、ツール一覧に現れるようにする
- [ ] finish ツール説明追記後に同条件で再実験し Judge スコアの改善を確認する
