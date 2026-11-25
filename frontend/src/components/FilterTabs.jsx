import { useRef } from 'react'
import { FILTERS } from '../constants.js'

// 전체 / 진행 중 / 완료 필터 탭 (WAI-ARIA tabs 패턴: ←→ Home End 키 이동)
export default function FilterTabs({ value, counts, onChange, panelId }) {
  const refs = useRef([])

  const onKeyDown = (e, index) => {
    let next = null
    if (e.key === 'ArrowRight') next = (index + 1) % FILTERS.length
    if (e.key === 'ArrowLeft') next = (index - 1 + FILTERS.length) % FILTERS.length
    if (e.key === 'Home') next = 0
    if (e.key === 'End') next = FILTERS.length - 1
    if (next === null) return
    e.preventDefault()
    onChange(FILTERS[next].value)
    refs.current[next]?.focus()
  }

  return (
    <div className="tabs" role="tablist" aria-label="작업 필터">
      {FILTERS.map((f, i) => {
        const selected = f.value === value
        return (
          <button
            key={f.value}
            ref={(el) => (refs.current[i] = el)}
            id={`tab-${f.value}`}
            type="button"
            role="tab"
            className="tab"
            aria-selected={selected}
            aria-controls={panelId}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(f.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {f.label}
            <span className="tab__count">{counts[f.value]}</span>
          </button>
        )
      })}
    </div>
  )
}
