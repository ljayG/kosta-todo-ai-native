import { useEffect, useRef, useState } from 'react'
import { PRIORITIES } from '../constants.js'
import ClearButton from './ClearButton.jsx'
import DueBadge from './DueBadge.jsx'
import DueDateField from './DueDateField.jsx'
import PriorityBadge from './PriorityBadge.jsx'

// 작업 카드: 완료 체크, 내용, 우선순위 배지, 오늘 표시, 마감일, 수정/삭제
// busy: 이 작업의 서버 요청이 진행 중. 포커스를 잃지 않도록 disabled 대신
// aria-disabled로 표시하고 조작을 무시한다.
export default function TaskCard({ todo, busy = false, onToggle, onUpdate, onDelete }) {
  const [isEditing, setIsEditing] = useState(false)
  const [draft, setDraft] = useState(todo.text)
  const [draftPriority, setDraftPriority] = useState(todo.priority)
  const [draftToday, setDraftToday] = useState(todo.today)
  const [draftDue, setDraftDue] = useState(todo.dueDate ?? '') // '' = 마감일 없음
  const editRef = useRef(null)
  const editBtnRef = useRef(null)
  const returnFocus = useRef(false)

  // 수정을 마치면 포커스를 "수정" 버튼으로 되돌린다
  useEffect(() => {
    if (!isEditing && returnFocus.current) {
      editBtnRef.current?.focus()
      returnFocus.current = false
    }
  }, [isEditing])

  const startEdit = () => {
    setDraft(todo.text)
    setDraftPriority(todo.priority)
    setDraftToday(todo.today)
    setDraftDue(todo.dueDate ?? '')
    setIsEditing(true)
  }

  // 서버 저장에 성공했을 때만 수정 모드를 닫는다. 실패하면 입력한 값을 유지한다
  const save = async () => {
    const text = draft.trim()
    if (!text || busy) return
    const ok = await onUpdate(todo.id, {
      text,
      priority: draftPriority,
      today: draftToday,
      dueDate: draftDue || null, // 비우면 마감일 지우기
    })
    if (!ok) return
    returnFocus.current = true
    setIsEditing(false)
  }

  const cancel = () => {
    returnFocus.current = true
    setIsEditing(false)
  }

  const checkboxId = `todo-${todo.id}`

  return (
    <li
      className={`task task--${todo.priority} ${todo.done ? 'is-done' : ''} ${isEditing ? 'is-editing' : ''}`}
    >
      <input
        id={checkboxId}
        className="check"
        type="checkbox"
        checked={todo.done}
        onChange={() => !busy && onToggle(todo.id)}
        aria-disabled={busy || undefined}
        aria-label={`"${todo.text}" 완료`}
      />

      {isEditing ? (
        <div className="task__edit">
          <div className="field field--sm">
            <input
              ref={editRef}
              className="field__input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                // preventDefault: 포커스가 "수정" 버튼으로 돌아간 뒤 같은 Enter가
                // 버튼 클릭으로 이어져 수정 모드가 다시 열리는 것을 막는다
                if (e.key === 'Enter') {
                  e.preventDefault()
                  save()
                }
                if (e.key === 'Escape') {
                  e.preventDefault()
                  cancel()
                }
              }}
              aria-label="할 일 수정"
              maxLength={200}
              autoFocus
            />
            {draft && (
              <ClearButton
                onClear={() => {
                  setDraft('')
                  editRef.current?.focus()
                }}
              />
            )}
          </div>
          <div className="task__edit-options">
            <label className="select">
              <span className="sr-only">우선순위</span>
              <select
                value={draftPriority}
                onChange={(e) => setDraftPriority(e.target.value)}
                onKeyDown={(e) => e.key === 'Escape' && cancel()}
              >
                {PRIORITIES.map((p) => (
                  <option key={p.value} value={p.value}>
                    우선순위 {p.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={draftToday}
                onChange={(e) => setDraftToday(e.target.checked)}
              />
              <span>오늘 할 일</span>
            </label>
            <DueDateField
              id={`due-${todo.id}`}
              value={draftDue}
              onChange={setDraftDue}
              onKeyDown={(e) => {
                // 텍스트 입력창과 같은 키 동작 (Enter 저장, Esc 취소)
                if (e.key === 'Enter') {
                  e.preventDefault()
                  save()
                }
                if (e.key === 'Escape') {
                  e.preventDefault()
                  cancel()
                }
              }}
            />
          </div>
        </div>
      ) : (
        <div className="task__body">
          <label htmlFor={checkboxId} className="task__text">
            {todo.text}
          </label>
          <div className="task__meta">
            <PriorityBadge priority={todo.priority} />
            {todo.today && <span className="tag">오늘</span>}
            <DueBadge dueDate={todo.dueDate} done={todo.done} />
          </div>
        </div>
      )}

      <div className="task__actions">
        {isEditing ? (
          <>
            <button
              type="button"
              className="btn btn--primary btn--sm"
              onClick={save}
              disabled={!draft.trim()}
              aria-disabled={busy || undefined}
            >
              {busy ? '저장 중' : '저장'}
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={cancel}>
              취소
            </button>
          </>
        ) : (
          <>
            <button
              ref={editBtnRef}
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => !busy && startEdit()}
              aria-disabled={busy || undefined}
              aria-label={`"${todo.text}" 수정`}
            >
              수정
            </button>
            <button
              type="button"
              className="btn btn--danger btn--sm"
              onClick={() => !busy && onDelete(todo.id)}
              aria-disabled={busy || undefined}
              aria-label={`"${todo.text}" 삭제`}
            >
              삭제
            </button>
          </>
        )}
      </div>
    </li>
  )
}
