"""요청/응답 모델 (docs/api-spec.md의 Todo 객체)."""

import re
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints, model_validator

Priority = Literal["high", "medium", "low"]

# 카테고리: 업무 / 개인 / 학습 (FR-16). 기본값은 personal
Category = Literal["work", "personal", "study"]
DEFAULT_CATEGORY: Category = "personal"

# 앞뒤 공백 제거 후 1~200자 (FR-01, FR-04)
TodoText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

_DATE_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _require_date_string(value: object) -> object:
    """마감일은 "YYYY-MM-DD" 문자열만 받는다 (FR-15).

    Pydantic 기본 동작은 숫자(유닉스 시각)나 시각이 붙은 문자열도 날짜로 바꾸므로
    파싱 전에 형식을 확인한다. 실제로 없는 날짜(2026-02-30)는 이후 date 파싱에서 거부된다.
    """
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and _DATE_FORMAT.match(value):
        return value
    raise ValueError("마감일은 YYYY-MM-DD 형식이어야 합니다.")


# 시각과 시간대가 없는 마감일
DueDate = Annotated[date, BeforeValidator(_require_date_string)]

# PATCH에서 null을 받는 필드 (null = 값 지우기)
NULLABLE_ON_UPDATE = {"due_date"}


class TodoCreate(BaseModel):
    """API-03 요청. done, id, 시각 필드 등 알 수 없는 필드는 거부한다."""

    model_config = ConfigDict(extra="forbid")

    text: TodoText
    priority: Priority = "medium"
    today: bool = False
    category: Category = DEFAULT_CATEGORY
    due_date: DueDate | None = None


class TodoUpdate(BaseModel):
    """API-04 요청. 하나 이상의 필드가 필요하며 null 값은 허용하지 않는다.

    예외: due_date는 null을 받으며 마감일을 지운다는 뜻이다.
    """

    model_config = ConfigDict(extra="forbid")

    text: TodoText | None = None
    done: bool | None = None
    priority: Priority | None = None
    today: bool | None = None
    category: Category | None = None
    due_date: DueDate | None = None

    @model_validator(mode="after")
    def check_fields(self) -> "TodoUpdate":
        if not self.model_fields_set:
            raise ValueError("변경할 필드가 하나 이상 필요합니다.")
        for name in self.model_fields_set - NULLABLE_ON_UPDATE:
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
    category: Category = DEFAULT_CATEGORY
    due_date: date | None
    created_at: datetime
    updated_at: datetime
