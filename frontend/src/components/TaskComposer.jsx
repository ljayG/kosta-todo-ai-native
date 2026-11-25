import { useEffect, useState } from 'react'
import { CATEGORIES, DEFAULT_CATEGORY, PRIORITIES } from '../constants.js'
import ClearButton from './ClearButton.jsx'
import DueDateField from './DueDateField.jsx'

// 새 할 일 입력 폼: 내용, 우선순위, 오늘 할 일 여부, 카테고리, 마감일
// adding: 등록 요청 중 여부. 실패하면 입력한 내용을 그대로 둔다 (AC-21)
// defaultCategory: 카테고리 필터가 선택되어 있으면 그 값 (새 할 일이 필터에 가려지지 않도록, FR-16)
export default function TaskComposer({ onAdd, inputRef, adding = false, defaultCategory = DEFAULT_CATEGORY }) {
  const [text, setText] = useState('')
  const [priority, setPriority] = useState('medium')
  const [today, setToday] = useState(false)
  const [dueDate, setDueDate] = useState('') // '' = 마감일 없음
  const [category, setCategory] = useState(defaultCategory)

  // 카테고리 필터를 바꾸면 등록 기본값도 따라간다
  useEffect(() => setCategory(defaultCategory), [defaultCategory])

  const submit = async (e) => {
    e.preventDefault()
    const value = text.trim()
    if (!value || adding) return
    const ok = await onAdd({ text: value, priority, today, category, dueDate: dueDate || null })
    if (ok) {
      setText('')
      setDueDate('')
    }
    inputRef.current?.focus()
  }

  return (
    <form className="composer" onSubmit={submit}>
      <div className="composer__main">
        <label htmlFor="new-todo" className="sr-only">
          새 할 일
        </label>
        <div className="field">
          <input
            id="new-todo"
            ref={inputRef}
            className="field__input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="할 일을 입력하세요"
            autoComplete="off"
            maxLength={200}
          />
          {text && (
            <ClearButton
              onClear={() => {
                setText('')
                inputRef.current?.focus()
              }}
            />
          )}
        </div>
        <button type="submit" className="btn btn--primary" disabled={!text.trim() || adding}>
          {adding ? '추가 중' : '추가'}
        </button>
      </div>

      <div className="composer__options">
        <fieldset className="segmented">
          <legend className="segmented__legend">우선순위</legend>
          {PRIORITIES.map((p) => (
            <label key={p.value} className={`segmented__item segmented__item--${p.value}`}>
              <input
                type="radio"
                name="new-priority"
                value={p.value}
                checked={priority === p.value}
                onChange={() => setPriority(p.value)}
              />
              <span>{p.label}</span>
            </label>
          ))}
        </fieldset>

        <label className="toggle">
          <input type="checkbox" checked={today} onChange={(e) => setToday(e.target.checked)} />
          <span>오늘 할 일</span>
        </label>

        <label className="field-inline">
          <span className="field-inline__label">카테고리</span>
          <select id="new-category" className="field-inline__select" value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>

        <DueDateField id="new-due" value={dueDate} onChange={setDueDate} />
      </div>
    </form>
  )
}
