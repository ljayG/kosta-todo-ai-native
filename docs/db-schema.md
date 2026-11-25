# DB 스키마

| 항목 | 내용 |
| --- | --- |
| 문서 버전 | 0.1 (초안) |
| DB | Supabase PostgreSQL |
| 관련 요구사항 | FR-01~FR-07, FR-13, NFR-05 ([PRD.md](PRD.md)) |
| 마이그레이션 위치 | `supabase/migrations/` (미작성, [TASKS.md](TASKS.md)의 T-02) |

## 테이블: `public.todos`

| 컬럼 | 타입 | 제약 / 기본값 | 관련 요구사항 |
| --- | --- | --- | --- |
| `id` | `uuid` | PK, `default gen_random_uuid()` | FR-13 |
| `text` | `text` | `not null`, `check (char_length(btrim(text)) between 1 and 200)` | FR-01, FR-04 |
| `done` | `boolean` | `not null default false` | FR-03 |
| `priority` | `text` | `not null default 'medium'`, `check (priority in ('high','medium','low'))` | FR-06 |
| `today` | `boolean` | `not null default false` | FR-07 |
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

## 프론트엔드 상태와의 대응

현재 프론트엔드의 todo 형태 `{ id, text, done, priority, today }`는 이 테이블의 컬럼과 이름이 같습니다. `created_at`과 `updated_at`은 프론트엔드에서 쓰지 않아도 됩니다(정렬은 서버가 처리).
