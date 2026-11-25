import { CATEGORIES } from '../constants.js'

const OPTIONS = [{ value: 'all', label: '전체' }, ...CATEGORIES]

// 카테고리 필터: 전체 / 업무 / 개인 / 학습 (FR-16)
// 라디오 그룹이라 ←/→ 키로 이동하고, 화면 낭독기에는 "카테고리" 그룹으로 읽힌다
export default function CategoryFilter({ value, onChange, counts }) {
  return (
    <fieldset className="catfilter">
      <legend className="catfilter__legend">카테고리</legend>
      {OPTIONS.map((o) => (
        <label key={o.value} className="catfilter__item">
          <input
            type="radio"
            name="category-filter"
            value={o.value}
            checked={value === o.value}
            onChange={() => onChange(o.value)}
          />
          <span>
            {o.label}
            <span className="catfilter__count">{counts[o.value]}</span>
          </span>
        </label>
      ))}
    </fieldset>
  )
}
