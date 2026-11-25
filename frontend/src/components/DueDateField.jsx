// 마감일 입력: 보이는 라벨 + 브라우저 기본 날짜 입력 + 지우기 버튼 (FR-15)
// value는 'YYYY-MM-DD' 또는 '' (마감일 없음)
export default function DueDateField({ id, value, onChange, onKeyDown }) {
  return (
    <div className="due-field">
      <label htmlFor={id} className="due-field__label">
        마감일
      </label>
      <input
        id={id}
        type="date"
        className="due-field__input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
      />
      {value && (
        <button type="button" className="due-field__clear" onClick={() => onChange('')} aria-label="마감일 지우기">
          지우기
        </button>
      )}
    </div>
  )
}
