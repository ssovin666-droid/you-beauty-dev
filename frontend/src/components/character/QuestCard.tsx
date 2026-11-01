import type { Quest } from '../../lib/character/api'

type Props = {
  quest: Quest
  onAction: () => void
}

const COPY: Record<Quest['code'], { title: string; text: (q: Quest) => string; cta: string; reward: string }> = {
  unlock: {
    title: 'Собери существо',
    text: q => `Добавь ${q.target} средств на полку`,
    cta: 'На полку',
    reward: 'существо',
  },
  first_item: {
    title: 'Первый предмет',
    text: q => `Добавь ${q.target} товаров в wishlist`,
    cta: 'В wishlist',
    reward: 'первый предмет',
  },
  purchase: {
    title: 'Покупка = лут',
    text: () => 'Купи что-нибудь из wishlist через cosmi',
    cta: 'К wishlist',
    reward: 'предмет или эволюция',
  },
}

export function QuestCard({ quest, onAction }: Props) {
  const copy = COPY[quest.code]
  const hasProgress = quest.code !== 'purchase'
  const pct = Math.round((Math.min(quest.progress, quest.target) / quest.target) * 100)

  return (
    <div className="cs-quest">
      <div className="cs-quest-head">
        <span className="cs-quest-kicker">задание</span>
        <span className="cs-quest-reward">→ {copy.reward}</span>
      </div>
      <div className="cs-quest-title">{copy.title}</div>
      <div className="cs-quest-text">
        {copy.text(quest)}
        {hasProgress && (
          <b>
            {' '}
            ({Math.min(quest.progress, quest.target)}/{quest.target})
          </b>
        )}
      </div>
      {hasProgress && (
        <div className="cs-progress" role="progressbar" aria-valuemin={0} aria-valuemax={quest.target} aria-valuenow={quest.progress}>
          <span style={{ width: `${pct}%` }} />
        </div>
      )}
      <button type="button" className="cs-quest-cta" onClick={onAction}>
        {copy.cta} →
      </button>
    </div>
  )
}
