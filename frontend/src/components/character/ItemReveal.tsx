import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

import type { PendingReward } from '../../lib/character/api'
import { RARITY, SLOTS, itemSwatch } from '../../lib/character/config'
import { prefersReducedMotion, type ThemeMode } from '../../lib/character/env'
import { haptic } from '../../lib/telegram'

type Props = {
  reward: PendingReward
  evolution: number
  theme: ThemeMode
  onEquip?: (code: string) => void
  onClose: () => void
}

const SOURCE_TEXT: Record<string, string> = {
  wishlist_quest: 'за задание «первый предмет»',
  purchase: 'за покупку через cosmi',
  streak: 'за серию',
}

// Мини-анбоксинг: коробка трясётся → крышка слетает → предмет в свечении редкости.
export function ItemReveal({ reward, evolution, theme, onEquip, onClose }: Props) {
  const [opened, setOpened] = useState(false)
  const rarity = reward.item?.rarity ?? reward.rolled_rarity ?? 'common'
  const R = RARITY[rarity]
  const isEvolution = reward.kind === 'evolution' || !reward.item

  useEffect(() => {
    const delay = prefersReducedMotion() ? 200 : 1100
    const t1 = window.setTimeout(() => haptic('light'), 350)
    const t2 = window.setTimeout(() => {
      setOpened(true)
      haptic('success')
    }, delay)
    return () => {
      window.clearTimeout(t1)
      window.clearTimeout(t2)
    }
  }, [])

  const slotLabel = reward.item ? SLOTS.find(s => s.key === reward.item?.slot)?.label : null

  return createPortal(
    <div
      className={`cs-reveal rarity-${rarity} ${opened ? 'is-opened' : ''}`}
      data-theme={theme}
      style={{ ['--rarity-glow' as string]: R.glow, ['--rarity-color' as string]: R.color }}
    >
      <div className="cs-reveal-beam" />

      <div className="cs-reveal-stage" onClick={() => setOpened(true)}>
        <div className="cs-box">
          <div className="cs-box-lid" />
          <div className="cs-box-body" />
          <div className="cs-box-ribbon" />
        </div>

        <div className="cs-reveal-item">
          {isEvolution ? (
            <div className="cs-reveal-evo">✦</div>
          ) : (
            <div
              className={`cs-item-orb rarity-${rarity}`}
              style={{ background: itemSwatch(reward.item!.code) }}
            />
          )}
        </div>
      </div>

      <div className="cs-reveal-copy">
        {isEvolution ? (
          <>
            <div className="cs-reveal-rarity">эволюция</div>
            <h2>Твоё существо прокачалось</h2>
            <p>
              Уровень {evolution}: больше сияния и новые спутники.{' '}
              {reward.source && SOURCE_TEXT[reward.source]}
            </p>
          </>
        ) : (
          <>
            <div className="cs-reveal-rarity">{R.label}</div>
            <h2>{reward.item!.name}</h2>
            <p>
              {slotLabel ? `слот: ${slotLabel.toLowerCase()}` : ''}
              {reward.source && SOURCE_TEXT[reward.source] ? ` · ${SOURCE_TEXT[reward.source]}` : ''}
            </p>
          </>
        )}

        <div className="cs-reveal-actions">
          {!isEvolution && onEquip && (
            <button
              type="button"
              className="cs-btn cs-btn-primary"
              disabled={!opened}
              onClick={() => onEquip(reward.item!.code)}
            >
              Надеть
            </button>
          )}
          <button
            type="button"
            className={`cs-btn ${isEvolution ? 'cs-btn-primary' : 'cs-btn-ghost'}`}
            disabled={!opened}
            onClick={onClose}
          >
            {isEvolution ? 'Вау' : 'Потом'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
