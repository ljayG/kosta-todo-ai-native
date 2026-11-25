"""계층 조립. 저장소 구현을 바꿀 때는 이 파일만 고친다."""

from functools import lru_cache

from fastapi import Depends

from app.repositories.todo_repository import InMemoryTodoRepository, TodoRepository
from app.services.todo_service import TodoService


@lru_cache
def get_repository() -> TodoRepository:
    # 프로세스 하나에 저장소 하나 (In-Memory 데이터를 요청 간에 공유)
    return InMemoryTodoRepository()


def get_todo_service(repo: TodoRepository = Depends(get_repository)) -> TodoService:
    return TodoService(repo)
