import { PRIORITY_LABEL } from '../constants.js'

// 우선순위 배지. 색만으로 구분하지 않도록 텍스트를 함께 표시한다.
export default function PriorityBadge({ priority }) {
  return (
    <span className={`badge badge--${priority}`}>
      <span className="sr-only">우선순위 </span>
      {PRIORITY_LABEL[priority]}
    </span>
  )
}
