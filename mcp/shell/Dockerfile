FROM python:3.11-slim

RUN pip install --no-cache-dir shell-mcp-server

# shell-mcp-server 0.1.0 のバグ修正:
# CLI スクリプトが asyncio.run() なしで async 関数を呼んでいるため修正
RUN sed -i \
    's/sys.exit(main())/import asyncio; sys.exit(asyncio.run(main()))/' \
    /usr/local/bin/shell-mcp-server

VOLUME ["/workspace"]

CMD ["tail", "-f", "/dev/null"]
