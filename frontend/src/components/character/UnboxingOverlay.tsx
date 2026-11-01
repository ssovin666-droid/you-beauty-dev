import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { trackCharacterEvent } from '../../lib/amplitude'
import { characterApi, type CharacterState } from '../../lib/character/api'
import { ARCHETYPES } from '../../lib/character/config'
import { prefersReducedMotion, type ThemeMode } from '../../lib/character/env'
import { haptic } from '../../lib/telegram'
import { CosmiStar, type CosmiStarHandle } from './CosmiStar'
import { LockedCapsule } from './LockedCapsule'
import { SharePanel } from './SharePanel'

type Phase = 'intro' | 'shake' | 'crack' | 'reveal' | 'plate' | 'share'

type Props = {
  character: CharacterState
  theme: ThemeMode
  onDone: (next: CharacterState | null) => void
}

// Полноэкранная распаковка: капсула трясётся → трескается →
// вспышка → звёздочка вылетает → плашка с типом → «Поделиться».
export function UnboxingOverlay({ character, theme, onDone }: Props) {
  const [phase, setPhase] = useState<Phase>('intro')
  const [flash, setFlash] = useState(false)
  const starRef = useRef<CosmiStarHandle>(null)
  const unboxed = useRef<CharacterState | null>(null)
  const timers = useRef<number[]>([])
  const T = ARCHETYPES[character.archetype]
  const accent = character.accent ? ARCHETYPES[character.accent] : null

  // --- таймлайн
  useEffect(() => {
    const k = prefersReducedMotion() ? 0.4 : 1
    const at = (ms: number, fn: () => void) => window.setTimeout(fn, ms * k)
    timers.current = [
      at(450, () => setPhase('shake')),
      at(750, () => haptic('light')),
      at(1150, () => haptic('light')),
      at(1500, () => haptic('medium')),
      at(1950, () => { setPhase('crack'); haptic('heavy') }),
      at(2550, () => setFlash(true)),
      at(2700, () => {
        setPhase('reveal')
        starRef.current?.playIntro()
        haptic('success')
      }),
      at(3050, () => setFlash(false)),
      at(3700, () => setPhase('plate')),
    ]
    return () => timers.current.forEach(window.clearTimeout)
  }, [])

  function skip() {
    timers.current.forEach(window.clearTimeout)
    setFlash(false)
    setPhase('reveal')
    window.setTimeout(() => starRef.current?.playIntro(), 30)
    timers.current = [window.setTimeout(() => setPhase('plate'), 900)]
  }

  // --- фиксируем распаковку на сервере (показывается один раз)
  useEffect(() => {
    if (phase !== 'reveal') return
    trackCharacterEvent('character_unbox_started', { archetype: character.archetype })
    characterApi
      .unbox()
      .then(next => { unboxed.current = next })
      .catch(error => {
        trackCharacterEvent('character_unbox_failed')
        console.error('unbox failed', error)
      })
  }, [phase, character.archetype, character.accent, T.rare])

  function finish() {
    onDone(unboxed.current)
  }

  const starVisible = phase === 'reveal' || phase === 'plate' || phase === 'share'

  return createPortal(
    <div className={`cs-unbox phase-${phase}`} data-theme={theme}>
      <div className="cs-unbox-bg" style={{ ['--glow' as string]: T.glowCol }} />

      {phase !== 'share' && (
        <div className="cs-unbox-top">
          <span>{phase === 'plate' ? 'знакомься' : 'собираю твоё существо…'}</span>
        </div>
      )}

      <div className="cs-unbox-stage">
        <div className={`cs-unbox-star ${starVisible ? 'is-visible' : ''}`}>
          <CosmiStar
            ref={starRef}
            archetype={character.archetype}
            accent={character.accent}
            evolution={character.evolution}
            shapeSeed={character.shape_seed}
            distribution={character.distribution}
            equipped={character.equipped}
            theme={theme}
            interactive={phase === 'plate'}
            onTap={() => haptic('light')}
          />
        </div>

        {!starVisible && (
          <div className="cs-unbox-capsule">
            <LockedCapsule
              progress={1}
              target={1}
              ready
              shaking={phase === 'shake' || phase === 'crack'}
              cracked={phase === 'crack'}
            />
          </div>
        )}

        {starVisible && (
          <div className="cs-unbox-shards" aria-hidden="true">
            <span className="cs-shard cs-shard-l" />
            <span className="cs-shard cs-shard-r" />
          </div>
        )}
      </div>

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

      {(phase === 'intro' || phase === 'shake') && (
        <button
          type="button"
          className="cs-unbox-skip"
          onClick={skip}
        >
          пропустить
        </button>
      )}

      <div className={`cs-unbox-flash ${flash ? 'is-on' : ''}`} />
    </div>,
    document.body,
  )
}
