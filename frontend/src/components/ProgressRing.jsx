// 완료율을 보여 주는 원형 프로그레스
export default function ProgressRing({ percent, done, total, size = 176, stroke = 16 }) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const offset = c * (1 - percent / 100)

  return (
    <div
      className="ring"
      role="progressbar"
      aria-label="완료율"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      aria-valuetext={`${percent}%, ${total}개 중 ${done}개 완료`}
      style={{ width: size, height: size }}
    >
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden="true">
        <circle className="ring__track" cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} />
        <circle
          className="ring__bar"
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <div className="ring__center" aria-hidden="true">
        <span className="ring__value">
          {percent}
          <small>%</small>
        </span>
        <span className="ring__caption">
          {total}개 중 {done}개 완료
        </span>
      </div>
    </div>
  )
}
