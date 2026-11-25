"""API 테스트. 각 테스트 이름 앞의 AC 번호는 docs/acceptance-criteria.md를 가리킨다."""

from uuid import UUID, uuid4

import pytest

TODO_FIELDS = {"id", "text", "done", "priority", "today", "due_date", "created_at", "updated_at"}


# ---------- API-01 ----------
def test_ac30_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


# ---------- API-03 등록 ----------
def test_ac31_create_trims_text_and_applies_defaults(client):
    res = client.post("/api/todos", json={"text": "  보고서  "})
    assert res.status_code == 201
    body = res.json()
    assert set(body) == TODO_FIELDS
    assert body["text"] == "보고서"
    assert body["priority"] == "medium"
    assert body["today"] is False
    assert body["done"] is False
    assert body["due_date"] is None
    UUID(body["id"])  # 서버가 만든 UUID
    assert body["created_at"] == body["updated_at"]


def test_create_with_all_fields(client):
    res = client.post("/api/todos", json={"text": "보고서", "priority": "high", "today": True})
    assert res.status_code == 201
    assert res.json()["priority"] == "high"
    assert res.json()["today"] is True


def test_create_accepts_200_chars(client):
    res = client.post("/api/todos", json={"text": "가" * 200})
    assert res.status_code == 201


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "   "},
        {"text": ""},
        {"text": "가" * 201},
        {"text": "보고서", "priority": "urgent"},
        {"text": "보고서", "done": True},
        {"text": "보고서", "id": str(uuid4())},
        {"text": "보고서", "created_at": "2026-01-01T00:00:00Z"},
        {"priority": "high"},
        {"text": None},
    ],
    ids=["공백만", "빈문자열", "201자", "잘못된priority", "done포함", "id포함", "시각포함", "text없음", "text-null"],
)
def test_ac32_create_validation_errors(client, payload):
    res = client.post("/api/todos", json=payload)
    assert res.status_code == 422
    assert "detail" in res.json()
    assert client.get("/api/todos").json() == []


# ---------- API-02 목록 ----------
def test_list_empty(client):
    res = client.get("/api/todos")
    assert res.status_code == 200
    assert res.json() == []


def test_ac33_list_in_creation_order(client, make_todo):
    for text in ["첫째", "둘째", "셋째"]:
        make_todo(text)
    res = client.get("/api/todos")
    assert [t["text"] for t in res.json()] == ["첫째", "둘째", "셋째"]


def test_list_order_unchanged_after_update(client, make_todo):
    first = make_todo("첫째")
    make_todo("둘째")
    client.patch(f"/api/todos/{first['id']}", json={"text": "첫째(수정)"})
    assert [t["text"] for t in client.get("/api/todos").json()] == ["첫째(수정)", "둘째"]


# ---------- API-04 수정 ----------
def test_ac34_toggle_done_updates_timestamp(client, make_todo):
    todo = make_todo("보고서")
    res = client.patch(f"/api/todos/{todo['id']}", json={"done": True})
    assert res.status_code == 200
    body = res.json()
    assert body["done"] is True
    assert body["updated_at"] > todo["updated_at"]
    assert body["created_at"] == todo["created_at"]


def test_patch_changes_only_given_fields(client, make_todo):
    todo = make_todo("보고서", priority="low", today=True)
    res = client.patch(f"/api/todos/{todo['id']}", json={"text": "  주간 보고서 ", "priority": "high"})
    body = res.json()
    assert body["text"] == "주간 보고서"
    assert body["priority"] == "high"
    assert body["today"] is True  # 보내지 않은 필드는 유지
    assert body["done"] is False


def test_patch_is_persisted(client, make_todo):
    todo = make_todo("보고서")
    client.patch(f"/api/todos/{todo['id']}", json={"today": True})
    assert client.get("/api/todos").json()[0]["today"] is True


@pytest.mark.parametrize(
    "payload",
    [{}, {"text": None}, {"done": None}, {"foo": 1}, {"text": "  "}, {"priority": "urgent"}, {"id": str(uuid4())}],
    ids=["빈객체", "text-null", "done-null", "알수없는필드", "공백text", "잘못된priority", "id변경"],
)
def test_ac35_patch_validation_errors(client, make_todo, payload):
    todo = make_todo("보고서")
    res = client.patch(f"/api/todos/{todo['id']}", json=payload)
    assert res.status_code == 422
    assert client.get("/api/todos").json()[0] == todo  # 바뀌지 않음


# ---------- 404 / 잘못된 id ----------
@pytest.mark.parametrize("method", ["patch", "delete"])
def test_ac36_unknown_id_returns_404(client, method):
    kwargs = {"json": {"done": True}} if method == "patch" else {}
    res = getattr(client, method)(f"/api/todos/{uuid4()}", **kwargs)
    assert res.status_code == 404
    assert res.json() == {"detail": "할 일을 찾을 수 없습니다."}


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_invalid_uuid_returns_422(client, method):
    kwargs = {"json": {"done": True}} if method == "patch" else {}
    res = getattr(client, method)("/api/todos/not-a-uuid", **kwargs)
    assert res.status_code == 422


# ---------- API-05 삭제 ----------
def test_ac37_delete(client, make_todo):
    keep = make_todo("남길 것")
    gone = make_todo("지울 것")
    res = client.delete(f"/api/todos/{gone['id']}")
    assert res.status_code == 204
    assert res.content == b""
    assert [t["id"] for t in client.get("/api/todos").json()] == [keep["id"]]


def test_delete_twice_returns_404(client, make_todo):
    todo = make_todo()
    assert client.delete(f"/api/todos/{todo['id']}").status_code == 204
    assert client.delete(f"/api/todos/{todo['id']}").status_code == 404


# ---------- 공통 ----------
def test_cors_allows_frontend_origin(client):
    res = client.options(
        "/api/todos",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PATCH"},
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_other_origin(client):
    res = client.get("/api/todos", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in res.headers


def test_internal_error_hides_details(make_todo):
    from fastapi.testclient import TestClient

    from app.dependencies import get_repository
    from app.main import app

    class BrokenRepo:
        def list(self):
            raise RuntimeError("DB 비밀번호가 틀림")

    app.dependency_overrides[get_repository] = lambda: BrokenRepo()
    with TestClient(app, raise_server_exceptions=False) as c:
        res = c.get("/api/todos")
    assert res.status_code == 500
    assert res.json() == {"detail": "서버 오류가 발생했습니다."}
    assert "비밀번호" not in res.text


# ---------- 마감일 (FR-15) ----------
def test_ac39_create_with_due_date(client):
    res = client.post("/api/todos", json={"text": "보고서", "due_date": "2026-11-28"})
    assert res.status_code == 201
    assert res.json()["due_date"] == "2026-11-28"
    assert client.get("/api/todos").json()[0]["due_date"] == "2026-11-28"


def test_ac39_create_with_null_due_date(client):
    res = client.post("/api/todos", json={"text": "보고서", "due_date": None})
    assert res.status_code == 201
    assert res.json()["due_date"] is None


def test_due_date_in_past_is_allowed(client):
    res = client.post("/api/todos", json={"text": "지난 일", "due_date": "2020-01-01"})
    assert res.status_code == 201


@pytest.mark.parametrize(
    "due_date",
    ["2026-02-30", "2026-13-01", "28-11-2026", "2026/11/28", "2026-11-28T10:00:00", "2026-11-28 10:00", "", 123, 0, True, []],
    ids=["없는날짜", "13월", "일월년", "슬래시", "시각포함", "공백시각", "빈문자열", "숫자", "0", "불리언", "배열"],
)
def test_ac50_invalid_due_date(client, make_todo, due_date):
    res = client.post("/api/todos", json={"text": "보고서", "due_date": due_date})
    assert res.status_code == 422
    todo = make_todo("기존")
    res = client.patch(f"/api/todos/{todo['id']}", json={"due_date": due_date})
    assert res.status_code == 422
    assert client.get("/api/todos").json()[0]["due_date"] is None


def test_ac51_patch_set_and_clear_due_date(client, make_todo):
    todo = make_todo("보고서")
    res = client.patch(f"/api/todos/{todo['id']}", json={"due_date": "2026-12-01"})
    assert res.status_code == 200
    assert res.json()["due_date"] == "2026-12-01"
    res = client.patch(f"/api/todos/{todo['id']}", json={"due_date": None})
    assert res.status_code == 200
    assert res.json()["due_date"] is None
    assert client.get("/api/todos").json()[0]["due_date"] is None


def test_ac52_other_patch_keeps_due_date(client, make_todo):
    todo = make_todo("보고서", due_date="2026-11-28")
    res = client.patch(f"/api/todos/{todo['id']}", json={"done": True})
    assert res.json()["due_date"] == "2026-11-28"
    res = client.patch(f"/api/todos/{todo['id']}", json={"text": "주간 보고서", "priority": "high"})
    assert res.json()["due_date"] == "2026-11-28"


def test_null_still_rejected_for_other_fields_with_due_date(client, make_todo):
    """due_date만 null 예외다. 다른 필드의 null은 함께 보내도 422."""
    todo = make_todo("보고서")
    res = client.patch(f"/api/todos/{todo['id']}", json={"due_date": None, "priority": None})
    assert res.status_code == 422


def test_existing_clients_without_due_date_still_work(client):
    """기존 API 계약 유지: due_date를 모르는 클라이언트의 요청도 그대로 동작한다."""
    res = client.post("/api/todos", json={"text": "보고서", "priority": "low", "today": True})
    assert res.status_code == 201
    res = client.patch(f"/api/todos/{res.json()['id']}", json={"done": True})
    assert res.status_code == 200
