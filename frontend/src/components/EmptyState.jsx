// 작업이 없을 때 보여 주는 화면. action이 있으면 다음 행동 버튼을 함께 보여 준다.
export default function EmptyState({ title, hint, actionLabel, onAction }) {
  return (
    <div className="empty">
      <svg className="empty__art" viewBox="0 0 96 72" width="96" height="72" aria-hidden="true">
        <rect x="14" y="6" width="68" height="60" rx="8" className="empty__paper" />
        <rect x="24" y="20" width="10" height="10" rx="3" className="empty__box" />
        <path d="M40 25h30" className="empty__line" />
        <rect x="24" y="38" width="10" height="10" rx="3" className="empty__box" />
        <path d="M40 43h22" className="empty__line" />
      </svg>
      <p className="empty__title">{title}</p>
      {hint && <p className="empty__hint">{hint}</p>}
      {actionLabel && (
        <button type="button" className="btn btn--ghost" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  )
}
