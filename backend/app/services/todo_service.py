"""서비스 계층. 업무 규칙을 담당하고 HTTP와 저장 방식은 모른다."""

from uuid import UUID

from app.repositories.todo_repository import TodoRepository
from app.schemas import Category, Todo, TodoCreate, TodoUpdate


class TodoNotFoundError(Exception):
    """해당 id의 할 일이 없을 때 발생한다. 라우터가 404로 바꾼다."""

    def __init__(self, todo_id: UUID) -> None:
        super().__init__(f"할 일을 찾을 수 없습니다: {todo_id}")
        self.todo_id = todo_id


class TodoService:
    def __init__(self, repository: TodoRepository) -> None:
        self._repo = repository

    def list_todos(self, category: Category | None = None) -> list[Todo]:
        # category가 없으면 전체 (FR-16)
        return self._repo.list(category=category)

    def create_todo(self, data: TodoCreate) -> Todo:
        # 새 할 일은 항상 미완료로 시작한다 (FR-01)
        return self._repo.add(
            text=data.text,
            priority=data.priority,
            today=data.today,
            due_date=data.due_date,
            category=data.category,
        )

    def update_todo(self, todo_id: UUID, data: TodoUpdate) -> Todo:
        updated = self._repo.update(todo_id, data.changes())
        if updated is None:
            raise TodoNotFoundError(todo_id)
        return updated

    def delete_todo(self, todo_id: UUID) -> None:
        if not self._repo.delete(todo_id):
            raise TodoNotFoundError(todo_id)
