import { PRIORITY_LABEL } from '../constants.js'

// 오늘의 작업: "오늘 할 일"로 표시한 작업을 미완료 → 우선순위 순으로 보여 준다
export default function TodayPanel({ tasks, onToggle, pendingIds }) {
  const left = tasks.filter((t) => !t.done).length

  return (
    <section className="today" aria-labelledby="today-title">
      <div className="today__head">
        <h2 id="today-title" className="section-title">
          오늘의 작업
        </h2>
        <span className="today__count">{tasks.length ? `${left}개 남음` : ''}</span>
      </div>

      {tasks.length === 0 ? (
        <p className="today__empty">작업을 추가할 때 "오늘 할 일"을 켜면 여기에 모입니다.</p>
      ) : (
        <ul className="today__list">
          {tasks.map((t) => (
            <li key={t.id} className={`today__item ${t.done ? 'is-done' : ''}`}>
              <input
                id={`today-${t.id}`}
                type="checkbox"
                className="check check--sm"
                checked={t.done}
                onChange={() => !pendingIds?.has(t.id) && onToggle(t.id)}
                aria-disabled={pendingIds?.has(t.id) || undefined}
              />
              <label htmlFor={`today-${t.id}`}>{t.text}</label>
              <span className={`dot dot--${t.priority}`} title={`우선순위 ${PRIORITY_LABEL[t.priority]}`}>
                <span className="sr-only">우선순위 {PRIORITY_LABEL[t.priority]}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
