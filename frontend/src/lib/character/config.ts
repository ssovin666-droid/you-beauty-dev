// Справочники персонажа: типы, оттенки полки, предметы, редкость.
// Значения материалов перенесены из design-reference/character
// (Cosmi Star). Ключи совпадают с enum на бэкенде.

export type ShadeKey =
  | 'bold'
  | 'goth'
  | 'nude'
  | 'pastel'
  | 'glow'
  | 'glitter'

export type ArchetypeKey = ShadeKey | 'chameleon'

export type Slot = 'head' | 'eyes' | 'ray' | 'aura'

export type Rarity = 'common' | 'rare' | 'epic' | 'secret'

export type ParticleKind =
  | 'crumb'
  | 'drop'
  | 'powder'
  | 'bow'
  | 'bubble'
  | 'glitter'

export const SHADE_ORDER: ShadeKey[] = [
  'bold',
  'goth',
  'nude',
  'pastel',
  'glow',
  'glitter',
]

export const SHADES: Record<
  ShadeKey,
  {
    label: string
    css: string
    shades: string[]
    kind: ParticleKind
  }
> = {
  bold: { label: 'Яркие', css: '#ff3b30', shades: ['#e3202f', '#ff5236', '#ff2f7a', '#ff7b1c'], kind: 'crumb' },
  goth: { label: 'Тёмные', css: '#241e2a', shades: ['#1a161e', '#4a0f22', '#2c1f40', '#3a0a1a'], kind: 'drop' },
  nude: { label: 'Нюд', css: '#e3b598', shades: ['#e9bfa1', '#d69c7a', '#f2d4bf', '#c48766'], kind: 'powder' },
  pastel: { label: 'Пастель', css: '#ffb3cf', shades: ['#ffb3cc', '#f79cc2', '#ffd0e0', '#e1b4ff'], kind: 'bow' },
  glow: { label: 'Уход', css: 'radial-gradient(circle at 35% 30%,#ffffff,#d6eef8 70%)', shades: ['#eaf7ff', '#fff3df', '#ddf7ee', '#f1eaff'], kind: 'bubble' },
  glitter: { label: 'Блёстки', css: 'linear-gradient(135deg,#f2c75c,#e6b8ff 50%,#9fe3ff)', shades: ['#dcdce8', '#f2c75c', '#b7a2ff', '#9fe3ff'], kind: 'glitter' },
}

// Числовые параметры внешности: прозрачность (tr),
// шероховатость, свечение, иридесценция, лицо.
export type LookParams = {
  body: string
  accent: string
  glowCol: string
  tr: number
  rough: number
  em: number
  irid: number
  sheen: number
  glow: number
  lid: number
  brow: number
  browR: number
  mouth: number
  smirk: number
  eye: number
}

export const ARCHETYPES: Record<
  ArchetypeKey,
  LookParams & {
    name: string
    caption: string
    rare?: boolean
  }
> = {
  bold: { name: 'Bold', caption: 'красная помада — это не про губы, это про власть', body: '#ff5240', accent: '#ff2a4d', glowCol: '#ff7a5c', tr: 0.82, rough: 0.07, em: 0.14, irid: 0, sheen: 0, glow: 0.55, lid: 0.24, brow: 0.4, browR: 0, mouth: 0.45, smirk: 0.3, eye: 1 },
  goth: { name: 'Гот', caption: 'чёрная подводка — это не макияж, это позиция', body: '#221d29', accent: '#9b5cff', glowCol: '#8a4dff', tr: 0.62, rough: 0.1, em: 0.03, irid: 0.45, sheen: 1, glow: 0.45, lid: 0.56, brow: 0.12, browR: 0, mouth: 0.1, smirk: 0.14, eye: 1 },
  nude: { name: 'Clean girl', caption: 'выгляжу так, будто сплю по восемь часов. не сплю', body: '#f7d5c2', accent: '#e9a07a', glowCol: '#ffc9a8', tr: 0.55, rough: 0.26, em: 0.1, irid: 0, sheen: 0.3, glow: 0.4, lid: 0.26, brow: -0.05, browR: 0, mouth: 0.42, smirk: 0.05, eye: 0.98 },
  pastel: { name: 'Coquette', caption: 'бантик — это не аксессуар, это мировоззрение', body: '#ffbcd5', accent: '#ff6fa6', glowCol: '#ff9cc4', tr: 0.8, rough: 0.09, em: 0.12, irid: 0.15, sheen: 0.4, glow: 0.5, lid: 0.06, brow: -0.18, browR: 0, mouth: 0.62, smirk: 0.06, eye: 1.1 },
  glow: { name: 'Glow', caption: 'не потная, а сияющая. разница принципиальная', body: '#f2f9ff', accent: '#9ff2ff', glowCol: '#c9f6ff', tr: 1, rough: 0.03, em: 0.42, irid: 0.12, sheen: 0, glow: 0.95, lid: 0.14, brow: -0.08, browR: 0, mouth: 0.4, smirk: 0.02, eye: 1.02 },
  glitter: { name: 'Disco', caption: 'если меня не видно из космоса — зачем вообще краситься', body: '#d8cfff', accent: '#ffd36b', glowCol: '#b99cff', tr: 0.88, rough: 0.05, em: 0.16, irid: 1, sheen: 0, glow: 0.7, lid: 0, brow: 0.18, browR: 0, mouth: 0.72, smirk: 0.18, eye: 1.08 },
  chameleon: { name: 'Хамелеон', caption: 'у меня нет стиля. у меня их все', body: '#ffffff', accent: '#ffffff', glowCol: '#c7b3ff', tr: 0.85, rough: 0.06, em: 0.14, irid: 0.7, sheen: 0, glow: 0.7, lid: 0.1, brow: 0, browR: 0.34, mouth: 0.5, smirk: 0.34, eye: 1.04, rare: true },
}

export const SLOTS: { key: Slot; label: string; icon: string }[] = [
  { key: 'head', label: 'Голова', icon: '◠' },
  { key: 'eyes', label: 'Глаза', icon: '◉' },
  { key: 'ray', label: 'Луч', icon: '✦' },
  { key: 'aura', label: 'Аура', icon: '✧' },
]

export const RARITY: Record<
  Rarity,
  {
    label: string
    color: string
    // Рамка (всегда градиент — рисуется через border-box) и свечение.
    frame: string
    glow: string
  }
> = {
  common: { label: 'обычный', color: '#8f8a95', frame: 'linear-gradient(135deg,#d9d4dc,#b9b3be)', glow: 'rgba(160,155,170,.35)' },
  rare: { label: 'редкий', color: '#5b7cff', frame: 'linear-gradient(135deg,#9fb6ff,#5b7cff)', glow: 'rgba(91,124,255,.45)' },
  epic: { label: 'эпический', color: '#b84dff', frame: 'linear-gradient(135deg,#e39bff,#9d3dff)', glow: 'rgba(184,77,255,.5)' },
  secret: { label: 'секретный', color: '#e09a00', frame: 'linear-gradient(135deg,#ffd36b,#ff8fc0,#9fd8ff)', glow: 'rgba(255,200,80,.6)' },
}

export const RARITY_ORDER: Rarity[] = ['common', 'rare', 'epic', 'secret']

// Иконка предмета в UI (2D): CSS-заливка «капли».
export const ITEM_SWATCH: Record<string, string> = {
  clip: 'radial-gradient(circle at 30% 30%,#9adf8f,#2f9a4c 45%,#0f5a28)',
  bow: 'linear-gradient(135deg,#ffc2da,#ff6fa6)',
  beanie: '#8fd6c0',
  crown: 'linear-gradient(135deg,#ffe08a,#f2b035)',
  glasses: '#111114',
  heart_glasses: 'linear-gradient(135deg,#ff3b6b,#ff9cc4)',
  bracelet: 'conic-gradient(#ff5236,#ffb3cc,#b7a2ff,#9fe3ff,#ff5236)',
  ring: 'linear-gradient(135deg,#fff1b8,#f2b035 60%,#ff5fa2)',
  halo: 'radial-gradient(circle,#fffbe6 30%,#ffe08a 55%,#f6c453)',
  dust: 'radial-gradient(circle,#fff6c9,#ffd36b 45%,#b99cff)',
}

export function itemSwatch(code: string) {
  return ITEM_SWATCH[code] ?? '#d9d4dc'
}

// Распределение полки → список «частиц» для тела звезды.
// Ограничиваем количество ради производительности.
export function shelfParticles(
  distribution: Partial<Record<ShadeKey, number>>,
  max = 12,
): { group: ShadeKey; shade: string }[] {
  const entries = SHADE_ORDER
    .map(key => [key, distribution[key] ?? 0] as const)
    .filter(([, count]) => count > 0)

  const total = entries.reduce((sum, [, count]) => sum + count, 0)
  if (total === 0) return []

  const scale = Math.min(1, max / total)
  const out: { group: ShadeKey; shade: string }[] = []

  entries.forEach(([key, count]) => {
    const n = Math.max(1, Math.round(count * scale))
    for (let i = 0; i < n; i++) {
      out.push({ group: key, shade: SHADES[key].shades[i % 4] })
    }
  })

  return out.slice(0, max)
}

export function pluralItems(n: number) {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return 'товар'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'товара'
  return 'товаров'
}
