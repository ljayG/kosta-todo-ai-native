"""저장소 계층. 저장 방식만 책임지고 업무 규칙은 모른다.

지금은 InMemoryTodoRepository를 쓰고, Supabase를 붙일 때는 같은
TodoRepository 인터페이스를 구현한 클래스를 추가해 교체한다.
"""

from datetime import date, datetime, timedelta, timezone
from threading import Lock
from typing import Protocol
from uuid import UUID, uuid4

from app.schemas import Todo


class TodoRepository(Protocol):
    def list(self) -> list[Todo]: ...
    def get(self, todo_id: UUID) -> Todo | None: ...
    def add(self, text: str, priority: str, today: bool, due_date: date | None = None) -> Todo: ...
    def update(self, todo_id: UUID, changes: dict) -> Todo | None: ...
    def delete(self, todo_id: UUID) -> bool: ...


class InMemoryTodoRepository:
    """프로세스 메모리에 저장한다. 서버를 재시작하면 데이터가 사라진다."""

    def __init__(self) -> None:
        self._items: dict[UUID, Todo] = {}
        self._lock = Lock()
        self._last_time = datetime.min.replace(tzinfo=timezone.utc)

    def _now(self) -> datetime:
        # 시계 해상도가 낮아도 시각이 항상 증가하도록 보정한다.
        # (목록 정렬 기준 created_at과 AC-34의 updated_at 증가를 보장)
        now = datetime.now(timezone.utc)
        if now <= self._last_time:
            now = self._last_time + timedelta(microseconds=1)
        self._last_time = now
        return now

    def list(self) -> list[Todo]:
        with self._lock:
            # API-02: created_at 오름차순, 같으면 id 오름차순
            return sorted(self._items.values(), key=lambda t: (t.created_at, str(t.id)))

    def get(self, todo_id: UUID) -> Todo | None:
        with self._lock:
            return self._items.get(todo_id)

    def add(self, text: str, priority: str, today: bool, due_date: date | None = None) -> Todo:
        with self._lock:
            now = self._now()
            todo = Todo(
                id=uuid4(),
                text=text,
                done=False,
                priority=priority,
                today=today,
                due_date=due_date,
                created_at=now,
                updated_at=now,
            )
            self._items[todo.id] = todo
            return todo

    def update(self, todo_id: UUID, changes: dict) -> Todo | None:
        with self._lock:
            current = self._items.get(todo_id)
            if current is None:
                return None
            updated = current.model_copy(update={**changes, "updated_at": self._now()})
            self._items[todo_id] = updated
            return updated

    def delete(self, todo_id: UUID) -> bool:
        with self._lock:
            return self._items.pop(todo_id, None) is not None
