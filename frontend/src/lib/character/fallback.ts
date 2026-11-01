// Статичная картинка персонажа (SVG) для слабых устройств,
// ошибки WebGL и силуэта в капсуле. Силуэт считается той же
// функцией радиуса (shape.ts), что и 3D-тело, поэтому формы совпадают.

import { ARCHETYPES, type ArchetypeKey } from './config'
import { generateShape, shapeRadius } from './shape'

function starPath(cx: number, cy: number, scale: number, seed?: number | null) {
  const shape = generateShape(seed)
  const pts: string[] = []
  const steps = 240
  for (let i = 0; i <= steps; i++) {
    const th = (i / steps) * Math.PI * 2
    const r = shapeRadius(shape, th).s * scale
    const x = cx + Math.cos(th) * r
    const y = cy - Math.sin(th) * r
    pts.push(`${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`)
  }
  return `${pts.join(' ')}Z`
}

function shade(hex: string, amount: number) {
  const n = parseInt(hex.slice(1), 16)
  const mix = (c: number) =>
    Math.round(amount < 0 ? c * (1 + amount) : c + (255 - c) * amount)
  const r = mix((n >> 16) & 255)
  const g = mix((n >> 8) & 255)
  const b = mix(n & 255)
  return `#${((1 << 24) | (r << 16) | (g << 8) | b).toString(16).slice(1)}`
}

export function starSvgMarkup(
  archetype: ArchetypeKey,
  accentKey: ArchetypeKey | null,
  options: { silhouette?: boolean; size?: number; seed?: number | null } = {},
) {
  const T = ARCHETYPES[archetype]
  const A = ARCHETYPES[accentKey ?? archetype]
  const accent = archetype === 'chameleon' ? '#ffffff' : (accentKey && accentKey !== archetype ? A.accent : T.accent)
  const size = options.size ?? 320
  const uid = `s${Math.random().toString(36).slice(2, 8)}`
  // Лучи бывают длиннее (до ~1.8 радиуса) — уменьшаем масштаб.
  const path = starPath(160, 168, 80, options.seed)

  if (options.silhouette) {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="${size}" height="${size}" aria-hidden="true">
<defs><radialGradient id="${uid}g" cx="50%" cy="45%" r="60%"><stop offset="0" stop-color="#3a3340"/><stop offset="1" stop-color="#17141b"/></radialGradient></defs>
<path d="${path}" fill="url(#${uid}g)" opacity=".85"/>
<text x="160" y="196" text-anchor="middle" font-family="Manrope, system-ui, sans-serif" font-weight="800" font-size="64" fill="rgba(255,255,255,.22)">?</text>
</svg>`
  }

  const bodyFill =
    archetype === 'chameleon'
      ? `<linearGradient id="${uid}b" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffb3cf"/><stop offset=".25" stop-color="#ffe08a"/><stop offset=".5" stop-color="#a8f0d8"/><stop offset=".75" stop-color="#9fd8ff"/><stop offset="1" stop-color="#d6b8ff"/></linearGradient>`
      : `<radialGradient id="${uid}b" cx="50%" cy="54%" r="62%"><stop offset="0" stop-color="${shade(T.body, 0.18)}"/><stop offset=".62" stop-color="${T.body}"/><stop offset="1" stop-color="${accent}"/></radialGradient>`

  const lidColor = archetype === 'chameleon' ? '#cbb8f5' : shade(T.body, -0.12)
  const lid = Math.max(0, Math.min(1, T.lid))
  const eyeR = 19 * T.eye
  const cheek = archetype === 'chameleon' ? '#ff7fb3' : accent
  const mouthCurve = 4 + T.mouth * 10

  const eye = (cx: number) => `
<g>
<circle cx="${cx}" cy="160" r="${eyeR}" fill="#fff"/>
<circle cx="${cx + 1}" cy="161" r="${eyeR * 0.76}" fill="#1a1320"/>
<circle cx="${cx - 5}" cy="153" r="${eyeR * 0.22}" fill="#fff"/>
<circle cx="${cx + 6}" cy="167" r="${eyeR * 0.1}" fill="#fff"/>
<clipPath id="${uid}c${cx}"><circle cx="${cx}" cy="160" r="${eyeR + 1}"/></clipPath>
<rect x="${cx - eyeR - 2}" y="${160 - eyeR - 2}" width="${eyeR * 2 + 4}" height="${(eyeR * 2 + 4) * lid}" fill="${lidColor}" clip-path="url(#${uid}c${cx})"/>
</g>`

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="${size}" height="${size}" aria-hidden="true">
<defs>
${bodyFill}
<radialGradient id="${uid}h" cx="38%" cy="30%" r="40%"><stop offset="0" stop-color="#fff" stop-opacity=".85"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<radialGradient id="${uid}a" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="${T.glowCol}" stop-opacity=".55"/><stop offset="1" stop-color="${T.glowCol}" stop-opacity="0"/></radialGradient>
</defs>
<circle cx="160" cy="170" r="150" fill="url(#${uid}a)"/>
<path d="${path}" fill="url(#${uid}b)" opacity=".96"/>
<path d="${path}" fill="url(#${uid}h)"/>
${eye(129)}${eye(191)}
<ellipse cx="114" cy="186" rx="10" ry="7" fill="${cheek}" opacity=".45"/>
<ellipse cx="206" cy="186" rx="10" ry="7" fill="${cheek}" opacity=".45"/>
<path d="M150 ${194} Q163 ${194 + mouthCurve} 176 ${194}" stroke="#1a1320" stroke-width="5" fill="none" stroke-linecap="round" transform="rotate(${-T.smirk * 18} 163 194)"/>
<path d="M164 ${196 + mouthCurve * 0.45} l3 7 l3 -7z" fill="#fff"/>
</svg>`
}

// Растеризация SVG в canvas — для карточки сторис без WebGL.
export function rasterizeStar(
  archetype: ArchetypeKey,
  accentKey: ArchetypeKey | null,
  seed?: number | null,
  size = 1080,
): Promise<HTMLCanvasElement> {
  const markup = starSvgMarkup(archetype, accentKey, { size, seed })
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`

  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = canvas.height = size
      canvas.getContext('2d')?.drawImage(img, 0, 0, size, size)
      resolve(canvas)
    }
    img.onerror = () => reject(new Error('SVG rasterization failed'))
    img.src = url
  })
}
