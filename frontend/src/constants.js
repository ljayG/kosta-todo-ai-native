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

// 카테고리 (FR-16). 값은 API와 같고, 순서 = 화면 표시 순서
export const CATEGORIES = [
  { value: 'work', label: '업무' },
  { value: 'personal', label: '개인' },
  { value: 'study', label: '학습' },
]

export const CATEGORY_LABEL = Object.fromEntries(CATEGORIES.map((c) => [c.value, c.label]))
export const DEFAULT_CATEGORY = 'personal'
