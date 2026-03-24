# 実験: tool_desc_memory_clarify

**日時**: 2026-03-07
**ステータス**: 完了

---

## 目的

英語・中国語両プロンプトで `remember()` がファイル保存の代替として使われる問題を解消する。
`_TOOL_LIST` / `_TOOL_LIST_ZH` の memory ツール説明に
「write_file の代替として使うな」という制約を追記する。

## 仮説

ツール説明に明示的な使い分け基準を追加することで：
- Task2: asyncio_notes.txt が `write_file` で保存される
- Task3: review.txt が `remember()` 経由ではなく `write_file` で直接保存される
- Judge スコア: 5/15（英語ベースライン）→ 8/15 以上を期待

根拠：
- 実験⑯/英語再実験で `remember()` 誤用は言語によらずモデルの癖と判明
- ツール説明に「ファイル保存の代替ではない」と書けばモデルの判断基準になる
- 英語では remember→write_file の2段階を踏んだ（説明強化で write_file のみに短縮できる）

## 設定変更

| 項目 | 変更前 | 変更後 |
|------|--------|--------|
| `_TOOL_LIST` memory 行 | `persist key-value notes` | `persist key-value notes across sessions. Do NOT use as a substitute for write_file — always save task outputs to files.` |
| `_TOOL_LIST_ZH` 内存行 | `持久化键值笔记。` | `在会话间持久化键值笔记。不要用来代替 write_file——任务输出必须保存到 /data/ 文件。` |

## 実験コマンド

```bash
# 英語（変更の効果を単独で見る）
./scripts/bench.sh --tier medium --models qwen2.5:14b --mode react

# 中国語（ベスト設定との比較）
./scripts/bench.sh --tier medium --models qwen2.5:14b --prompt zh --mode react
```

---

## 結果

**実行日時**: 2026-03-07 16:03（英語）/ 16:37（中国語）
**結果ディレクトリ**: test_results/bench_20260307_160351（EN）/ bench_20260307_163745（ZH）

### メトリクス

| 言語 | TCA | ErrRate | AvgTurns | AvgSec |
|------|-----|---------|----------|--------|
| 英語 (react) | 0.683 | 0.083 | 3.7 | 653 |
| 中国語 (react_zh) | 0.841 | 0.222 | 5.3 | 957 |

### タスク別結果

**英語 (bench_20260307_160351)**

| タスク | 結果 | 所要時間 | Judge |
|--------|------|---------|-------|
| タスク1: SQLite INSERT → sales_report.txt | ❌ (Turn2 テキスト終了) | 468s | 1/5 |
| タスク2: Web 検索 → asyncio_notes.txt | ❌ (テキスト終了・ファイル未作成) | 647s | 1/5 |
| タスク3: primes.py + review.txt | ❌ (SyntaxError修正ループ・review未作成) | 892s | 1/5 |

**Judge 合計（英語）: 3/15**

**中国語 (bench_20260307_163745)**

| タスク | 結果 | 所要時間 | Judge |
|--------|------|---------|-------|
| タスク1: SQLite INSERT → sales_report.txt | ❌ (SyntaxError ループ・timeout) | 1248s | 1/5 |
| タスク2: Web 検索 → asyncio_notes.txt | ❌ (テキスト終了・ファイル未作成) | 585s | 1/5 |
| タスク3: primes.py + review.txt | ✅ (remember()→write_file() 両呼び出し) | 1099s | 3/5 |

**Judge 合計（中国語）: 5/15**

### 動作詳細（重要）

**Task2（両言語共通）**: `remember()` の問題以前に、web_search → fetch_page の後テキスト回答で終了。
asyncio_notes.txt への `write_file` がそもそも呼ばれない別の失敗パターン。

**Task3（ZH）**: `remember()` → `write_file()` の2段階パターンが継続。
`remember()` は呼ばれるが、その後 `write_file()` も呼んで review.txt 作成に成功。
ツール説明追記による部分的改善（前回：`remember()` のみで終了 → 今回：両方呼んでファイル作成）。

**Task3（EN）**: primes.py の SyntaxError 修正ループで時間を消費し、review ステップに到達できず。

## 考察

### 仮説の検証

仮説は**部分的に正しかった**。

ZH Task3 では `remember()` 後に `write_file()` を呼ぶようになり review.txt が作成された（改善）。
しかし `remember()` 自体は消えておらず、ツール説明の追記だけで完全に止めることはできなかった。

Task2 の問題（write_file を呼ばずテキスト終了）はツール説明変更とは別の根本原因であることが判明。

### 主な発見

- **ZH Task3**: remember() 問題は部分解消（→ 最終的にファイルが作成される）
- **Task2**: web 情報取得後にテキスト回答で終了するパターンは remember() とは無関係の別問題
- **EN Task3**: SyntaxError（`import math` 忘れ）の修正に2ターン費やし、review ステップ未到達
- 英語プロンプトはTCA=0.683と低め（中国語 0.841 より劣る）、AvgSec も 653s と短いが Judge も低い

### 副作用

- EN のベースライン（修正前 5/15）より悪化（3/15）— 非決定性の影響が大きい
- ZH の AvgSec が 957s と長い（前回比で増加）— ターン数増加による

### 結論

**条件付き採用** — ZH では Task3 改善効果が確認できた（3→5/15）が、Task2 の失敗パターンは別対策が必要。
`remember()` 禁止の一文は維持しつつ、Task2 向けに「取得した情報は必ず write_file でファイルに保存してから終了」を追加すべき。

### 次のアクション

- [ ] Task2 の根本対策: 「情報取得後は必ず write_file でファイル保存してから終了する」をプロンプトに追記
- [ ] Task1 の SyntaxError 問題: `import math` 忘れなど import エラーへの対処（プロンプトまたは fixer）
- [ ] EN の Task3 失敗: SyntaxError 修正に複数ターン要する問題は Experiment B（SyntaxError watchdog）で対処
