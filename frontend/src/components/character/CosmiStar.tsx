import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react'

import {
  shelfParticles,
  type ArchetypeKey,
  type ShadeKey,
  type Slot,
} from '../../lib/character/config'
import {
  STAGE_COLORS,
  isDeviceMarkedSlow,
  markDeviceSlow,
  useAppActive,
  webglSupport,
  type ThemeMode,
} from '../../lib/character/env'
import { rasterizeStar, starSvgMarkup } from '../../lib/character/fallback'
import type { StarScene } from '../../lib/character/scene'
import { LockedCapsule } from './LockedCapsule'

// Капсула вокруг персонажа (design-reference «Cosmi Capsule»).
// locked — собирается (progress 0..1), ready — можно открыть,
// open — запустить открытие (заряд → взрыв → проявление).
export type CapsuleState = {
  phase: 'locked' | 'ready' | 'open'
  progress?: number
  // Скорость заряда/взрыва (1 — как в референсе).
  speed?: number
}

export type CosmiStarHandle = {
  // Кадр персонажа для карточки сторис (2D-копия).
  snapshot: () => Promise<HTMLCanvasElement | null>
  react: () => void
  playIntro: () => void
  // Пропустить анимацию капсулы — сразу открытый персонаж.
  skipCapsule: () => void
}

type Props = {
  archetype: ArchetypeKey
  accent: ArchetypeKey | null
  evolution?: number
  distribution?: Partial<Record<ShadeKey, number>>
  equipped?: Partial<Record<Slot, string | null>>
  theme: ThemeMode
  interactive?: boolean
  // Внешняя пауза: например, поверх открыт полноэкранный оверлей.
  paused?: boolean
  // Seed формы, закреплённый за пользователем на сервере.
  shapeSeed?: number | null
  zoom?: number
  cameraY?: number
  className?: string
  onTap?: () => void
  onFirstDrag?: () => void
  // Режим капсулы задаётся при монтировании (наличие пропа),
  // дальше меняется только phase/progress.
  capsule?: CapsuleState | null
  onCapsuleBurst?: () => void
  onCapsuleRevealed?: () => void
}

// Если кадр в среднем дольше — переключаемся на картинку.
const SLOW_FRAME_MS = 45

export const CosmiStar = forwardRef<CosmiStarHandle, Props>(function CosmiStar(
  {
    archetype,
    accent,
    evolution = 0,
    distribution,
    equipped,
    theme,
    interactive = false,
    paused = false,
    shapeSeed,
    zoom,
    cameraY,
    className,
    onTap,
    onFirstDrag,
    capsule,
    onCapsuleBurst,
    onCapsuleRevealed,
  },
  ref,
) {
  const hostRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<StarScene | null>(null)
  const callbacks = useRef({ onTap, onFirstDrag, onCapsuleBurst, onCapsuleRevealed })
  callbacks.current = { onTap, onFirstDrag, onCapsuleBurst, onCapsuleRevealed }
  const capsuleMode = useRef(Boolean(capsule)).current
  // Капсула раскрыта (персонаж виден) — общий флаг для 3D и картинки.
  const [revealed, setRevealed] = useState(false)
  const revealedRef = useRef(false)
  const markRevealed = () => {
    if (revealedRef.current) return
    revealedRef.current = true
    setRevealed(true)
    callbacks.current.onCapsuleRevealed?.()
  }

  const [fallback, setFallback] = useState(
    () => webglSupport() !== 'ok' || isDeviceMarkedSlow(),
  )
  // Номер текущей сцены (0 — ещё нет). Счётчик, а не boolean:
  // при пересоздании сцены false→true могло склеиться в один рендер,
  // эффекты синхронизации не перезапускались, и новая сцена оставалась
  // «пустой» (дефолтный вид) и на паузе.
  const [sceneVersion, setSceneVersion] = useState(0)
  const ready = sceneVersion > 0
  const [inView, setInView] = useState(true)
  const appActive = useAppActive()

  const particles = useMemo(
    () => shelfParticles(distribution ?? {}),
    [distribution],
  )

  // Актуальные пропсы для мгновенной настройки только что созданной сцены.
  const latest = useRef({ archetype, accent, evolution, particles, equipped, theme, capsule })
  latest.current = { archetype, accent, evolution, particles, equipped, theme, capsule }

  // --- создание сцены (three.js грузится отдельным чанком)
  useEffect(() => {
    if (fallback) return
    const host = hostRef.current
    if (!host) return

    let cancelled = false
    let scene: StarScene | null = null

    import('../../lib/character/scene')
      .then(({ StarScene }) => {
        if (cancelled) return
        scene = new StarScene(host, {
          interactive,
          stage: STAGE_COLORS[theme],
          quality: 'high',
          maxDpr: 2,
          shapeSeed,
          zoom,
          cameraY,
          onTap: () => callbacks.current.onTap?.(),
          onFirstDrag: () => callbacks.current.onFirstDrag?.(),
          capsule: capsuleMode && !revealedRef.current,
          onCapsuleBurst: () => callbacks.current.onCapsuleBurst?.(),
          onCapsuleRevealed: markRevealed,
          onPerfSample: avg => {
            if (avg > SLOW_FRAME_MS) {
              markDeviceSlow()
              setFallback(true)
            }
          },
          onContextLost: () => setFallback(true),
        })
        // Сразу применяем внешний вид — не ждём эффектов.
        const now = latest.current
        scene.setStage(STAGE_COLORS[now.theme])
        scene.setEvolution(now.evolution)
        scene.setLook(now.archetype, now.accent, Boolean(now.equipped?.aura))
        scene.setShelf(now.particles)
        scene.setEquipped(now.equipped ?? {}, true)
        if (now.capsule && !revealedRef.current) {
          scene.setCapsuleSpeed(now.capsule.speed ?? 1)
          scene.setCapsule(now.capsule.phase === 'locked' ? 'locked' : 'ready', now.capsule.progress ?? 0)
          if (now.capsule.phase === 'open') scene.openCapsule()
        }
        sceneRef.current = scene
        setSceneVersion(v => v + 1)
      })
      .catch(error => {
        console.error('Cosmi star: WebGL init failed', error)
        if (!cancelled) setFallback(true)
      })

    return () => {
      cancelled = true
      scene?.dispose()
      sceneRef.current = null
    }
    // Сцена создаётся один раз; остальное синхронизируется эффектами ниже.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fallback, shapeSeed])

  // --- пауза рендера, когда персонаж не виден
  useEffect(() => {
    const host = hostRef.current
    if (!host || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(
      entries => setInView(entries.some(e => e.isIntersecting)),
      { threshold: 0.05 },
    )
    io.observe(host)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    sceneRef.current?.setActive(inView && appActive && !paused)
  }, [sceneVersion, inView, appActive, paused])

  // --- синхронизация данных со сценой
  useEffect(() => {
    sceneRef.current?.setStage(STAGE_COLORS[theme])
  }, [sceneVersion, theme])

  useEffect(() => {
    sceneRef.current?.setEvolution(evolution)
  }, [sceneVersion, evolution])

  useEffect(() => {
    sceneRef.current?.setLook(archetype, accent, Boolean(equipped?.aura))
  }, [sceneVersion, archetype, accent, equipped?.aura])

  useEffect(() => {
    sceneRef.current?.setShelf(particles)
  }, [sceneVersion, particles])

  useEffect(() => {
    sceneRef.current?.setEquipped(equipped ?? {})
  }, [sceneVersion, equipped])

  // --- капсула: фаза и прогресс
  const capPhase = capsule?.phase
  const capProgress = capsule?.progress ?? 0
  const capSpeed = capsule?.speed ?? 1
  useEffect(() => {
    const scene = sceneRef.current
    if (!scene || !capPhase || revealedRef.current) return
    scene.setCapsuleSpeed(capSpeed)
    if (capPhase === 'open') scene.openCapsule()
    else scene.setCapsule(capPhase, capProgress)
  }, [sceneVersion, capPhase, capProgress, capSpeed])

  // --- капсула без WebGL: CSS-капсула трясётся → трескается → вспышка
  const [fbStage, setFbStage] = useState<'idle' | 'shake' | 'crack' | 'flash'>('idle')
  useEffect(() => {
    if (!fallback || !capsuleMode || capPhase !== 'open' || revealedRef.current) return
    const k = 1 / Math.max(0.3, capSpeed)
    const timers = [
      window.setTimeout(() => setFbStage('shake'), 0),
      window.setTimeout(() => setFbStage('crack'), 900 * k),
      window.setTimeout(() => { setFbStage('flash'); callbacks.current.onCapsuleBurst?.() }, 1400 * k),
      window.setTimeout(() => markRevealed(), 1650 * k),
      window.setTimeout(() => setFbStage('idle'), 2000 * k),
    ]
    return () => timers.forEach(window.clearTimeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fallback, capPhase, capSpeed])

  useImperativeHandle(
    ref,
    () => ({
      snapshot: async () => {
        const scene = sceneRef.current
        if (scene) {
          // Копируем кадр синхронно: буфер WebGL очищается после композитинга.
          const src = scene.snapshot()
          const copy = document.createElement('canvas')
          copy.width = src.width
          copy.height = src.height
          copy.getContext('2d')?.drawImage(src, 0, 0)
          return copy
        }
        try {
          return await rasterizeStar(archetype, accent, shapeSeed)
        } catch {
          return null
        }
      },
      react: () => sceneRef.current?.react(),
      playIntro: () => sceneRef.current?.playIntro(),
      skipCapsule: () => {
        if (!capsuleMode || revealedRef.current) return
        if (sceneRef.current) sceneRef.current.skipCapsule()
        else {
          setFbStage('idle')
          markRevealed()
        }
      },
    }),
    [archetype, accent, shapeSeed],
  )

  const fallbackMarkup = useMemo(
    () => (fallback ? starSvgMarkup(archetype, accent, { seed: shapeSeed }) : ''),
    [fallback, archetype, accent, shapeSeed],
  )
  const showFallbackCapsule = fallback && capsuleMode && !revealed

  return (
    <div
      ref={hostRef}
      className={`cosmi-star ${fallback ? 'is-fallback' : ''} ${className ?? ''}`}
      style={{ background: STAGE_COLORS[theme] }}
      data-ready={ready || fallback ? 'true' : 'false'}
    >
      {showFallbackCapsule && (
        <div className="cosmi-star-capsule-fb">
          <LockedCapsule
            progress={capPhase === 'locked' ? capProgress : 1}
            target={1}
            ready={capPhase !== 'locked'}
            shaking={fbStage === 'shake' || fbStage === 'crack'}
            cracked={fbStage === 'crack' || fbStage === 'flash'}
            onClick={() => callbacks.current.onTap?.()}
          />
        </div>
      )}
      {capsuleMode && fallback && <div className={`cosmi-star-flash ${fbStage === 'flash' ? 'is-on' : ''}`} />}
      {fallback && !showFallbackCapsule && (
        <button
          type="button"
          className="cosmi-star-fallback"
          aria-label="Твоё существо"
          onClick={() => callbacks.current.onTap?.()}
          // Разметка генерируется нами (без пользовательского ввода).
          dangerouslySetInnerHTML={{ __html: fallbackMarkup }}
        />
      )}
    </div>
  )
})
