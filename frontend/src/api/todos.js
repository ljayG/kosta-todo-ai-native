// FastAPI 호출 모음 (docs/api-spec.md API-02~05)

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.name = 'ApiError'
    this.status = status // 0이면 네트워크 오류
  }
}

async function request(path, { method = 'GET', body } = {}) {
  let res
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, '서버에 연결할 수 없습니다.')
  }

  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : '요청을 처리하지 못했습니다.'
    throw new ApiError(res.status, detail)
  }
  return data
}

// 서버(snake_case) → 화면(camelCase). created_at, updated_at은 화면에서 쓰지 않음
const toTodo = ({ id, text, done, priority, today, category, due_date }) => ({
  id,
  text,
  done,
  priority,
  today,
  category: category ?? 'personal',
  dueDate: due_date ?? null,
})

// 화면 → 서버. 들어온 필드만 보낸다 (PATCH는 일부 필드만 보냄)
const FIELD_TO_API = { dueDate: 'due_date' }
const toBody = (fields) =>
  Object.fromEntries(
    Object.entries(fields)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => [FIELD_TO_API[k] ?? k, v]),
  )

// category를 주면 서버에서 거른 목록 (FR-16). 화면은 통계 때문에 전체 목록을 받아 직접 거른다
export const listTodos = async (category) =>
  (await request(category ? `/api/todos?category=${encodeURIComponent(category)}` : '/api/todos')).map(toTodo)

export const createTodo = async ({ text, priority, today, category, dueDate }) =>
  toTodo(
    await request('/api/todos', {
      method: 'POST',
      body: toBody({ text, priority, today, category, dueDate }),
    }),
  )

// changes.dueDate가 null이면 마감일을 지운다
export const updateTodo = async (id, changes) =>
  toTodo(await request(`/api/todos/${id}`, { method: 'PATCH', body: toBody(changes) }))

export const deleteTodo = (id) => request(`/api/todos/${id}`, { method: 'DELETE' })
