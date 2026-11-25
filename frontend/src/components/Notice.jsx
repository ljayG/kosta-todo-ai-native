// 변경 실패나 안내를 보여 주는 띠 (tone: error | info)
export default function Notice({ tone = 'error', message, onClose }) {
  return (
    <div className={`notice notice--${tone}`} role="alert">
      <p className="notice__text">{message}</p>
      <button type="button" className="notice__close" onClick={onClose} aria-label="알림 닫기">
        <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
          <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  )
}
