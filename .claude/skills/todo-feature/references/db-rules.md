# DB 규칙
- 기존 `todos` 데이터와 마감일을 보존한다.
- `category` 컬럼을 추가하고 기존 데이터의 기본값을 `personal`로 설정한다.
- 허용값: `work`, `personal`, `study`.
- 스키마 변경은 기존 `supabase/schema.sql` 및 프로젝트 마이그레이션 방식에 맞춘다.
