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

export type CosmiStarHandle = {
  // Кадр персонажа для карточки сторис (2D-копия).
  snapshot: () => Promise<HTMLCanvasElement | null>
  react: () => void
  playIntro: () => void
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
  },
  ref,
) {
  const hostRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<StarScene | null>(null)
  const callbacks = useRef({ onTap, onFirstDrag })
  callbacks.current = { onTap, onFirstDrag }

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
  const latest = useRef({ archetype, accent, evolution, particles, equipped, theme })
  latest.current = { archetype, accent, evolution, particles, equipped, theme }

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
    }),
    [archetype, accent, shapeSeed],
  )

  const fallbackMarkup = useMemo(
    () => (fallback ? starSvgMarkup(archetype, accent, { seed: shapeSeed }) : ''),
    [fallback, archetype, accent, shapeSeed],
  )

  return (
    <div
      ref={hostRef}
      className={`cosmi-star ${fallback ? 'is-fallback' : ''} ${className ?? ''}`}
      style={{ background: STAGE_COLORS[theme] }}
      data-ready={ready || fallback ? 'true' : 'false'}
    >
      {fallback && (
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
