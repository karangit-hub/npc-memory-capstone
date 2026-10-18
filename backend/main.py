from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ollama import AsyncClient, ResponseError
import httpx

from memory_store import (
    DEFAULT_DB_PATH as DATABASE_PATH,
    get_recent_messages,
    init_db,
    save_conversation,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(DATABASE_PATH)
    yield


app = FastAPI(title="NPC Persistent Memory API", lifespan=lifespan)

# Our locally installed AI model
MODEL = "qwen3:8b"

# Connect to the local Ollama server
llm = AsyncClient(
    host="http://127.0.0.1:11434",
    timeout=120.0
)


class ChatRequest(BaseModel):
    player_id: str
    npc_id: str
    message: str


@app.get("/")
def home():
    return {"message": "NPC Memory Backend is running!"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/chat")
async def chat(request: ChatRequest):
    history = get_recent_messages(
        request.player_id, request.npc_id, db_path=DATABASE_PATH
    )

    try:
        response = await llm.chat(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are {request.npc_id}, a friendly "
                        "guard in a medieval fantasy village. "
                        "Speak naturally and stay in character. "
                        "Keep your replies to 1-3 sentences. "
                        "Do not claim to remember past conversations "
                        "unless that information is provided."
                    )
                },
                *history,
                {
                    "role": "user",
                    "content": request.message
                }
            ],
            stream=False,
            think=False
        )

    except (httpx.HTTPError, ResponseError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"Local Ollama request failed: {error}"
        ) from error

    reply = response.message.content
    if reply is None:
        raise HTTPException(status_code=502, detail="Local Ollama returned no reply")

    save_conversation(
        request.player_id,
        request.npc_id,
        request.message,
        reply,
        db_path=DATABASE_PATH,
    )

    return {
        "npc_id": request.npc_id,
        "reply": reply
    }
