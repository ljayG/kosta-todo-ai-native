"""라우터 계층. HTTP 요청/응답 변환만 담당한다 (docs/api-spec.md API-02~05)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.dependencies import get_todo_service
from app.schemas import Category, Todo, TodoCreate, TodoUpdate
from app.services.todo_service import TodoNotFoundError, TodoService

router = APIRouter(prefix="/api/todos", tags=["todos"])

NOT_FOUND = "할 일을 찾을 수 없습니다."


@router.get("", response_model=list[Todo])
def list_todos(
    category: Category | None = Query(None, description="카테고리 필터 (없으면 전체)"),
    service: TodoService = Depends(get_todo_service),
) -> list[Todo]:
    return service.list_todos(category)


@router.post("", response_model=Todo, status_code=status.HTTP_201_CREATED)
def create_todo(data: TodoCreate, service: TodoService = Depends(get_todo_service)) -> Todo:
    return service.create_todo(data)


@router.patch("/{todo_id}", response_model=Todo)
def update_todo(
    todo_id: UUID, data: TodoUpdate, service: TodoService = Depends(get_todo_service)
) -> Todo:
    try:
        return service.update_todo(todo_id, data)
    except TodoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: UUID, service: TodoService = Depends(get_todo_service)) -> Response:
    try:
        service.delete_todo(todo_id)
    except TodoNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
