// 입력창 안쪽의 "입력 내용 지우기" 버튼
export default function ClearButton({ onClear }) {
  return (
    <button type="button" className="clear-btn" onClick={onClear} aria-label="입력 내용 지우기">
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
        <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </button>
  )
}
