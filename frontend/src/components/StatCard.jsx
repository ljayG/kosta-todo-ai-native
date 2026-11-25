// 통계 카드: 라벨 + 숫자. tone으로 강조 색을 정한다 (default | done | active)
export default function StatCard({ label, value, tone = 'default' }) {
  return (
    <div className={`stat stat--${tone}`}>
      <dt className="stat__label">{label}</dt>
      <dd className="stat__value">{value}</dd>
    </div>
  )
}
