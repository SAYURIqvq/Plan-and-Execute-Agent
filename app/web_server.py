from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import run

app = FastAPI()


class ChatRequest(BaseModel):
    message: str


@app.post("/chat")
async def chat(req: ChatRequest) -> dict:
    answer = await run(req.message)
    return {"answer": answer or "(応答なし)"}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
