import uuid
from typing import Any, List

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.api import deps as api_deps
import src.api.routes.chat as chat_routes
from src.database.models import Conversation, Message


class FakeResult:
    def __init__(self, items: List[Any] | None = None):
        self._items = items or []

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None

    def scalars(self):
        class _ScalarWrapper:
            def __init__(self, items):
                self._items = items

            def all(self):
                return list(self._items)

        return _ScalarWrapper(self._items)


class FakeSession:
    def __init__(self):
        self.added = []

    async def execute(self, statement):
        # Return empty results for any select.
        return FakeResult([])

    def add(self, obj):
        # Ensure IDs are set for new objects.
        if getattr(obj, "id", None) is None and hasattr(obj, "id"):
            try:
                obj.id = uuid.uuid4()
            except Exception:
                pass
        self.added.append(obj)

    async def flush(self):
        return None

    async def delete(self, obj):
        if obj in self.added:
            self.added.remove(obj)


class FakeAgent:
    def run(self, query: str, **kwargs):
        return {
            "response": f"Echo: {query}",
            "groundedness_score": 1.0,
            "tools_called": [],
            "sources_used": 0,
        }

    async def astream(self, query: str, **kwargs):
        for token in ["Echo:", " ", query]:
            yield "token", token
        yield "final", self.run(query)


def fake_agent_factory():
    return FakeAgent()


@pytest.fixture()
def client(monkeypatch):
    app = create_app()

    async def override_get_db_session():
        yield FakeSession()

    def override_get_current_user():
        return {"user_id": uuid.uuid4(), "email": "test@example.com", "claims": {}}

    app.dependency_overrides[api_deps.get_db_session] = override_get_db_session
    app.dependency_overrides[api_deps.get_current_user] = override_get_current_user
    monkeypatch.setattr(chat_routes, "create_agent", fake_agent_factory)

    return TestClient(app)


def test_chat_non_stream(client: TestClient):
    response = client.post("/chat?stream=false", json={"message": "hello"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["response"].startswith("Echo:")
    assert "conversation_id" in payload


def test_chat_stream(client: TestClient):
    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    body = response.text
    assert "data:" in body
