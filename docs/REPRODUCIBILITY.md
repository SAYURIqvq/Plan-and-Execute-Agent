# 复现与验证范围

## 依赖

`app/requirements.txt` 自动引用 `app/constraints.txt`。约束文件来自独立 Python 3.12 环境的已安装版本；在该环境中完整的 82 个确定性测试通过。它固定直接与传递依赖，Docker 构建和 CI 使用同一份约束。Linux/Python 3.11 的 CI 仍应以远端实际结果为准。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r app/requirements.txt
python -m pip check
python -m pytest app/tests -q
```

更新依赖时在干净环境中解除或更新约束、安装并运行完整测试，然后重新生成约束文件。不要直接把其他项目环境的 freeze 覆盖进来。

## 本地启动

`bash scripts/start` 从脚本位置定位仓库，检查 Docker、读取 Linux daemon 内 socket 的 GID，并通过环境变量交给 Compose。不会创建或覆盖 `.env`。首次读取 GID 可能拉取 `python:3.11-slim`；可提前设置 shell 环境变量 `DOCKER_GID` 避免这一步。

GPU runtime 探测与 CPU 回退仍保留。启动脚本的离线测试使用假的 Docker 命令验证路径、GID 传递与 `.env` 保留；它不代表真实 Docker/Ollama/MCP 集成已通过。Docker socket 访问只适合可信的本地开发环境。

## 模型实验

```bash
bash scripts/bench.sh --tier quick --models qwen2.5:7b
```

需要先启动服务并下载模型，输出保存在 `test_results/bench_YYYYMMDD_HHMMSS/`。报告结果时保留任务文本、模型具体版本、配置、硬件、原始日志、成功判定与失败案例。确定性测试使用 mock，不能证明模型任务成功率。
