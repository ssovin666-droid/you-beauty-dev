import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { trackCharacterEvent } from '../../lib/amplitude'
import { characterApi, type CharacterState } from '../../lib/character/api'
import { ARCHETYPES } from '../../lib/character/config'
import { prefersReducedMotion, type ThemeMode } from '../../lib/character/env'
import { haptic } from '../../lib/telegram'
import { CosmiStar, type CapsuleState, type CosmiStarHandle } from './CosmiStar'
import { SharePanel } from './SharePanel'

// capsule — капсула готова, ждём тап; opening — заряд и взрыв;
// reveal — персонаж проявился; plate — плашка с типом; share — «Поделиться».
type Phase = 'capsule' | 'opening' | 'reveal' | 'plate' | 'share'
type Trigger = 'tap' | 'button' | 'skip'

type Props = {
  character: CharacterState
  theme: ThemeMode
  onDone: (next: CharacterState | null) => void
}

// Полноэкранная распаковка (design-reference «Cosmi Capsule»):
// перламутровая капсула с силуэтом → тап → заряд (тряска, свет из шва)
// → половинки разлетаются, вспышка, конфетти → персонаж проявляется,
// открывает глаза → плашка с типом → «Поделиться».
export function UnboxingOverlay({ character, theme, onDone }: Props) {
  const [phase, setPhase] = useState<Phase>('capsule')
  const starRef = useRef<CosmiStarHandle>(null)
  const unboxed = useRef<CharacterState | null>(null)
  const started = useRef(false)
  const timers = useRef<number[]>([])
  const T = ARCHETYPES[character.archetype]
  const accent = character.accent ? ARCHETYPES[character.accent] : null
  const reduced = useMemo(() => prefersReducedMotion(), [])

  useEffect(() => () => timers.current.forEach(window.clearTimeout), [])

  // Старт раскрытия: фиксируем распаковку на сервере (показывается один раз).
  function start(trigger: Trigger) {
    if (started.current) return
    started.current = true
    setPhase('opening')
    trackCharacterEvent('character_unbox_started', { archetype: character.archetype, trigger })
    characterApi
      .unbox()
      .then(next => { unboxed.current = next })
      .catch(error => {
        trackCharacterEvent('character_unbox_failed')
        console.error('unbox failed', error)
      })

    if (trigger === 'skip') return
    // хаптик нарастает вместе с зарядом капсулы
    const k = reduced ? 0.6 : 1
    timers.current.push(
      window.setTimeout(() => haptic('light'), 0),
      window.setTimeout(() => haptic('light'), 450 * k),
      window.setTimeout(() => haptic('medium'), 850 * k),
      window.setTimeout(() => haptic('medium'), 1100 * k),
    )
  }

  function skip() {
    start('skip')
    starRef.current?.skipCapsule()
  }

  function onRevealed() {
    haptic('success')
    setPhase(p => (p === 'capsule' || p === 'opening' ? 'reveal' : p))
    timers.current.push(
      window.setTimeout(() => setPhase(p => (p === 'reveal' ? 'plate' : p)), reduced ? 150 : 450),
    )
  }

  function finish() {
    onDone(unboxed.current)
  }

  const capsule: CapsuleState = {
    phase: phase === 'capsule' ? 'ready' : 'open',
    speed: reduced ? 1.6 : 1,
  }

  return createPortal(
    <div className={`cs-unbox phase-${phase}`} data-theme={theme}>
      {phase !== 'share' && (
        <div className="cs-unbox-top">
          <span className={phase === 'capsule' ? 'cs-unbox-pill' : undefined}>
            {phase === 'capsule' && 'нажми на капсулу'}
            {phase === 'opening' && 'собираю твоё существо…'}
            {(phase === 'reveal' || phase === 'plate') && 'знакомься'}
          </span>
        </div>
      )}

      <div className="cs-unbox-stage">
        <div className="cs-unbox-star is-visible">
          <CosmiStar
            ref={starRef}
            className="is-unbox"
            archetype={character.archetype}
            accent={character.accent}
            evolution={character.evolution}
            shapeSeed={character.shape_seed}
            distribution={character.distribution}
            equipped={character.equipped}
            theme={theme}
            interactive={phase === 'plate'}
            capsule={capsule}
            onCapsuleBurst={() => haptic('heavy')}
            onCapsuleRevealed={onRevealed}
            onTap={() => {
              haptic('light')
              if (phase === 'capsule') start('tap')
            }}
          />
        </div>
      </div>

      {phase === 'capsule' && (
        <div className="cs-unbox-cta">
          <button type="button" className="cs-btn cs-btn-primary" onClick={() => start('button')}>
            Открыть капсулу
          </button>
        </div>
      )}

      {phase === 'plate' && (
        <div className="cs-unbox-plate">
          <div className="cs-plate-row">
            <span className="cs-plate-label">твой тип</span>
            {T.rare && <span className="cs-rare-badge">редкий тип</span>}
          </div>
          <div className="cs-plate-name">{T.name}</div>
          <div className="cs-plate-caption">{T.caption}</div>
          {accent && character.accent !== character.archetype && (
            <div className="cs-plate-meta">акцент: {accent.name}</div>
          )}
          <button type="button" className="cs-btn cs-btn-primary" onClick={() => setPhase('share')}>
            Дальше
          </button>
        </div>
      )}

      {phase === 'share' && (
        <div className="cs-unbox-share">
          <h2>Покажи всем, кто живёт в твоей косметичке</h2>
          <SharePanel
            starRef={starRef}
            archetype={character.archetype}
            accent={character.accent}
            theme={theme}
            source="unboxing"
            onClose={finish}
          />
        </div>
      )}

      {phase === 'opening' && (
        <button type="button" className="cs-unbox-skip" onClick={skip}>
          пропустить
        </button>
      )}
    </div>,
    document.body,
  )
}
