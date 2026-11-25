"""요청/응답 모델 (docs/api-spec.md의 Todo 객체)."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

Priority = Literal["high", "medium", "low"]

# 앞뒤 공백 제거 후 1~200자 (FR-01, FR-04)
TodoText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class TodoCreate(BaseModel):
    """API-03 요청. done, id, 시각 필드 등 알 수 없는 필드는 거부한다."""

    model_config = ConfigDict(extra="forbid")

    text: TodoText
    priority: Priority = "medium"
    today: bool = False


class TodoUpdate(BaseModel):
    """API-04 요청. 하나 이상의 필드가 필요하며 null 값은 허용하지 않는다."""

    model_config = ConfigDict(extra="forbid")

    text: TodoText | None = None
    done: bool | None = None
    priority: Priority | None = None
    today: bool | None = None

    @model_validator(mode="after")
    def check_fields(self) -> "TodoUpdate":
        if not self.model_fields_set:
            raise ValueError("변경할 필드가 하나 이상 필요합니다.")
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} 값은 null일 수 없습니다.")
        return self

    def changes(self) -> dict:
        """요청에 실제로 들어온 필드만 돌려준다."""
        return self.model_dump(include=self.model_fields_set)


class Todo(BaseModel):
    """저장소와 API 응답에 쓰는 할 일 (db-schema.md의 todos 행)."""

    id: UUID
    text: str
    done: bool
    priority: Priority
    today: bool
    created_at: datetime
    updated_at: datetime
