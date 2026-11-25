// 우선순위 정의 (정렬 순서 = 배열 순서)
export const PRIORITIES = [
  { value: 'high', label: '높음' },
  { value: 'medium', label: '보통' },
  { value: 'low', label: '낮음' },
]

export const PRIORITY_LABEL = Object.fromEntries(PRIORITIES.map((p) => [p.value, p.label]))
export const PRIORITY_RANK = Object.fromEntries(PRIORITIES.map((p, i) => [p.value, i]))

export const FILTERS = [
  { value: 'all', label: '전체' },
  { value: 'active', label: '진행 중' },
  { value: 'done', label: '완료' },
]
