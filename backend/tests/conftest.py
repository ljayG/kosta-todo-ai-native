import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_repository
from app.main import app
from app.repositories.todo_repository import InMemoryTodoRepository


@pytest.fixture
def client():
    """테스트마다 비어 있는 새 In-Memory 저장소를 쓴다."""
    repo = InMemoryTodoRepository()
    app.dependency_overrides[get_repository] = lambda: repo
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_todo(client):
    def _make(text="할 일", **fields):
        res = client.post("/api/todos", json={"text": text, **fields})
        assert res.status_code == 201, res.text
        return res.json()

    return _make
