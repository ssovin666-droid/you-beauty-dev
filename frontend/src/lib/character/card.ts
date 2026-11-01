import { ARCHETYPES, type ArchetypeKey } from './config'
import type { ThemeMode } from './env'

const CARD_THEME: Record<ThemeMode, { stage: string; ink: string; mute: string }> = {
  light: { stage: '#ece8ea', ink: '#17151a', mute: '#77727c' },
  dark: { stage: '#1a181d', ink: '#f3f1f4', mute: '#8f8a95' },
}

const FONT = 'Manrope, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif'
const LOGO_FONT = 'Unbounded, Manrope, sans-serif'

// Canvas рисует только уже загруженные шрифты — догружаем перед отрисовкой.
async function ensureFonts() {
  if (!document.fonts?.load) return
  try {
    await Promise.all([
      document.fonts.load(`600 44px ${LOGO_FONT}`, 'cosmi'),
      document.fonts.load(`500 42px ${FONT}`, 'ая'),
      document.fonts.load(`600 30px ${FONT}`, 'ая'),
      document.fonts.load(`700 34px ${FONT}`, 'ая'),
      document.fonts.load(`800 80px ${FONT}`, 'ая'),
    ])
  } catch {
    // нет шрифта — нарисуем системным
  }
}

export const BOT_USERNAME: string =
  import.meta.env.VITE_BOT_USERNAME || 'cosmi_bbot'

// Сторис 1080×1920 по макету референса.
// starCanvas — кадр WebGL, отрисованный прямо перед вызовом.
export async function makeShareCard(
  starCanvas: HTMLCanvasElement | null,
  archetype: ArchetypeKey,
  theme: ThemeMode,
): Promise<Blob> {
  await ensureFonts()

  const T = ARCHETYPES[archetype]
  const th = CARD_THEME[theme]
  const W = 1080
  const H = 1920

  const canvas = document.createElement('canvas')
  canvas.width = W
  canvas.height = H
  const g = canvas.getContext('2d')
  if (!g) throw new Error('Canvas 2D недоступен')

  g.fillStyle = th.stage
  g.fillRect(0, 0, W, H)

  const glow = g.createRadialGradient(540, 900, 0, 540, 900, 700)
  glow.addColorStop(0, `${T.glowCol}55`)
  glow.addColorStop(1, `${T.glowCol}00`)
  g.fillStyle = glow
  g.fillRect(0, 0, W, H)

  if (starCanvas && starCanvas.width && starCanvas.height) {
    // Квадрат из центра кадра с мягкой круглой маской.
    const sw = starCanvas.width
    const sh = starCanvas.height
    const side = Math.min(sw, sh)
    const tmp = document.createElement('canvas')
    tmp.width = tmp.height = 1080
    const tg = tmp.getContext('2d')
    if (tg) {
      tg.drawImage(starCanvas, (sw - side) / 2, (sh - side) / 2, side, side, 0, 0, 1080, 1080)
      tg.globalCompositeOperation = 'destination-in'
      const mask = tg.createRadialGradient(540, 540, 400, 540, 540, 540)
      mask.addColorStop(0, '#000')
      mask.addColorStop(1, 'rgba(0,0,0,0)')
      tg.fillStyle = mask
      tg.fillRect(0, 0, 1080, 1080)
      g.drawImage(tmp, 0, 360)
    }
  }

  g.textBaseline = 'alphabetic'
  g.fillStyle = th.ink
  // Логотип: Unbounded 600, трекинг −0.03em.
  g.font = `600 44px ${LOGO_FONT}`
  const ctx = g as CanvasRenderingContext2D & { letterSpacing?: string }
  if ('letterSpacing' in ctx) ctx.letterSpacing = `${-0.03 * 44}px`
  g.fillText('cosmi', 84, 140)
  if ('letterSpacing' in ctx) ctx.letterSpacing = '0px'
  g.font = `800 80px ${FONT}`
  g.fillText('моя косметичка', 84, 270)
  g.fillText('выглядит так', 84, 362)

  g.fillStyle = th.mute
  g.font = `700 34px ${FONT}`
  g.fillText('мой тип', 84, 1500)

  if (T.rare) {
    const x = 84 + g.measureText('мой тип').width + 20
    const lg = g.createLinearGradient(x, 0, x + 210, 0)
    lg.addColorStop(0, '#ffd36b')
    lg.addColorStop(0.5, '#ff8fc0')
    lg.addColorStop(1, '#9fd8ff')
    g.fillStyle = lg
    g.beginPath()
    if (typeof g.roundRect === 'function') g.roundRect(x, 1466, 210, 46, 23)
    else g.rect(x, 1466, 210, 46)
    g.fill()
    g.fillStyle = '#17151a'
    g.font = `800 26px ${FONT}`
    g.fillText('редкий тип', x + 28, 1498)
  }

  g.fillStyle = th.ink
  g.font = `800 112px ${FONT}`
  g.fillText(T.name, 78, 1626)

  g.font = `500 42px ${FONT}`
  let line = ''
  let y = 1702
  T.caption.split(' ').forEach(word => {
    const test = line ? `${line} ${word}` : word
    if (g.measureText(test).width > 912 && line) {
      g.fillText(line, 84, y)
      y += 56
      line = word
    } else {
      line = test
    }
  })
  if (line) g.fillText(line, 84, y)

  g.fillStyle = th.mute
  g.font = `600 30px ${FONT}`
  g.fillText(`сканируй косметику в @${BOT_USERNAME}`, 84, 1856)

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      blob => (blob ? resolve(blob) : reject(new Error('Не удалось собрать карточку'))),
      'image/png',
    )
  })
}
