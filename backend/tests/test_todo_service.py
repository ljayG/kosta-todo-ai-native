"""서비스·저장소 계층 단위 테스트 (HTTP 없이)."""

from uuid import uuid4

import pytest

from app.repositories.todo_repository import InMemoryTodoRepository
from app.schemas import TodoCreate, TodoUpdate
from app.services.todo_service import TodoNotFoundError, TodoService


@pytest.fixture
def service():
    return TodoService(InMemoryTodoRepository())


def test_create_starts_not_done(service):
    todo = service.create_todo(TodoCreate(text="보고서", priority="high", today=True))
    assert todo.done is False
    assert service.list_todos() == [todo]


def test_update_unknown_raises(service):
    with pytest.raises(TodoNotFoundError):
        service.update_todo(uuid4(), TodoUpdate(done=True))


def test_delete_unknown_raises(service):
    with pytest.raises(TodoNotFoundError):
        service.delete_todo(uuid4())


def test_timestamps_strictly_increase_even_when_fast():
    repo = InMemoryTodoRepository()
    todos = [repo.add(f"할 일 {i}", "medium", False) for i in range(200)]
    times = [t.created_at for t in todos]
    assert times == sorted(times)
    assert len(set(times)) == len(times)
    assert [t.text for t in repo.list()] == [t.text for t in todos]


def test_update_changes_only_set_fields():
    data = TodoUpdate(done=True)
    assert data.changes() == {"done": True}


def test_create_passes_due_date(service):
    from datetime import date

    todo = service.create_todo(TodoCreate(text="보고서", due_date="2026-11-28"))
    assert todo.due_date == date(2026, 11, 28)


def test_update_changes_includes_null_due_date():
    assert TodoUpdate(due_date=None).changes() == {"due_date": None}


def test_list_filters_by_category(service):
    service.create_todo(TodoCreate(text="업무", category="work"))
    service.create_todo(TodoCreate(text="개인"))
    assert [t.text for t in service.list_todos("work")] == ["업무"]
    assert [t.text for t in service.list_todos()] == ["업무", "개인"]


def test_create_passes_category(service):
    todo = service.create_todo(TodoCreate(text="공부", category="study"))
    assert todo.category == "study"
