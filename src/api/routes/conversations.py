"""
Conversation and message CRUD.
"""

from typing import Optional, List
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db_session
from src.database.models import Conversation, Message

router = APIRouter()


class ConversationCreate(BaseModel):
    title: Optional[str] = None
    tags: Optional[List[str]] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    tags: Optional[List[str]] = None


class MessageCreate(BaseModel):
    role: str
    content: str


@router.get("/", response_model=List[dict])
async def list_conversations(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user["user_id"])
        .order_by(Conversation.created_at.desc())
    )
    items = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "summary": c.summary,
            "tags": c.tags,
        }
        for c in items
    ]


@router.post("/", response_model=dict)
async def create_conversation(
    payload: ConversationCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    convo = Conversation(user_id=user["user_id"], title=payload.title, tags=payload.tags)
    db.add(convo)
    await db.flush()
    return {"id": str(convo.id)}


@router.get("/{conversation_id}", response_model=dict)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user["user_id"],
        )
    )
    convo = result.scalar_one_or_none()
    if convo is None:
        return {"error": "conversation not found"}

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == convo.id)
        .order_by(Message.created_at.asc())
    )
    messages = msg_result.scalars().all()

    return {
        "id": str(convo.id),
        "title": convo.title,
        "summary": convo.summary,
        "tags": convo.tags,
        "messages": [
            {"id": str(m.id), "role": m.role, "content": m.content}
            for m in messages
        ],
    }


@router.patch("/{conversation_id}", response_model=dict)
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user["user_id"],
        )
    )
    convo = result.scalar_one_or_none()
    if convo is None:
        return {"error": "conversation not found"}

    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(convo, field, value)

    await db.flush()
    return {"status": "updated"}


@router.delete("/{conversation_id}", response_model=dict)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user["user_id"],
        )
    )
    convo = result.scalar_one_or_none()
    if convo is None:
        return {"error": "conversation not found"}

    await db.delete(convo)
    await db.flush()
    return {"status": "deleted"}


@router.post("/{conversation_id}/messages", response_model=dict)
async def add_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user["user_id"],
        )
    )
    convo = result.scalar_one_or_none()
    if convo is None:
        return {"error": "conversation not found"}

    msg = Message(
        conversation_id=conversation_id,
        role=payload.role,
        content=payload.content,
    )
    db.add(msg)
    await db.flush()
    return {"id": str(msg.id)}
