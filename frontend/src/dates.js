// 마감일(YYYY-MM-DD, 시각 없음) 계산과 표시 문구 (FR-15)
// new Date('YYYY-MM-DD')는 UTC 자정으로 해석되어 한국 시간에서 날짜가 어긋날 수 있으므로
// 항상 현지 날짜의 연·월·일로만 다룬다.

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

const pad = (n) => String(n).padStart(2, '0')

// 현지 날짜를 YYYY-MM-DD로
export const toISODate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`

// YYYY-MM-DD를 현지 자정 Date로
const fromISODate = (iso) => {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

// a - b (일). 서머타임이 있어도 반올림으로 정확한 일 수를 얻는다
const diffDays = (a, b) => Math.round((fromISODate(a) - fromISODate(b)) / 86_400_000)

const formatDate = (iso, today) => {
  const d = fromISODate(iso)
  const year = d.getFullYear() !== fromISODate(today).getFullYear() ? `${d.getFullYear()}년 ` : ''
  return `${year}${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEKDAYS[d.getDay()]})`
}

/**
 * 마감일 배지 정보. 마감일이 없으면 null.
 * tone: overdue(지남, 미완료만) | today | soon(내일) | default
 */
export function describeDue(dueDate, done, today = toISODate(new Date())) {
  if (!dueDate) return null
  const days = diffDays(dueDate, today)
  if (done) return { tone: 'default', label: `마감 ${formatDate(dueDate, today)}` }
  if (days < 0) return { tone: 'overdue', label: `${formatDate(dueDate, today)} 마감 지남` }
  if (days === 0) return { tone: 'today', label: '오늘 마감' }
  if (days === 1) return { tone: 'soon', label: '내일 마감' }
  return { tone: 'default', label: `마감 ${formatDate(dueDate, today)}` }
}
