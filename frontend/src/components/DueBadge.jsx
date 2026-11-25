import { describeDue } from '../dates.js'

// 마감일 배지 (FR-15). 마감일이 없으면 아무것도 그리지 않는다.
export default function DueBadge({ dueDate, done }) {
  const due = describeDue(dueDate, done)
  if (!due) return null
  return (
    <span className={`due due--${due.tone}`}>
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
        <rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      {due.label}
    </span>
  )
}
