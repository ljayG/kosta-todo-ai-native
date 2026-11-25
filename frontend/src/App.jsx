import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from './api/todos.js'
import { FILTERS, PRIORITY_RANK } from './constants.js'
import EmptyState from './components/EmptyState.jsx'
import FilterTabs from './components/FilterTabs.jsx'
import Notice from './components/Notice.jsx'
import ProgressRing from './components/ProgressRing.jsx'
import StatCard from './components/StatCard.jsx'
import TaskCard from './components/TaskCard.jsx'
import TaskComposer from './components/TaskComposer.jsx'
import TodayPanel from './components/TodayPanel.jsx'

const EMPTY_COPY = {
  all: { title: '아직 할 일이 없습니다', hint: '입력창에 첫 할 일을 적고 Enter를 누르세요.' },
  active: { title: '진행 중인 작업이 없습니다', hint: '모든 작업을 끝냈습니다. 새 할 일을 추가해 보세요.' },
  done: { title: '완료한 작업이 없습니다', hint: '작업 왼쪽의 체크박스를 누르면 여기로 옮겨집니다.' },
}

export default function App() {
  // todo: { id, text, done, priority: 'high'|'medium'|'low', today: boolean, dueDate: 'YYYY-MM-DD'|null }
  const [todos, setTodos] = useState([])
  const [filter, setFilter] = useState('all')
  const [loadState, setLoadState] = useState('loading') // loading | ready | error
  const [pendingIds, setPendingIds] = useState(() => new Set()) // 요청 중인 할 일 id
  const [notice, setNotice] = useState(null) // { tone, message }
  const inputRef = useRef(null)

  // 처음 불러오기 (FR-13, FR-14)
  const load = useCallback(async () => {
    setLoadState('loading')
    try {
      setTodos(await api.listTodos())
      setLoadState('ready')
    } catch {
      setLoadState('error')
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const setPending = (id, on) =>
    setPendingIds((prev) => {
      const next = new Set(prev)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })

  const removeLocal = (id) => setTodos((prev) => prev.filter((t) => t.id !== id))

  // 변경 실패 처리. 404는 다른 곳에서 이미 삭제된 경우라 화면에서도 지운다 (AC-22)
  // 결과: 'removed'(404로 화면에서 제거) | 'failed'
  const handleError = (err, action, id) => {
    if (err instanceof api.ApiError && err.status === 404 && id !== 'new') {
      removeLocal(id)
      setNotice({ tone: 'info', message: '이미 삭제된 할 일이라 목록에서 제거했습니다.' })
      return 'removed'
    }
    setNotice({ tone: 'error', message: `할 일을 ${action}하지 못했습니다. ${err.message} 다시 시도하세요.` })
    return 'failed'
  }

  // 서버 응답을 받은 뒤 화면에 반영한다 (비관적 업데이트, D-04)
  // 결과: 'ok' | 'removed' | 'failed'
  const mutate = async (id, action, call, apply) => {
    setPending(id, true)
    try {
      apply(await call())
      setNotice(null)
      return 'ok'
    } catch (err) {
      return handleError(err, action, id)
    } finally {
      setPending(id, false)
    }
  }

  const total = todos.length
  const doneCount = todos.filter((t) => t.done).length
  const activeCount = total - doneCount
  const percent = total ? Math.round((doneCount / total) * 100) : 0

  const visible = todos.filter((t) =>
    filter === 'active' ? !t.done : filter === 'done' ? t.done : true,
  )
  const todayTasks = todos
    .filter((t) => t.today)
    .sort((a, b) => a.done - b.done || PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority])

  const replaceLocal = (saved) => setTodos((prev) => prev.map((t) => (t.id === saved.id ? saved : t)))

  // 콜백 이름과 인자는 기존과 같고, 성공 여부(Promise<boolean>)를 돌려준다
  const addTodo = async ({ text, priority, today, dueDate }) =>
    (await mutate('new', '추가', () => api.createTodo({ text, priority, today, dueDate }), (saved) =>
      setTodos((prev) => [...prev, saved]),
    )) === 'ok'

  const toggleTodo = async (id) => {
    const current = todos.find((t) => t.id === id)
    if (!current) return false
    return (await mutate(id, '변경', () => api.updateTodo(id, { done: !current.done }), replaceLocal)) === 'ok'
  }

  const updateTodo = async (id, changes) =>
    (await mutate(id, '수정', () => api.updateTodo(id, changes), replaceLocal)) === 'ok'

  const deleteTodo = async (id) => {
    const result = await mutate(id, '삭제', () => api.deleteTodo(id), () => removeLocal(id))
    // 카드가 사라졌으면(성공 또는 404) 포커스를 입력창으로 옮긴다. 실패하면 삭제 버튼에 그대로 둔다
    if (result !== 'failed') inputRef.current?.focus()
    return result === 'ok'
  }

  const today = new Date().toLocaleDateString('ko-KR', {
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  })

  const activeTabId = `tab-${filter}`
  const filterLabel = FILTERS.find((f) => f.value === filter).label

  return (
    <div className="page">
      <header className="masthead">
        <h1 className="masthead__title">My ToDo</h1>
        <p className="masthead__date">{today}</p>
      </header>

      <main className="layout">
        {/* DOM 순서 = 모바일 순서(입력 → 요약 → 목록). 데스크톱은 grid-area로 2열 배치 */}
        <section className="area-composer" aria-label="할 일 추가">
          <TaskComposer onAdd={addTodo} inputRef={inputRef} adding={pendingIds.has('new')} />
          {notice && (
            <Notice tone={notice.tone} message={notice.message} onClose={() => setNotice(null)} />
          )}
        </section>

        <aside className="summary" aria-label="오늘 요약">
          <div className="summary__ring">
            <ProgressRing percent={percent} done={doneCount} total={total} />
          </div>

          <dl className="stats">
            <StatCard label="전체 작업" value={total} />
            <StatCard label="완료" value={doneCount} tone="done" />
            <StatCard label="미완료" value={activeCount} tone={activeCount ? 'active' : 'default'} />
          </dl>

          <TodayPanel tasks={todayTasks} onToggle={toggleTodo} pendingIds={pendingIds} />
        </aside>

        <section className="work" aria-labelledby="list-title">
          <div className="work__bar">
            <h2 id="list-title" className="section-title">
              작업 목록
            </h2>
            <FilterTabs
              value={filter}
              onChange={setFilter}
              panelId="task-panel"
              counts={{ all: total, active: activeCount, done: doneCount }}
            />
          </div>

          <div
            id="task-panel"
            role="tabpanel"
            aria-labelledby={activeTabId}
            aria-busy={loadState === 'loading'}
          >
            {loadState === 'loading' ? (
              <p className="loading">할 일을 불러오는 중입니다.</p>
            ) : loadState === 'error' ? (
              <EmptyState
                title="할 일을 불러오지 못했습니다"
                hint="서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
                actionLabel="다시 시도"
                onAction={load}
              />
            ) : visible.length === 0 ? (
              <EmptyState
                title={EMPTY_COPY[filter].title}
                hint={total === 0 ? EMPTY_COPY.all.hint : EMPTY_COPY[filter].hint}
                actionLabel={total === 0 || filter === 'active' ? '할 일 추가하기' : undefined}
                onAction={() => inputRef.current?.focus()}
              />
            ) : (
              <ul className="tasks" aria-label={`${filterLabel} 작업`}>
                {visible.map((todo) => (
                  <TaskCard
                    key={todo.id}
                    todo={todo}
                    busy={pendingIds.has(todo.id)}
                    onToggle={toggleTodo}
                    onUpdate={updateTodo}
                    onDelete={deleteTodo}
                  />
                ))}
              </ul>
            )}
          </div>
        </section>
      </main>
    </div>
  )
}
