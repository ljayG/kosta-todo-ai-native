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

// 화면에서 쓰는 형태로 변환 (created_at, updated_at은 화면에서 쓰지 않음)
const toTodo = ({ id, text, done, priority, today }) => ({ id, text, done, priority, today })

export const listTodos = async () => (await request('/api/todos')).map(toTodo)

export const createTodo = async ({ text, priority, today }) =>
  toTodo(await request('/api/todos', { method: 'POST', body: { text, priority, today } }))

export const updateTodo = async (id, changes) =>
  toTodo(await request(`/api/todos/${id}`, { method: 'PATCH', body: changes }))

export const deleteTodo = (id) => request(`/api/todos/${id}`, { method: 'DELETE' })
