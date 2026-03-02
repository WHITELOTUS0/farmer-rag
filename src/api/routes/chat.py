"""
Chat endpoint for streaming RAG agent responses.
"""

import asyncio
import json
import logging
import uuid
from typing import Optional, List, AsyncGenerator, Tuple, Any, Dict

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.deps import get_current_user, get_db_session
from src.api.utils.title_generator import generate_conversation_title
from src.api.services.users import get_or_create_user_profile
from src.agent import create_agent
from src.config.settings import get_settings
from src.database.models import Conversation, Message, Farm, ToolCall as ToolCallModel
from src.database.repositories.advisory import AdvisoryRepository

router = APIRouter()


def _build_farmer_context(
    user_id: uuid.UUID,
    profile,
    farms: list,
) -> Dict[str, Any]:
    """Build farmer context for agent. Handles missing profile/farms/region/location."""
    ctx: Dict[str, Any] = {"user_id": str(user_id)}
    farmer: Dict[str, Any] = {}
    if profile is not None:
        farmer["name"] = getattr(profile, "name", None) or "Unknown"
        farmer["region"] = getattr(profile, "region", None) or "Unknown"
        lat = getattr(profile, "location_lat", None)
        lon = getattr(profile, "location_lon", None)
        if lat is not None and lon is not None:
            try:
                farmer["location"] = {"lat": float(lat), "lon": float(lon)}
            except (TypeError, ValueError):
                pass
    if farmer:
        ctx["farmer"] = farmer

    farms_data = []
    for farm in (farms or []):
        if farm is None:
            continue
        farm_dict: Dict[str, Any] = {"name": getattr(farm, "name", None) or "Unknown"}
        crops_data = []
        for crop in (getattr(farm, "crops", None) or []):
            if crop is None:
                continue
            if getattr(crop, "is_active", True) is False:
                continue
            ct = getattr(crop, "crop_type", None)
            gs = getattr(crop, "current_growth_stage", None)
            crop_item = {
                "type": ct.value if ct and hasattr(ct, "value") else (str(ct) if ct else "unknown"),
                "growth_stage": gs.value if gs and hasattr(gs, "value") else (str(gs) if gs else "planting"),
            }
            pd = getattr(crop, "planting_date", None)
            if pd is not None:
                try:
                    crop_item["planting_date"] = pd.isoformat()[:10] if hasattr(pd, "isoformat") else str(pd)[:10]
                except Exception as e:
                    logger.debug("Could not serialize planting_date: %s", e)
            crops_data.append(crop_item)
        farm_dict["crops"] = crops_data
        farms_data.append(farm_dict)
    if farms_data:
        ctx["farms"] = farms_data

    return ctx


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    mode: str = "chat"


def _build_history(messages: List[Message]) -> list:
    history = []
    for msg in messages:
        if msg.role in ("user", "assistant"):
            history.append({"role": msg.role, "content": msg.content})
    return history


def _sse(data: Any) -> str:
    if isinstance(data, str):
        return f"data: {data}\n\n"
    return f"data: {json.dumps(data)}\n\n"


async def _persist_advisory_and_tool_calls(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    query: str,
    final_result: Dict[str, Any],
) -> None:
    """Persist advisory to advisories table and tool calls to tool_calls table."""
    if not final_result.get("success", True):
        return
    response_text = final_result.get("response", "")
    if not response_text:
        return
    try:
        groundedness = float(final_result.get("groundedness_score", 0.0))
        verification = final_result.get("verification_details") or {}
        source_summaries = final_result.get("source_summaries") or []
        tool_call_records = final_result.get("tool_call_records") or []

        settings = get_settings()
        advisory_repo = AdvisoryRepository(db)
        await advisory_repo.create_advisory(
            user_id=user_id,
            query=query,
            response=response_text,
            groundedness_score=groundedness,
            model_used=settings.primary_model,
            sources=[{"source": s.get("source"), "confidence": s.get("confidence"), "text": s.get("text_preview", "")} for s in source_summaries] if source_summaries else None,
            tools_used=[{"tool_name": tc.get("tool_name"), "input": tc.get("tool_input"), "output": tc.get("tool_output")} for tc in tool_call_records] if tool_call_records else None,
            claims_verified=verification.get("claims"),
        )
        await db.flush()

        for tc in tool_call_records:
            tool_in = tc.get("tool_input") or {}
            tool_out = tc.get("tool_output")
            if tool_out is None:
                out_serialized = None
            elif isinstance(tool_out, (dict, list)):
                out_serialized = tool_out
            else:
                out_serialized = {"value": str(tool_out)}
            tool_call = ToolCallModel(
                conversation_id=conversation_id,
                tool_name=str(tc.get("tool_name", "unknown")),
                tool_input=tool_in,
                tool_output=out_serialized,
            )
            db.add(tool_call)
        await db.flush()
    except Exception as e:
        logger.error("Failed to persist advisory/tool-call records: %s", e)


@router.post("/")
async def chat(
    req: ChatRequest,
    stream: bool = True,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    agent = create_agent()
    conversation_id = req.conversation_id

    convo = None
    if conversation_id:
        try:
            conversation_uuid = uuid.UUID(conversation_id)
        except ValueError:
            return {"error": "invalid conversation id"}
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_uuid,
                Conversation.user_id == user["user_id"],
            )
        )
        convo = result.scalar_one_or_none()
        if convo is None:
            return {"error": "conversation not found"}

    if convo is None:
        convo = Conversation(user_id=user["user_id"], title=None)
        db.add(convo)
        await db.flush()
        conversation_id = str(convo.id)

    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == convo.id)
        .order_by(Message.created_at.asc())
    )
    history = _build_history(list(history_result.scalars().all()))

    user_msg = Message(
        conversation_id=convo.id,
        role="user",
        content=req.message,
    )
    db.add(user_msg)
    await db.flush()
    
    # Generate title from first message if conversation doesn't have one
    if convo.title is None:
        title = generate_conversation_title(req.message)
        convo.title = title
        await db.flush()

    # Enrich farmer_context with profile + farms (fallback to minimal if missing/fails)
    profile = None
    farms: list = []
    try:
        _, profile = await get_or_create_user_profile(db, user["user_id"], email=user.get("email"))
        farms_result = await db.execute(
            select(Farm)
            .where(Farm.user_id == user["user_id"])
            .options(selectinload(Farm.crops))
        )
        farms = list(farms_result.scalars().all() or [])
    except Exception as e:
        logger.warning("Failed to load farmer profile/farms; continuing with minimal context: %s", e)
    farmer_context = _build_farmer_context(user["user_id"], profile, farms)

    async def event_stream() -> AsyncGenerator[str, None]:
        # Send conversation_id early so frontend can use it
        yield _sse({
            "type": "conversation",
            "value": {
                "conversation_id": conversation_id,
                "title": convo.title,
            }
        })
        
        final_result = None
        async for event_type, payload in agent.astream(
            query=req.message,
            farmer_context=farmer_context,
            conversation_history=history,
        ):
            if event_type == "token":
                yield _sse({"type": "text", "value": payload})
            elif event_type == "tool_start":
                yield _sse({"type": "tool", "value": payload})
            elif event_type == "error":
                yield _sse({"type": "error", "value": payload})
                yield _sse("[DONE]")
                return
            elif event_type == "final":
                final_result = payload

        # Agent does not stream tokens; chunk and yield response for progressive display
        if final_result:
            response_text = final_result.get("response", "")
            if response_text:
                chunk_size = 30
                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i : i + chunk_size]
                    yield _sse({"type": "text", "value": chunk})
            assistant_msg = Message(
                conversation_id=convo.id,
                role="assistant",
                content=final_result.get("response", ""),
                extra_metadata={
                    "groundedness_score": final_result.get("groundedness_score"),
                    "tools_called": final_result.get("tools_called", []),
                    "sources_used": final_result.get("sources_used", 0),
                },
            )
            db.add(assistant_msg)
            await db.flush()

            await _persist_advisory_and_tool_calls(
                db, user["user_id"], convo.id, req.message, final_result
            )

            yield _sse(
                {
                    "type": "data",
                    "value": {
                        "conversation_id": conversation_id,
                        "groundedness_score": final_result.get("groundedness_score"),
                        "tools_called": final_result.get("tools_called", []),
                        "sources_used": final_result.get("sources_used", 0),
                    },
                }
            )
        yield _sse("[DONE]")  # Always end stream (handles both success and no-final cases)

    if not stream:
        result = await asyncio.to_thread(
            agent.run,
            query=req.message,
            farmer_context=farmer_context,
            conversation_history=history,
        )
        assistant_msg = Message(
            conversation_id=convo.id,
            role="assistant",
            content=result.get("response", ""),
            extra_metadata={
                "groundedness_score": result.get("groundedness_score"),
                "tools_called": result.get("tools_called", []),
                "sources_used": result.get("sources_used", 0),
            },
        )
        db.add(assistant_msg)
        await db.flush()

        await _persist_advisory_and_tool_calls(
            db, user["user_id"], convo.id, req.message, result
        )

        return {
            "conversation_id": conversation_id,
            "response": result.get("response", ""),
            "groundedness_score": result.get("groundedness_score"),
            "tools_called": result.get("tools_called", []),
            "sources_used": result.get("sources_used", 0),
        }

    return StreamingResponse(event_stream(), media_type="text/event-stream")
