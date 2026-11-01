import type { CharacterState } from '../../lib/character/api'
import {
  ARCHETYPES,
  RARITY,
  RARITY_ORDER,
  SHADES,
  SHADE_ORDER,
} from '../../lib/character/config'
import type { ThemeMode } from '../../lib/character/env'
import { BottomSheet } from './BottomSheet'

type Props = {
  open: boolean
  onClose: () => void
  theme: ThemeMode
  character: CharacterState | null
}

const DEFAULT_ODDS = { common: 70, rare: 22, epic: 7, secret: 1 }

export function HowToSheet({ open, onClose, theme, character }: Props) {
  const odds = character?.rarity_odds ?? DEFAULT_ODDS
  const dist = character?.distribution
  const total = dist ? SHADE_ORDER.reduce((sum, key) => sum + (dist[key] ?? 0), 0) : 0

  return (
    <BottomSheet open={open} onClose={onClose} title="Как прокачать" theme={theme} tall>
      <ol className="cs-howto">
        <li>
          <span className="cs-howto-icon">🎯</span>
          <div>
            <h4>Задания дают предметы</h4>
            <p>Добавляй товары, выполняй задания — за каждое выпадает шмотка для твоего существа.</p>
          </div>
        </li>
        <li>
          <span className="cs-howto-icon">🛍️</span>
          <div>
            <h4>Каждая покупка через cosmi — награда</h4>
            <p>
              Купила по ссылке из cosmi — получаешь новый предмет или существо эволюционирует.
              Считаются подтверждённые заказы, просто клики не в счёт.
            </p>
          </div>
        </li>
        <li>
          <span className="cs-howto-icon">💎</span>
          <div>
            <h4>Редкость</h4>
            <div className="cs-odds">
              {RARITY_ORDER.map(r => (
                <div key={r} className={`cs-odds-row rarity-${r}`}>
                  <span
                    className="cs-odds-frame"
                    style={{ ['--rarity-frame' as string]: RARITY[r].frame, ['--rarity-glow' as string]: RARITY[r].glow }}
                  />
                  <span className="cs-odds-label" style={{ color: RARITY[r].color }}>
                    {RARITY[r].label}
                  </span>
                  <span className="cs-odds-value">{odds[r]}%</span>
                </div>
              ))}
            </div>
          </div>
        </li>
        <li>
          <span className="cs-howto-icon">🪞</span>
          <div>
            <h4>Существо — это твоя полка</h4>
            <p>
              Самый частый оттенок на полке задаёт тип, второй — акцент. Если ни один не набрал
              больше 3 из 10 — выпадает редкий {ARCHETYPES.chameleon.name}. Меняется полка — меняется и существо.
            </p>

            {dist && total > 0 && (
              <>
                <div className="cs-dist-bar">
                  {SHADE_ORDER.filter(k => (dist[k] ?? 0) > 0).map(k => (
                    <span key={k} style={{ flex: dist[k], background: SHADES[k].css }} title={SHADES[k].label} />
                  ))}
                </div>
                <div className="cs-dist-legend">
                  {SHADE_ORDER.map(k => (
                    <span key={k}>
                      <i style={{ background: SHADES[k].css }} />
                      {SHADES[k].label}
                      <b>{dist[k] ?? 0}</b>
                    </span>
                  ))}
                </div>
              </>
            )}
            {character && character.progress.shelf_count > (character.progress.classified_count ?? 0) && (
              <p className="cs-muted cs-small">
                Часть товаров пока без оттенка — они не влияют на тип.
              </p>
            )}
          </div>
        </li>
      </ol>
    </BottomSheet>
  )
}
