# rtw-ollama-agent

LangChain + Ollama + MCP で動くローカル Plan-and-Execute エージェント。

「Reinventing The Wheel」の名の通り、既存のエージェントフレームワークをなるべく使わず、計画・実行・リプランのループを自前で実装しています。

---

## 特徴

- **完全ローカル実行** — Ollama によりモデルをローカルで動かします（デフォルト: `qwen2.5:7b`）
- **Plan-and-Execute** — LLM がタスクを番号付きステップに分解してから逐次実行します
- **自動リプラン** — ステップ失敗時や未完了ステップが残った場合に、完了済みを引き継ぎながら計画を立て直します
- **ルーター** — 挨拶・雑談はキーワード判定で即 Chat パスへ、ツールが必要なタスクのみ Agent パスへ振り分けます
- **Input Fixer** — 小型モデルが幻覚するツール名・引数名・エスケープ文字を自動修正してから呼び出します
- **ガードレール** — Watchdog（繰り返し失敗検知）、言語ガード（日本語強制）、タイムアウト（`EXEC_TIMEOUT`）を備えます
- **メトリクス** — TCA / ArgFit / StepCR を各セッション後に `metrics.jsonl` へ記録します
- **MCP ツール** — 6種のツールサーバーをコンテナで起動します
- **モジュール構造** — 責務ごとにファイルを分割し、純粋関数を中心に単体テストを整備しています

---

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────┐
│ executor.py          run()                              │
│   ├── _quick_classify() / classify_intent()  ← Router  │
│   ├── planner.py     make_plan()                        │
│   │     └── gather_current_state()                      │
│   └── exec_loop.py   run_exec_loop()                    │
│         ├── _fix_tool_name()   ← Tool Name Fixer        │
│         ├── _fix_args()        ← Arg Fixer              │
│         ├── _fix_content()     ← Content Fixer          │
│         ├── _invoke_tool()                              │
│         ├── _build_watchdog_hint()  ← Watchdog          │
│         └── planner.py  _apply_replan()                 │
└─────────────────────────────────────────────────────────┘
```

### ファイル構成

```
app/
├── main.py          # エントリポイント (argparse + asyncio.run)
├── executor.py      # Router → plan → exec の接続
├── exec_loop.py     # 実行ループ + Input Fixer + Watchdog + メトリクス
├── planner.py       # LLM による計画生成・リプラン・状態収集
├── models.py        # Step dataclass / parse_steps / format_checklist
├── prompts.py       # 各フェーズのプロンプトテンプレート
├── utils.py         # MetricsLogger / setup_logging / ヘルパー関数
├── config.py        # 定数 (MAX_STEPS, EXEC_TIMEOUT など)
├── llm.py           # Ollama クライアント + モデル別設定
├── servers/         # MCP サーバー設定
└── tests/           # 単体テスト (pytest)
```

---

## MCP ツール

| ツール | 用途 |
|---|---|
| filesystem | ファイル読み書き (`/data/` 以下) |
| shell | コマンド実行 (`/workspace`, `/data`) |
| websearch | Web 検索 + ページ取得 |
| time | 現在日時の取得 (JST) |
| sqlite | SQLite DB 操作 (`/data/agent.db`) |
| memory | キーバリュー形式のメモ永続化 |

---

## ガードレール

| 機能 | 説明 |
|---|---|
| Tool Name Fixer | 幻覚ツール名をエイリアステーブル + difflib で修正 |
| Arg Fixer | 誤った引数名（`cmd`→`command` 等）をスキーマに合わせて修正 |
| Content Fixer | `write_file` の `\n` リテラルを実改行に変換（SyntaxError 防止） |
| Watchdog | 同一ツールが 2 回以上失敗した場合、リプラン時にヒントを注入 |
| Language Guard | SYSTEM_PROMPT で日本語出力を強制 |
| EXEC_TIMEOUT | 実行ループ全体・各 LLM 呼び出しを `asyncio.wait_for` でカット（デフォルト 300 秒） |

---

## メトリクス

各セッション終了時に `/app/logs/metrics.jsonl` へ 1 行追記されます。

| 指標 | 説明 |
|---|---|
| TCA | Tool Calling Accuracy — ターン中にツールを呼んだ割合 |
| ArgFit | 引数修正なしでスキーマに一致したツール呼び出しの割合 |
| StepCR | Step Completion Rate — 全ステップ中に完了できた割合 |

---

## セットアップ

**前提:** Docker / Docker Compose がインストールされていること

```bash
git clone https://github.com/stanaka1110/rtw-ollama-agent.git
cd rtw-ollama-agent

# コンテナをビルド・起動 (初回は Ollama モデルのダウンロードに時間がかかります)
docker compose up -d
```

`ollama` サービスの `healthcheck` が通ればエージェントを使えます。

```bash
docker compose ps
```

---

## 使い方

プロジェクトルートの `agent` スクリプト経由で実行します。

```bash
chmod +x agent  # 初回のみ

./agent "ToDoリストに「買い物」を追加して"
./agent "現在時刻を教えて"
./agent "hello world を出力する Python を書いて実行して"
./agent "agent.db に users テーブルを作って3件のサンプルデータを挿入して"
```

---

## モデルの変更

`docker-compose.yml` の環境変数を変更します。

```yaml
environment:
  - OLLAMA_MODEL=qwen2.5:7b  # 任意の Ollama モデル
```

変更後は `docker compose up -d` で再起動します。

### サポート済みモデル（`llm.py` に設定あり）

| モデル | サイズ | 特徴 |
|---|---|---|
| `qwen2.5:7b` | 7B | ベースライン（デフォルト） |
| `qwen2.5:14b` | 14B | 汎用 |
| `llama3.1:8b` | 8B | Meta 汎用 |
| `llama3.2:3b` | 3B | 軽量 |
| `mistral:7b` | 7B | 汎用 |
| `gemma3:4b` | 4B | ノートPC 向け汎用 |
| `gemma3:9b` | 9B | Google 汎用 |
| `phi4` | 14B | STEM・論理推論 |
| `lfm2.5-thinking` | 1.2B | 超軽量・推論特化 |
| `qwen3:30b-a3b` | 30B(MoE) | 高効率フラグシップ |
| `deepseek-r1:14b` | 14B | 蒸留版・推論特化 |

上記以外のモデルはデフォルト設定（`temperature=0.0, num_ctx=4096`）で動作します。

---

## テスト

### 単体テスト

```bash
docker exec langchain_app python -m pytest tests/ -v
```

| テストファイル | 対象 |
|---|---|
| `test_models.py` | `parse_steps` / `format_checklist` |
| `test_utils.py` | `_sanitize` / `_task_message` / `_tool_descriptions` |
| `test_planner.py` | `gather_current_state` / `_apply_replan` |
| `test_exec_loop.py` | `_invoke_tool` / `_update_step` |

### モデル比較テスト

複数モデルを順番に実行して結果とメトリクスを比較します。

```bash
./test_models.sh
```

結果は `test_results/YYYYMMDD_HHMMSS/` 以下に保存されます。

| ファイル | 内容 |
|---|---|
| `model_test_results.txt` | 各モデル・タスクの結果と所要時間 |
| `metrics_snapshot.jsonl` | 今回分の生メトリクス |
| `*_task*.stderr.log` | モデル/タスクごとの詳細ログ |