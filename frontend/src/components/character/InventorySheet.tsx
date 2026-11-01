import type { InventoryItem } from '../../lib/character/api'
import { RARITY, SLOTS, itemSwatch } from '../../lib/character/config'
import type { ThemeMode } from '../../lib/character/env'
import { BottomSheet } from './BottomSheet'

type Props = {
  open: boolean
  onClose: () => void
  theme: ThemeMode
  inventory: InventoryItem[]
  busyCode: string | null
  onToggle: (item: InventoryItem) => void
}

export function InventorySheet({ open, onClose, theme, inventory, busyCode, onToggle }: Props) {
  const owned = inventory.filter(i => i.owned).length

  return (
    <BottomSheet open={open} onClose={onClose} title="Инвентарь" theme={theme}>
      <p className="cs-muted">
        {owned === 0
          ? 'Пока пусто. Предметы падают за задания и покупки через cosmi.'
          : `Собрано ${owned} из ${inventory.length}. Тапни, чтобы надеть или снять.`}
      </p>

      {SLOTS.map(slot => {
        const items = inventory.filter(i => i.slot === slot.key)
        if (!items.length) return null

        return (
          <section key={slot.key} className="cs-inv-slot">
            <div className="cs-inv-slot-title">
              <span>{slot.icon}</span> {slot.label}
            </div>

            <div className="cs-inv-grid">
              {items.map(item => {
                const R = RARITY[item.rarity]
                return (
                  <button
                    key={item.code}
                    type="button"
                    className={[
                      'cs-inv-card',
                      `rarity-${item.rarity}`,
                      item.owned ? 'is-owned' : 'is-locked',
                      item.equipped ? 'is-equipped' : '',
                    ].join(' ')}
                    style={{ ['--rarity-frame' as string]: R.frame, ['--rarity-glow' as string]: R.glow }}
                    disabled={!item.owned || busyCode === item.code}
                    onClick={() => onToggle(item)}
                    aria-pressed={item.equipped}
                  >
                    <span className="cs-inv-icon">
                      {item.owned ? (
                        <span className="cs-inv-swatch" style={{ background: itemSwatch(item.code) }} />
                      ) : (
                        <span className="cs-inv-lock">
                          <span>?</span>
                          <svg viewBox="0 0 16 16" aria-hidden="true">
                            <path d="M4.5 7V5a3.5 3.5 0 0 1 7 0v2" />
                            <rect x="3" y="7" width="10" height="7" rx="2" />
                          </svg>
                        </span>
                      )}
                    </span>
                    <span className="cs-inv-name">{item.owned ? item.name : '???'}</span>
                    <span className="cs-inv-rarity" style={{ color: R.color }}>
                      {R.label}
                    </span>
                    {item.owned && (
                      <span className="cs-inv-action">
                        {busyCode === item.code ? '…' : item.equipped ? 'надето ✓' : 'надеть'}
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </section>
        )
      })}
    </BottomSheet>
  )
}
