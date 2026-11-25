# DB 스키마

| 항목 | 내용 |
| --- | --- |
| 문서 버전 | 0.2 (초안). 0.2: `due_date` 컬럼 추가 (FR-15) |
| DB | Supabase PostgreSQL |
| 관련 요구사항 | FR-01~FR-07, FR-13, FR-15, NFR-05 ([PRD.md](PRD.md)) |
| 마이그레이션 위치 | `supabase/migrations/` (미작성, [TASKS.md](TASKS.md)의 T-02) |

## 테이블: `public.todos`

| 컬럼 | 타입 | 제약 / 기본값 | 관련 요구사항 |
| --- | --- | --- | --- |
| `id` | `uuid` | PK, `default gen_random_uuid()` | FR-13 |
| `text` | `text` | `not null`, `check (char_length(btrim(text)) between 1 and 200)` | FR-01, FR-04 |
| `done` | `boolean` | `not null default false` | FR-03 |
| `priority` | `text` | `not null default 'medium'`, `check (priority in ('high','medium','low'))` | FR-06 |
| `today` | `boolean` | `not null default false` | FR-07 |
| `due_date` | `date` | `null` 허용, 기본값 없음(`null` = 마감일 없음) | FR-15 |
| `created_at` | `timestamptz` | `not null default now()` | FR-02 |
| `updated_at` | `timestamptz` | `not null default now()`, 수정 시 트리거로 갱신 | FR-04 |

- `priority`를 PostgreSQL enum이 아니라 `text`와 `check`로 둔 이유: 값을 추가하거나 바꿀 때 마이그레이션이 단순합니다.
- `text`의 앞뒤 공백 제거는 API가 합니다. DB의 `check`는 마지막 안전장치입니다.

## 인덱스

| 이름 | 정의 | 용도 |
| --- | --- | --- |
| `todos_created_at_idx` | `(created_at, id)` | 목록 정렬 (API-02) |

## 보안 (NFR-05)

- **RLS:** `todos` 테이블에 RLS를 켜고(`enable row level security`) 정책은 만들지 않습니다. 그러면 `anon`과 `authenticated` 키로는 읽기와 쓰기가 모두 막힙니다.
- **백엔드 접근:** FastAPI는 RLS를 우회하는 `service_role` 키로 접근합니다. 이 키는 `backend/.env`와 Vercel 환경 변수에만 둡니다.
- **인증을 도입할 때(D-01):** `user_id uuid references auth.users` 컬럼과 사용자별 RLS 정책을 추가합니다.

## 마이그레이션 초안

T-02에서 `supabase/migrations/<타임스탬프>_create_todos.sql`로 만듭니다.

```sql
create table public.todos (
  id          uuid primary key default gen_random_uuid(),
  text        text not null check (char_length(btrim(text)) between 1 and 200),
  done        boolean not null default false,
  priority    text not null default 'medium' check (priority in ('high', 'medium', 'low')),
  today       boolean not null default false,
  due_date    date,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index todos_created_at_idx on public.todos (created_at, id);

create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger todos_set_updated_at
  before update on public.todos
  for each row execute function public.set_updated_at();

alter table public.todos enable row level security;
```

### 마감일 추가 마이그레이션 (T-14)

위 초안을 아직 적용하지 않았다면 초안에 포함된 `due_date` 컬럼으로 충분합니다. 이미 `todos` 테이블을 만든 뒤라면 아래 마이그레이션을 따로 추가합니다. **둘 다 승인 전에는 실행하지 않습니다.** 현재 백엔드는 In-Memory 저장소라서 DB 변경 없이 동작합니다.

```sql
alter table public.todos add column due_date date;
```

- `date` 타입이라 시간대 변환이 없습니다. "오늘"인지는 화면에서 사용자 현지 날짜로 판단합니다(FR-15).
- 마감일 기준 정렬·필터는 범위 밖이므로 인덱스를 추가하지 않습니다.

## 프론트엔드 상태와의 대응

현재 프론트엔드의 todo 형태는 `{ id, text, done, priority, today, dueDate }`입니다. `due_date` ↔ `dueDate` 변환은 `frontend/src/api/todos.js`에서만 합니다. `created_at`과 `updated_at`은 프론트엔드에서 쓰지 않아도 됩니다(정렬은 서버가 처리).
