import { useCallback, useEffect, useRef, useState } from 'react'

import type { Tab } from '../BottomNav'
import { trackCharacterEvent } from '../../lib/amplitude'
import {
  characterApi,
  type CharacterState,
  type InventoryItem,
  type PendingReward,
} from '../../lib/character/api'
import { readCachedCharacter, writeCachedCharacter } from '../../lib/character/cache'
import { ARCHETYPES, pluralItems } from '../../lib/character/config'
import { useTelegramTheme } from '../../lib/character/env'
import { getTelegramInitData, haptic } from '../../lib/telegram'
import { BottomSheet } from './BottomSheet'
import { CosmiStar, type CosmiStarHandle } from './CosmiStar'
import { HowToSheet } from './HowToSheet'
import { InventorySheet } from './InventorySheet'
import { ItemReveal } from './ItemReveal'
import { LockedCapsule } from './LockedCapsule'
import { QuestCard } from './QuestCard'
import { SharePanel } from './SharePanel'
import { UnboxingOverlay } from './UnboxingOverlay'

import '../../styles/character.css'

type Props = {
  go: (tab: Tab) => void
  // Меняется, когда главная перезагружает данные (фокус/возврат во вкладку).
  refreshToken: number
  // Пока /character не ответил — прогресс из уже загруженной полки.
  shelfCountHint: number
}

const HINT_KEY = 'cosmi_star_hint_seen'

function readHintSeen() {
  try {
    return localStorage.getItem(HINT_KEY) === '1'
  } catch {
    return false
  }
}

export function CharacterHero({ go, refreshToken, shelfCountHint }: Props) {
  const theme = useTelegramTheme()
  const starRef = useRef<CosmiStarHandle>(null)

  // Первый кадр — из кэша устройства (повторный заход), потом — ответ сервера.
  const [character, setCharacter] = useState<CharacterState | null>(readCachedCharacter)
  // Есть ли уже свежий ответ сервера. До него не запускаем распаковку,
  // не показываем награды и не шлём аналитику по данным из кэша.
  const [fresh, setFresh] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [unboxing, setUnboxing] = useState(false)
  const [howToOpen, setHowToOpen] = useState(false)
  const [inventoryOpen, setInventoryOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [busyCode, setBusyCode] = useState<string | null>(null)
  const [hintSeen, setHintSeen] = useState(readHintSeen)
  const [shownRewardIds, setShownRewardIds] = useState<number[]>([])

  const viewedTracked = useRef(false)
  const lastTapAt = useRef(0)

  const load = useCallback(async () => {
    if (!getTelegramInitData()) return
    try {
      const next = await characterApi.get()
      setCharacter(next)
      setFresh(true)
      setError(null)
    } catch (err) {
      console.error(err)
      setError(err instanceof Error ? err.message : 'Не удалось загрузить существо')
    }
  }, [])

  useEffect(() => {
    // Главная поднимает refreshToken при каждом своём loadHomeData,
    // включая первый — поэтому 0 пропускаем, чтобы не грузить дважды.
    if (refreshToken > 0) load()
  }, [load, refreshToken])

  // --- кэш последнего состояния для следующего захода
  useEffect(() => {
    if (fresh && character) writeCachedCharacter(character)
  }, [fresh, character])

  // --- аналитика: прогресс увидели
  useEffect(() => {
    if (!fresh || !character || viewedTracked.current) return
    viewedTracked.current = true
    trackCharacterEvent('character_progress_viewed', {
      status: character.status,
      shelf_count: character.progress.shelf_count,
      shelf_target: character.progress.shelf_target,
      archetype: character.status === 'locked' ? null : character.archetype,
      quest: character.quest.code,
    })
  }, [fresh, character])

  // --- 10-й товар: распаковка при открытии главной
  useEffect(() => {
    if (fresh && character?.status === 'ready_to_unbox') setUnboxing(true)
  }, [fresh, character?.status])

  // --- капсула готова: заранее подгружаем 3D-чанк распаковки
  useEffect(() => {
    if (character?.status === 'ready_to_unbox') import('../../lib/character/scene').catch(() => undefined)
  }, [character?.status])

  // --- награды, которые ещё не показывали
  const pending: PendingReward | undefined =
    fresh && character?.status === 'active' && !unboxing
      ? character.pending_rewards.find(r => !shownRewardIds.includes(r.id))
      : undefined

  useEffect(() => {
    if (!pending) return
    trackCharacterEvent('item_received', {
      reward_id: pending.id,
      kind: pending.kind,
      rarity: pending.item?.rarity ?? pending.rolled_rarity ?? null,
      item_code: pending.item?.code ?? null,
      source: pending.source,
    })
    if (pending.source === 'wishlist_quest') {
      trackCharacterEvent('quest_completed', { quest: 'first_item', reward_id: pending.id })
    }
  }, [pending?.id])

  function closeReward(reward: PendingReward) {
    setShownRewardIds(ids => [...ids, reward.id])
    characterApi.ackRewards([reward.id]).catch(() => undefined)
  }

  async function equip(code: string, on: boolean) {
    setBusyCode(code)
    try {
      const next = await characterApi.equip(code, on)
      setCharacter(next)
      trackCharacterEvent(on ? 'item_equipped' : 'item_unequipped', { item_code: code })
      haptic('selection')
    } catch (err) {
      console.error(err)
      trackCharacterEvent('item_equip_failed', { item_code: code, equip: on })
    } finally {
      setBusyCode(null)
    }
  }

  function toggleItem(item: InventoryItem) {
    if (!item.owned) return
    equip(item.code, !item.equipped)
  }

  function handleTap() {
    haptic('light')
    const now = Date.now()
    if (now - lastTapAt.current > 1000) {
      lastTapAt.current = now
      trackCharacterEvent('character_tapped', { archetype: character?.archetype ?? null })
    }
  }

  function handleFirstDrag() {
    setHintSeen(true)
    try {
      localStorage.setItem(HINT_KEY, '1')
    } catch {
      // приватный режим
    }
  }

  function openInventory() {
    setInventoryOpen(true)
    trackCharacterEvent('inventory_opened', {
      owned: character?.inventory.filter(i => i.owned).length ?? 0,
    })
  }

  const status = character?.status ?? 'locked'
  const shelfCount = character?.progress.shelf_count ?? shelfCountHint
  const target = character?.progress.shelf_target ?? 10
  const left = Math.max(0, target - shelfCount)
  const overlayOpen = unboxing || Boolean(pending) || shareOpen

  // -------------------------
  // ЗАГРУЗКА (нет ни кэша, ни ответа) — нейтральная заглушка, не капсула
  // -------------------------

  if (!character && !error && getTelegramInitData()) {
    return (
      <div className="cs-hero" data-theme={theme}>
        <div className="cs-hero-skeleton" aria-busy="true" />
      </div>
    )
  }

  // -------------------------
  // LOCKED / READY
  // -------------------------

  if (status !== 'active' || !character) {
    const ready = status === 'ready_to_unbox'
    return (
      <div className="cs-hero" data-theme={theme}>
        <div className="cs-locked">
          <div className="cs-locked-stage">
            <LockedCapsule
              progress={shelfCount}
              target={target}
              ready={ready}
              onClick={() => {
                haptic('light')
                if (!ready) return
                trackCharacterEvent('character_unbox_clicked', { source: 'capsule' })
                setUnboxing(true)
              }}
            />
            <button
              type="button"
              className="cs-icon-btn cs-stage-btn cs-stage-btn-right"
              onClick={() => { trackCharacterEvent('character_help_opened'); setHowToOpen(true) }}
              aria-label="Как прокачать"
            >
              i
            </button>
          </div>

          <div className="cs-locked-copy">
            <div className="cs-kicker">твоё существо</div>
            <h3>
              {ready ? 'Готово! Открывай капсулу' : 'Добавь 10 средств — и мы соберём твоё существо из косметички'}
            </h3>

            <div className="cs-progress-row">
              <div className="cs-progress" role="progressbar" aria-valuemin={0} aria-valuemax={target} aria-valuenow={shelfCount}>
                <span style={{ width: `${Math.min(100, (shelfCount / target) * 100)}%` }} />
              </div>
              <span className="cs-progress-label">
                {Math.min(shelfCount, target)}/{target} {pluralItems(target)} на полке
              </span>
            </div>

            {!ready && left > 0 && (
              <p className="cs-muted cs-small">
                осталось {left} {pluralItems(left)}. тип зависит от оттенков — будет интересно
              </p>
            )}

            {ready ? (
              <button type="button" className="cs-btn cs-btn-primary" onClick={() => { trackCharacterEvent('character_unbox_clicked', { source: 'button' }); setUnboxing(true) }}>
                Распаковать
              </button>
            ) : (
              <button type="button" className="cs-btn cs-btn-primary" onClick={() => go('shelf')}>
                Добавить на полку
              </button>
            )}
            {error && <p className="cs-muted cs-small">{error}</p>}
          </div>
        </div>

        <HowToSheet open={howToOpen} onClose={() => setHowToOpen(false)} theme={theme} character={character} />

        {unboxing && character && (
          <UnboxingOverlay
            character={character}
            theme={theme}
            onDone={next => {
              setUnboxing(false)
              if (next) setCharacter(next)
              else load()
            }}
          />
        )}
      </div>
    )
  }

  // -------------------------
  // ACTIVE
  // -------------------------

  const T = ARCHETYPES[character.archetype]
  const accent = character.accent && character.accent !== character.archetype ? ARCHETYPES[character.accent] : null

  return (
    <div className="cs-hero" data-theme={theme}>
      <div className="cs-stage">
        <CosmiStar
          ref={starRef}
          archetype={character.archetype}
          accent={character.accent}
          evolution={character.evolution}
          shapeSeed={character.shape_seed}
          distribution={character.distribution}
          equipped={character.equipped}
          theme={theme}
          interactive
          cameraY={-0.12}
          zoom={1.04}
          paused={overlayOpen}
          onTap={handleTap}
          onFirstDrag={handleFirstDrag}
        />

        {!hintSeen && <div className="cs-hint">покрути меня или ткни</div>}

        <div className="cs-stage-actions">
          <button type="button" className="cs-icon-btn" onClick={() => { trackCharacterEvent('character_help_opened'); setHowToOpen(true) }} aria-label="Как прокачать">
            i
          </button>
          <button type="button" className="cs-icon-btn" onClick={openInventory} aria-label="Инвентарь">
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M5 7h10l-1 10H6L5 7Z" />
              <path d="M7.5 7V5.5a2.5 2.5 0 0 1 5 0V7" />
            </svg>
          </button>
          <button type="button" className="cs-icon-btn" onClick={() => { trackCharacterEvent('character_share_opened'); setShareOpen(true) }} aria-label="Поделиться">
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M10 3v10" />
              <path d="m6 7 4-4 4 4" />
              <path d="M4 12v4h12v-4" />
            </svg>
          </button>
        </div>

      </div>

      <div className="cs-type-plate">
        <div className="cs-plate-row">
          <span className="cs-plate-label">твой тип</span>
          {T.rare && <span className="cs-rare-badge">редкий тип</span>}
          {character.evolution > 0 && <span className="cs-evo-badge">ур. {character.evolution + 1}</span>}
        </div>
        <div className="cs-plate-name">{T.name}</div>
        <div className="cs-plate-caption">{T.caption}</div>
        {accent && <div className="cs-plate-meta">акцент: {accent.name}</div>}
      </div>

      <QuestCard
        quest={character.quest}
        onAction={() => { trackCharacterEvent('character_quest_clicked', { quest: character.quest.code }); go(character.quest.code === 'unlock' ? 'shelf' : 'wishlist') }}
      />

      <button type="button" className="cs-howto-link" onClick={() => { trackCharacterEvent('character_help_opened'); setHowToOpen(true) }}>
        Как прокачать →
      </button>

      <HowToSheet open={howToOpen} onClose={() => setHowToOpen(false)} theme={theme} character={character} />

      <InventorySheet
        open={inventoryOpen}
        onClose={() => setInventoryOpen(false)}
        theme={theme}
        inventory={character.inventory}
        busyCode={busyCode}
        onToggle={toggleItem}
      />

      <BottomSheet open={shareOpen} onClose={() => setShareOpen(false)} title="Поделиться" theme={theme} tall>
        {shareOpen && (
          <SharePanel
            starRef={starRef}
            archetype={character.archetype}
            accent={character.accent}
            theme={theme}
            source="home"
            onClose={() => setShareOpen(false)}
          />
        )}
      </BottomSheet>

      {pending && (
        <ItemReveal
          key={pending.id}
          reward={pending}
          evolution={character.evolution + 1}
          theme={theme}
          onEquip={async code => {
            closeReward(pending)
            await equip(code, true)
          }}
          onClose={() => closeReward(pending)}
        />
      )}
    </div>
  )
}
