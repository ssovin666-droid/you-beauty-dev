// Уникальная форма звезды пользователя.
//
// Сервер один раз выдаёт shape_seed при открытии персонажа
// (UserCharacter.shape_seed), а форма строится из него
// детерминированно. Порядок вызовов rand() повторяет
// design-reference/character (Cosmi Star, ревью 1).
//
// ВАЖНО: не меняйте порядок и количество вызовов rand() и
// диапазоны — иначе у всех пользователей поменяется форма.
// Новый генератор = новая версия функции и поле версии на бэкенде.

export type Ray = {
  // угол луча (рад), длина, угловая полуширина
  a: number
  L: number
  w: number
}

export type StarShape = {
  seed: number
  rays: Ray[]
  // угол «главного» (верхнего) луча — на него садятся шапки
  A0: number
  wobble: number
}

// Фиксированная форма для капсулы и превью, пока seed ещё не выдан.
export const DEFAULT_SHAPE_SEED = 20261101

// mulberry32: быстрый детерминированный PRNG на 32 битах.
export function mulberry32(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const cache = new Map<number, StarShape>()

export function generateShape(seed: number | null | undefined): StarShape {
  const key = seed && seed > 0 ? Math.floor(seed) : DEFAULT_SHAPE_SEED
  const hit = cache.get(key)
  if (hit) return hit

  const rand = mulberry32(key)
  const RN = [5, 5, 6, 7, 8, 8][Math.floor(rand() * 6)]
  const SP = (2 * Math.PI) / RN
  const A0 = Math.PI / 2 + (rand() - 0.5) * 0.14
  const rays: Ray[] = []

  for (let k = 0; k < RN; k++) {
    // У 8-лучевой звезды каждый второй луч короче и уже.
    const alt = RN === 8 && k % 2 === 1
    const a = A0 + k * SP + (k ? (rand() - 0.5) * SP * 0.26 : 0)
    const L = k === 0
      ? 0.72 + rand() * 0.1
      : alt
        ? 0.34 + rand() * 0.18
        : 0.5 + rand() * 0.36
    const w = SP * (alt ? 0.4 : 0.52) * (0.85 + rand() * 0.3)
    rays.push({ a, L, w })
  }

  const shape: StarShape = { seed: key, rays, A0, wobble: rand() * 6.28 }
  cache.set(key, shape)
  return shape
}

// Радиус силуэта в направлении th.
// f — «насколько это кончик луча» (0..1), s — множитель радиуса.
export function shapeRadius(shape: StarShape, th: number) {
  let best = 0
  let bf = 0
  for (const r of shape.rays) {
    const d = Math.abs(Math.atan2(Math.sin(th - r.a), Math.cos(th - r.a))) / r.w
    if (d < 1) {
      const g = Math.pow(Math.cos((d * Math.PI) / 2), 2.4)
      if (r.L * g > best) {
        best = r.L * g
        bf = g
      }
    }
  }
  return { f: bf, s: 0.96 + 0.025 * Math.sin(3 * th + shape.wobble) + best }
}

// Луч, ближайший к нужному углу (без главного) — для браслета и кольца.
export function nearestRayAngle(shape: StarShape, want: number) {
  const diff = (a: number) => Math.abs(Math.atan2(Math.sin(a - want), Math.cos(a - want)))
  return shape.rays.slice(1).reduce((best, r) => (diff(r.a) < diff(best) ? r.a : best), shape.rays[1].a)
}
