import argparse
import asyncio

from agent import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP オーケストレーター")
    parser.add_argument("prompt", help="LLM へのプロンプト")
    args = parser.parse_args()
    print(asyncio.run(run(args.prompt)) or "")
