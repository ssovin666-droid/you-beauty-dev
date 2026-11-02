// Cosmi Star — 3D-сцена без React.
// Перенос design-reference/character/Cosmi Star.dc.html (ревью 1):
// та же геометрия (сфера → звезда с уникальной для пользователя
// формой, см. shape.ts), материал
// (transmission + clearcoat + iridescence), лицо, частицы-косметика,
// аксессуары и анимации. React-обёртка — components/character/CosmiStar.tsx.

import * as THREE from 'three'

import {
  ARCHETYPES,
  SHADES,
  type ArchetypeKey,
  type ParticleKind,
  type ShadeKey,
  type Slot,
} from './config'
import {
  generateShape,
  nearestRayAngle,
  shapeRadius,
  type StarShape,
} from './shape'

export type StarSceneOptions = {
  interactive?: boolean
  stage?: string
  quality?: 'high' | 'low'
  maxDpr?: number
  eyesFollow?: boolean
  // Seed формы звезды пользователя (UserCharacter.shape_seed).
  shapeSeed?: number | null
  // Насколько отодвинуть камеру (1 — как в референсе).
  zoom?: number
  // Сдвиг камеры по Y: отрицательный поднимает персонажа в кадре.
  cameraY?: number
  onTap?: () => void
  onFirstDrag?: () => void
  // Средняя длительность кадра за первые ~2 c (мс).
  onPerfSample?: (avgFrameMs: number) => void
  onContextLost?: () => void
  // Режим капсулы (design-reference «Cosmi Capsule»): персонаж
  // тёмным силуэтом внутри перламутровой капсулы, открытие —
  // заряд → взрыв половинок → конфетти → проявление персонажа.
  capsule?: boolean
  // Половинки капсулы разлетелись (вспышка) — момент для хаптика.
  onCapsuleBurst?: () => void
  // Персонаж проявился и открыл глаза — можно показывать плашку типа.
  onCapsuleRevealed?: () => void
}

export type CapsulePhase = 'locked' | 'ready'

type CapPhase = 'none' | 'locked' | 'ready' | 'charge' | 'burst' | 'done'

type Confetti = {
  mesh: THREE.Mesh
  vel: THREE.Vector3
  spin: THREE.Vector3
  size: number
  life: number
  max: number
}

const CAPSULE_R = 1.62
const CAPSULE_H = 0.3
const CHARGE_SEC = 1.25
const STAR_IN_CAPSULE = 0.66

const springOut = (x: number) => (x <= 0 ? 0 : 1 - Math.exp(-5.5 * x) * Math.cos(11 * x))
const sstep = (a: number, b: number, x: number) => {
  const u = Math.max(0, Math.min(1, (x - a) / (b - a)))
  return u * u * (3 - 2 * u)
}

type LookState = {
  body: THREE.Color
  accent: THREE.Color
  glowCol: THREE.Color
  bg: THREE.Color
  tr: number
  rough: number
  em: number
  irid: number
  sheen: number
  glow: number
  rainbow: number
  purple: number
  lid: number
  brow: number
  browR: number
  mouth: number
  smirk: number
  eye: number
  evo: number
}

const NUM_KEYS = [
  'tr', 'rough', 'em', 'irid', 'sheen', 'glow', 'rainbow', 'purple',
  'lid', 'brow', 'browR', 'mouth', 'smirk', 'eye', 'evo',
] as const

type Particle = {
  mesh: THREE.Object3D
  mat: THREE.Material
  base: THREE.Vector3
  size: number
  s: number
  ph: number
  sp: number
  amp: number
  spin: THREE.Vector3
  dying: boolean
}

type Accessory = { g: THREE.Group; s: number; t: number }

type BurstBit = {
  mesh: THREE.Mesh
  vel: THREE.Vector3
  life: number
  size: number
}

const BASE_Z = 10.6
const EX = 0.31
const EY = 0.12
const MAX_SATELLITES = 5

// Текстура «черепахового» ацетата для заколки-краба (как в референсе).
function tortoiseTexture() {
  const cv = document.createElement('canvas')
  cv.width = cv.height = 256
  const c2 = cv.getContext('2d')
  if (c2) {
    c2.fillStyle = '#1f7a3a'
    c2.fillRect(0, 0, 256, 256)
    const greens = ['#0f5a28', '#2f9a4c', '#58c26e', '#9adf8f', '#0b4420', '#c9d98a']
    for (let k = 0; k < 90; k++) {
      c2.fillStyle = greens[k % greens.length]
      c2.globalAlpha = 0.35 + Math.random() * 0.5
      c2.beginPath()
      const x = Math.random() * 256
      const y = Math.random() * 256
      const r = 6 + Math.random() * 26
      c2.moveTo(x + r, y)
      for (let q = 1; q <= 6; q++) {
        const a = (q / 6) * Math.PI * 2
        const rr = r * (0.55 + Math.random() * 0.6)
        c2.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr)
      }
      c2.fill()
    }
  }
  const tex = new THREE.CanvasTexture(cv)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  return tex
}

function makeLook(): LookState {
  const C = (h: string) => new THREE.Color(h)
  return {
    body: C('#ff5240'), accent: C('#ff2a4d'), glowCol: C('#ffffff'), bg: C('#ebe6e1'),
    tr: 0.8, rough: 0.08, em: 0.1, irid: 0, sheen: 0, glow: 0.5, rainbow: 0, purple: 0,
    lid: 0.2, brow: 0, browR: 0, mouth: 0.5, smirk: 0, eye: 1, evo: 0,
  }
}

function starShape(outer: number, inner: number) {
  const shape = new THREE.Shape()
  for (let i = 0; i < 10; i++) {
    const r = i % 2 === 0 ? outer : inner
    const a = Math.PI / 2 + (i * Math.PI) / 5
    const x = Math.cos(a) * r
    const y = Math.sin(a) * r
    if (i === 0) shape.moveTo(x, y)
    else shape.lineTo(x, y)
  }
  shape.closePath()
  return shape
}

function heartShape(scale: number) {
  const s = scale
  const shape = new THREE.Shape()
  shape.moveTo(0, -0.9 * s)
  shape.bezierCurveTo(-0.15 * s, -0.7 * s, -1.0 * s, -0.25 * s, -1.0 * s, 0.25 * s)
  shape.bezierCurveTo(-1.0 * s, 0.75 * s, -0.4 * s, 0.95 * s, 0, 0.5 * s)
  shape.bezierCurveTo(0.4 * s, 0.95 * s, 1.0 * s, 0.75 * s, 1.0 * s, 0.25 * s)
  shape.bezierCurveTo(1.0 * s, -0.25 * s, 0.15 * s, -0.7 * s, 0, -0.9 * s)
  return shape
}

export class StarScene {
  readonly canvas: HTMLCanvasElement

  private host: HTMLElement
  private opts: StarSceneOptions
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100)
  private zoom: number
  private shape: StarShape
  private textures: THREE.Texture[] = []

  private root = new THREE.Group()
  private star = new THREE.Group()
  private auraGroup = new THREE.Group()
  private pGroup = new THREE.Group()
  private burstGroup = new THREE.Group()

  private bodyMat!: THREE.MeshPhysicalMaterial
  private bgMat!: THREE.ShaderMaterial
  private lidMat!: THREE.MeshPhysicalMaterial
  private cheekMat!: THREE.MeshBasicMaterial
  private goldMat!: THREE.MeshStandardMaterial
  private body!: THREE.Mesh
  private vcol!: THREE.BufferAttribute
  private tipF!: Float32Array
  private rainbow!: Float32Array
  private vertexCount = 0

  private eyes: { g: THREE.Group; iris: THREE.Group; lid: THREE.Mesh }[] = []
  private brows: THREE.Mesh[] = []
  private mouth = new THREE.Group()
  private mouthZ = 0
  private fang!: THREE.Mesh
  private purple!: THREE.PointLight
  private purple2!: THREE.PointLight

  private particles: Particle[] = []
  private shelfSlots: { group: ShadeKey; density: number; parts: Particle[] }[] = []
  private particleGeo: Record<string, THREE.BufferGeometry> = {}
  private acc: Record<string, Accessory> = {}
  private beads: THREE.Mesh[] = []
  private satellites: THREE.Mesh[] = []
  private burst: BurstBit[] = []
  private burstColors: THREE.Color[] = [new THREE.Color('#ffffff')]

  private cur = makeLook()
  private tgt = makeLook()
  private lastType: ArchetypeKey | null = null
  private firstLook = true
  private colorsDirty = true
  private squash = 0
  private intro = 1

  // интеракция
  private rotY = 0
  private rotX = 0
  private velY = 0
  private velX = 0
  private dragging = false
  private dragged = false
  private lastX = 0
  private lastY = 0
  private downX = 0
  private downY = 0
  private downAt = 0
  private idleT = 0
  private gx = 0
  private gy = 0
  private gcx = 0
  private gcy = 0

  // цикл
  private raf = 0
  private running = false
  private disposed = false
  private t = 0
  private lastFrame = 0
  private nextBlink = 2
  private blinkStart = -10
  private perfFrames = 0
  private perfTotal = 0
  private perfReported = false
  private ro: ResizeObserver

  private tmpColor = new THREE.Color()
  private emColor = new THREE.Color()
  private srgb = new THREE.Color()
  private white = new THREE.Color('#ffffff')
  private violet = new THREE.Color('#9b5cff')
  private cham = new THREE.Color('#d9c8ff')
  private cheekPink = new THREE.Color('#ff7fb3')

  // лицо целиком — прячем, пока персонаж внутри капсулы
  private faceParts: THREE.Object3D[] = []
  private camZ = BASE_Z

  // капсула
  private capPhase: CapPhase = 'none'
  private capPt = 0
  private capHop = 0
  private capProgress = 0
  private capSpeed = 1
  private capSpinY = 0
  private capZ = 1
  private capGlowMix = 0
  private capRevealSent = false
  private cap = new THREE.Group()
  private capTop = new THREE.Group()
  private capBot = new THREE.Group()
  private capTopMat!: THREE.MeshPhysicalMaterial
  private capSeamMat!: THREE.MeshPhysicalMaterial
  private capLight!: THREE.PointLight
  private capSparks: THREE.Mesh[] = []
  private capGlow!: THREE.Sprite
  private raysMat!: THREE.ShaderMaterial
  private rays!: THREE.Mesh
  private flashMat!: THREE.MeshBasicMaterial
  private confGeo: THREE.BufferGeometry[] = []
  private confetti: Confetti[] = []
  private topV = new THREE.Vector3()
  private botV = new THREE.Vector3()
  private topSpin = new THREE.Vector3()
  private botSpin = new THREE.Vector3()
  private capDark = new THREE.Color('#2a2430')
  private capLavender = new THREE.Color('#e6dcf7')
  private glowMixColor = new THREE.Color()

  constructor(host: HTMLElement, opts: StarSceneOptions = {}) {
    this.host = host
    this.opts = opts
    this.zoom = opts.zoom ?? 1
    this.shape = generateShape(opts.shapeSeed)

    const quality = opts.quality ?? 'high'

    this.renderer = new THREE.WebGLRenderer({
      antialias: quality === 'high',
      powerPreference: 'low-power',
      failIfMajorPerformanceCaveat: true,
    })
    this.renderer.setPixelRatio(
      Math.min(window.devicePixelRatio || 1, opts.maxDpr ?? 2),
    )
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping

    this.canvas = this.renderer.domElement
    this.canvas.style.cssText =
      'width:100%;height:100%;display:block;touch-action:none;'
    if (opts.interactive) this.canvas.style.cursor = 'grab'
    host.appendChild(this.canvas)

    this.camera.position.set(0, opts.cameraY ?? -0.45, BASE_Z * this.zoom)

    this.buildEnvironment()
    this.buildBody(quality === 'high' ? 128 : 80)
    this.buildFace()
    this.buildParticleGeometry()
    this.buildAccessories()
    this.buildSatellites()
    this.buildBurst()

    this.scene.add(this.root)
    this.root.add(this.star)
    this.root.add(this.burstGroup)
    this.star.add(this.pGroup)
    this.scene.add(this.auraGroup)
    // камера в сцене — к ней прикреплена плоскость вспышки
    this.scene.add(this.camera)

    if (opts.capsule) {
      this.buildCapsule()
      this.capPhase = 'locked'
    }

    this.canvas.addEventListener('webglcontextlost', this.handleContextLost)

    if (opts.interactive || opts.capsule) {
      this.canvas.addEventListener('pointerdown', this.onDown)
      this.canvas.addEventListener('pointermove', this.onDrag)
      this.canvas.addEventListener('pointerup', this.onUp)
      this.canvas.addEventListener('pointercancel', this.onUp)
    }
    window.addEventListener('pointermove', this.onLook)

    this.ro = new ResizeObserver(() => this.resize())
    this.ro.observe(host)
    this.resize()

    this.setStage(opts.stage ?? '#ebe6e1')
  }

  // -------------------------
  // BUILD
  // -------------------------

  private buildEnvironment() {
    const { renderer, scene } = this

    // Студийное окружение из светящихся панелей (как в референсе).
    const pmrem = new THREE.PMREMGenerator(renderer)
    const env = new THREE.Scene()
    env.background = new THREE.Color(0x2a2830)
    const panel = (w: number, h: number, p: [number, number, number], intensity: number, col: number = 0xffffff) => {
      const mesh = new THREE.Mesh(
        new THREE.PlaneGeometry(w, h),
        new THREE.MeshBasicMaterial({
          color: new THREE.Color(col).multiplyScalar(intensity),
          side: THREE.DoubleSide,
        }),
      )
      mesh.position.set(...p)
      mesh.lookAt(0, 0, 0)
      env.add(mesh)
    }
    panel(8, 3, [0, 7, 3], 5)
    panel(2.5, 9, [-7, 1, 4], 3.2)
    panel(2.5, 9, [7, 0, 3], 2.4, 0xfff0f6)
    panel(10, 3, [0, -6, 1], 1, 0xe6eeff)
    panel(6, 6, [0, 3, -8], 1.6)
    scene.environment = pmrem.fromScene(env, 0.03).texture
    env.traverse(obj => {
      if (obj instanceof THREE.Mesh) {
        obj.geometry.dispose()
        ;(obj.material as THREE.Material).dispose()
      }
    })
    pmrem.dispose()

    const key = new THREE.DirectionalLight(0xffffff, 1.2)
    key.position.set(-2, 3, 5)
    scene.add(key)

    this.purple = new THREE.PointLight(0x9b5cff, 0, 10)
    this.purple.position.set(1.5, 1.2, -2)
    this.purple2 = new THREE.PointLight(0xb070ff, 0, 10)
    this.purple2.position.set(-2, -1, 2)
    scene.add(this.purple, this.purple2)

    // Фон: цвет сцены + мягкое свечение цвета персонажа + дизеринг.
    this.bgMat = new THREE.ShaderMaterial({
      uniforms: {
        uBg: { value: new THREE.Vector3(0.92, 0.9, 0.88) },
        uGlow: { value: new THREE.Vector3(1, 1, 1) },
        uAmt: { value: 0.5 },
      },
      vertexShader:
        'varying vec2 vP; void main(){ vP=position.xy; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
      fragmentShader:
        'uniform vec3 uBg; uniform vec3 uGlow; uniform float uAmt; varying vec2 vP;' +
        'float h(vec2 p){return fract(sin(dot(p,vec2(12.9898,78.233)))*43758.5453);}' +
        'void main(){ vec2 p=vP-vec2(0.0,0.2); float g=exp(-dot(p,p)/(2.0*1.6*1.6));' +
        'vec3 c=mix(uBg,uGlow,clamp(g*uAmt,0.0,1.0)); c+=(h(gl_FragCoord.xy)-0.5)/255.0; gl_FragColor=vec4(c,1.0); }',
      depthWrite: false,
      toneMapped: false,
    })
    const bg = new THREE.Mesh(new THREE.PlaneGeometry(80, 80), this.bgMat)
    bg.position.z = -5
    scene.add(bg)
  }

  private buildBody(segments: number) {
    const geo = new THREE.SphereGeometry(1, segments, segments)
    const pos = geo.attributes.position as THREE.BufferAttribute
    const n = pos.count
    this.vertexCount = n
    this.tipF = new Float32Array(n)
    this.rainbow = new Float32Array(n * 3)
    const c = new THREE.Color()

    for (let i = 0; i < n; i++) {
      const x = pos.getX(i)
      const y = pos.getY(i)
      const z = pos.getZ(i)
      const rho = Math.hypot(x, y)
      const th = Math.atan2(y, x)
      const { f, s } = shapeRadius(this.shape, th)
      const thickness = 0.68 - 0.18 * f * rho
      pos.setXYZ(i, x * s, y * s, z * thickness)
      this.tipF[i] = Math.pow(f, 4) * Math.pow(rho, 3)
      c.setHSL(((th / (2 * Math.PI) + 0.5) + y * 0.12 + z * 0.1 + 1) % 1, 0.85, 0.66)
      this.rainbow[i * 3] = c.r
      this.rainbow[i * 3 + 1] = c.g
      this.rainbow[i * 3 + 2] = c.b
    }

    geo.computeVertexNormals()

    // Сглаживаем нормали на шве UV-сферы.
    const nrm = geo.attributes.normal as THREE.BufferAttribute
    const merged = new Map<string, [number, number, number, number[]]>()
    for (let i = 0; i < n; i++) {
      const k = `${Math.round(pos.getX(i) * 1e4)},${Math.round(pos.getY(i) * 1e4)},${Math.round(pos.getZ(i) * 1e4)}`
      let a = merged.get(k)
      if (!a) {
        a = [0, 0, 0, []]
        merged.set(k, a)
      }
      a[0] += nrm.getX(i)
      a[1] += nrm.getY(i)
      a[2] += nrm.getZ(i)
      a[3].push(i)
    }
    merged.forEach(a => {
      const l = Math.hypot(a[0], a[1], a[2]) || 1
      a[3].forEach(i => nrm.setXYZ(i, a[0] / l, a[1] / l, a[2] / l))
    })

    this.vcol = new THREE.BufferAttribute(new Float32Array(n * 3), 3)
    geo.setAttribute('color', this.vcol)

    this.bodyMat = new THREE.MeshPhysicalMaterial({
      vertexColors: true,
      color: 0xffffff,
      transmission: 0.9,
      thickness: 1.3,
      roughness: 0.08,
      ior: 1.4,
      clearcoat: 1,
      clearcoatRoughness: 0.05,
      iridescence: 0,
      iridescenceIOR: 1.5,
      iridescenceThicknessRange: [200, 600],
      sheen: 0,
      sheenColor: new THREE.Color('#9b5cff'),
      sheenRoughness: 0.35,
      emissive: new THREE.Color(0xffffff),
      emissiveIntensity: 0.1,
      attenuationColor: new THREE.Color(1, 1, 1),
      attenuationDistance: 3,
      specularIntensity: 1,
    })

    this.body = new THREE.Mesh(geo, this.bodyMat)
    this.star.add(this.body)
    this.star.updateMatrixWorld(true)
  }

  private raycaster = new THREE.Raycaster()

  private hitZ(x: number, y: number): number | null {
    this.raycaster.set(new THREE.Vector3(x, y, 5), new THREE.Vector3(0, 0, -1))
    const hit = this.raycaster.intersectObject(this.body, false)
    return hit.length ? hit[0].point.z : null
  }

  private surfZ(x: number, y: number) {
    return this.hitZ(x, y) ?? 0.5
  }

  // Длина луча в направлении a (до края тела).
  private tipR(a: number) {
    let r = 0.8
    while (r < 3 && this.hitZ(Math.cos(a) * r, Math.sin(a) * r) !== null) r += 0.01
    return r
  }

  // Сечение луча на расстоянии r: центр, полуширина, смещение центра, толщина.
  private rayFit(a: number, r: number) {
    const c = new THREE.Vector2(Math.cos(a) * r, Math.sin(a) * r)
    const v = new THREE.Vector2(-Math.sin(a), Math.cos(a))
    const side = (sign: number) => {
      let w = 0
      while (w < 1 && this.hitZ(c.x + v.x * w * sign, c.y + v.y * w * sign) !== null) w += 0.005
      return w
    }
    const plus = side(1)
    const minus = side(-1)
    return { c, w: (plus + minus) / 2, off: (plus - minus) / 2, d: this.surfZ(c.x, c.y) }
  }

  // Шапка/корона садится на главный луч там, где он достаточно широкий.
  private fitHat(g: THREE.Group, a: number, want: number, tilt: number) {
    const tip = this.tipR(a)
    let r = tip - 0.1
    let f = this.rayFit(a, r)
    while (r > 0.9 && f.w < want) {
      r -= 0.02
      f = this.rayFit(a, r)
    }
    const v = new THREE.Vector2(-Math.sin(a), Math.cos(a))
    g.position.set(f.c.x + v.x * f.off, f.c.y + v.y * f.off, 0)
    g.rotation.z = a - Math.PI / 2 + tilt
    return f
  }

  // Переносит детей группы во вложенную группу (для масштабирования по лучу).
  private wrapChildren(g: THREE.Group) {
    const inner = new THREE.Group()
    while (g.children.length) inner.add(g.children[0])
    g.add(inner)
    return inner
  }

  private buildFace() {
    const ink = new THREE.MeshPhysicalMaterial({ color: '#1a1320', roughness: 0.25, clearcoat: 1, clearcoatRoughness: 0.1 })
    const white = new THREE.MeshPhysicalMaterial({ color: '#ffffff', roughness: 0.25, clearcoat: 1 })
    const highlight = new THREE.MeshBasicMaterial({ color: '#ffffff' })
    this.lidMat = new THREE.MeshPhysicalMaterial({ color: '#ff5240', roughness: 0.2, clearcoat: 1, side: THREE.DoubleSide })

    this.eyes = [-1, 1].map(sd => {
      const g = new THREE.Group()
      g.position.set(sd * EX, EY, this.surfZ(sd * EX, EY) - 0.04)
      g.scale.set(1, 1, 0.5)
      g.add(new THREE.Mesh(new THREE.SphereGeometry(0.2, 32, 24), white))

      const iris = new THREE.Group()
      const irisMesh = new THREE.Mesh(new THREE.SphereGeometry(0.152, 32, 24), ink)
      irisMesh.position.z = 0.07
      iris.add(irisMesh)
      g.add(iris)

      const h1 = new THREE.Mesh(new THREE.SphereGeometry(0.04, 16, 12), highlight)
      h1.position.set(-0.05, 0.065, 0.225)
      const h2 = new THREE.Mesh(new THREE.SphereGeometry(0.018, 12, 8), highlight)
      h2.position.set(0.06, -0.05, 0.215)
      g.add(h1, h2)

      const lid = new THREE.Mesh(
        new THREE.SphereGeometry(0.213, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2),
        this.lidMat,
      )
      g.add(lid)
      this.star.add(g)
      this.faceParts.push(g)
      return { g, iris, lid }
    })

    const browGeo = new THREE.CapsuleGeometry(0.024, 0.13, 4, 10)
    this.brows = [-1, 1].map(sd => {
      const m = new THREE.Mesh(browGeo, ink)
      m.position.set(sd * 0.31, 0.43, this.surfZ(sd * 0.31, 0.43) + 0.005)
      m.userData.sd = sd
      this.star.add(m)
      this.faceParts.push(m)
      return m
    })

    this.mouthZ = this.surfZ(0.03, -0.2)
    this.mouth.position.set(0.03, -0.2, this.mouthZ + 0.008)
    const arc = new THREE.Mesh(new THREE.TorusGeometry(0.075, 0.019, 8, 28, Math.PI), ink)
    arc.rotation.z = Math.PI
    this.mouth.add(arc)
    this.star.add(this.mouth)

    this.fang = new THREE.Mesh(new THREE.ConeGeometry(0.026, 0.065, 14), white)
    this.fang.rotation.z = Math.PI
    this.star.add(this.fang)
    this.faceParts.push(this.mouth, this.fang)

    this.cheekMat = new THREE.MeshBasicMaterial({ color: '#ff6fa6', transparent: true, opacity: 0.5, depthWrite: false })
    ;[-1, 1].forEach(sd => {
      const m = new THREE.Mesh(new THREE.CircleGeometry(0.085, 28), this.cheekMat)
      m.position.set(sd * 0.5, -0.1, this.surfZ(sd * 0.5, -0.1) + 0.012)
      m.rotation.y = sd * 0.3
      m.scale.set(1.15, 0.8, 1)
      this.star.add(m)
      this.faceParts.push(m)
    })
  }

  private buildParticleGeometry() {
    this.particleGeo = {
      cone: new THREE.ConeGeometry(0.05, 0.09, 12),
      knot: new THREE.SphereGeometry(0.024, 10, 8),
      crumb: new THREE.DodecahedronGeometry(0.05),
      drop: new THREE.SphereGeometry(0.05, 16, 12),
      powder: new THREE.SphereGeometry(0.04, 12, 10),
      bubble: new THREE.SphereGeometry(0.058, 16, 12),
      glitter: new THREE.CylinderGeometry(0.05, 0.05, 0.01, 6),
    }
  }

  private spawnParticle(group: ShadeKey, shade: string): Particle {
    const kind: ParticleKind = SHADES[group].kind
    const G = this.particleGeo
    const col = new THREE.Color(shade)
    let mesh: THREE.Object3D
    let mat: THREE.Material

    if (kind === 'bow') {
      mat = new THREE.MeshStandardMaterial({ color: col, roughness: 0.35 })
      const g = new THREE.Group()
      const l = new THREE.Mesh(G.cone, mat)
      l.rotation.z = -Math.PI / 2
      l.position.x = -0.045
      const r = new THREE.Mesh(G.cone, mat)
      r.rotation.z = Math.PI / 2
      r.position.x = 0.045
      g.add(l, r, new THREE.Mesh(G.knot, mat))
      mesh = g
    } else if (kind === 'crumb') {
      mat = new THREE.MeshStandardMaterial({ color: col, roughness: 0.5 })
      mesh = new THREE.Mesh(G.crumb, mat)
    } else if (kind === 'drop') {
      mat = new THREE.MeshPhysicalMaterial({ color: col, roughness: 0.05, clearcoat: 1 })
      mesh = new THREE.Mesh(G.drop, mat)
    } else if (kind === 'powder') {
      mat = new THREE.MeshStandardMaterial({ color: col, roughness: 0.9 })
      mesh = new THREE.Mesh(G.powder, mat)
    } else if (kind === 'bubble') {
      mat = new THREE.MeshPhysicalMaterial({ color: col, roughness: 0, clearcoat: 1, emissive: col, emissiveIntensity: 0.8 })
      mesh = new THREE.Mesh(G.bubble, mat)
    } else {
      mat = new THREE.MeshStandardMaterial({ color: col, metalness: 1, roughness: 0.15, emissive: col, emissiveIntensity: 0.3 })
      mesh = new THREE.Mesh(G.glitter, mat)
    }

    // Случайная точка внутри тела звезды.
    const th = Math.random() * Math.PI * 2
    const rho = Math.sqrt(Math.random()) * 0.82
    const { f, s } = shapeRadius(this.shape, th)
    const zmax = (0.68 - 0.18 * f * rho) * Math.sqrt(Math.max(0, 1 - rho * rho)) * 0.55
    const base = new THREE.Vector3(
      Math.cos(th) * rho * s * 0.82,
      Math.sin(th) * rho * s * 0.82,
      (Math.random() * 2 - 1) * zmax - 0.05,
    )

    mesh.rotation.set(Math.random() * 6, Math.random() * 6, Math.random() * 6)
    mesh.scale.setScalar(0.001)
    this.pGroup.add(mesh)

    const p: Particle = {
      mesh,
      mat,
      base,
      size: (kind === 'bow' ? 1.15 : 1) * (0.75 + Math.random() * 0.5),
      s: 0,
      ph: Math.random() * 6.28,
      sp: 0.3 + Math.random() * 0.5,
      amp: 0.03 + Math.random() * 0.05,
      spin: new THREE.Vector3(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5)
        .multiplyScalar(kind === 'glitter' ? 2.4 : 0.8),
      dying: false,
    }
    this.particles.push(p)
    return p
  }

  private addAccessory(id: string, g: THREE.Group, parent: THREE.Object3D = this.star) {
    g.scale.setScalar(0.001)
    g.visible = false
    parent.add(g)
    this.acc[id] = { g, s: 0, t: 0 }
  }

  private buildAccessories() {
    this.goldMat = new THREE.MeshStandardMaterial({
      color: '#f6c453', metalness: 1, roughness: 0.2,
      emissive: '#ff9d00', emissiveIntensity: 0.15, side: THREE.DoubleSide,
    })
    const gold = this.goldMat

    const A0 = this.shape.A0

    // --- head: crown (secret) — подгоняется под ширину главного луча
    {
      const g = new THREE.Group()
      const fit = this.fitHat(g, A0, 0.2, -0.12)
      g.add(new THREE.Mesh(new THREE.CylinderGeometry(0.27, 0.24, 0.13, 40, 1, true), gold))
      const gem = new THREE.MeshStandardMaterial({ color: '#ff5fa2', emissive: '#ff2f86', emissiveIntensity: 0.6, roughness: 0.1 })
      for (let k = 0; k < 5; k++) {
        const a = (k / 5) * Math.PI * 2
        const c = new THREE.Mesh(new THREE.ConeGeometry(0.05, 0.16, 12), gold)
        c.position.set(Math.cos(a) * 0.26, 0.14, Math.sin(a) * 0.26)
        const gm = new THREE.Mesh(new THREE.SphereGeometry(0.034, 12, 10), gem)
        gm.position.set(Math.cos(a) * 0.26, 0.24, Math.sin(a) * 0.26)
        g.add(c, gm)
      }
      const sparks = new THREE.Group()
      const sparkMat = new THREE.MeshBasicMaterial({ color: '#fff3c4', toneMapped: false })
      for (let k = 0; k < 6; k++) {
        const m = new THREE.Mesh(new THREE.OctahedronGeometry(0.04), sparkMat)
        m.scale.set(0.5, 1.3, 0.5)
        m.userData.a = (k / 6) * Math.PI * 2
        sparks.add(m)
      }
      g.add(sparks)
      const light = new THREE.PointLight(0xffc04d, 2.5, 3)
      light.position.set(0, 0.2, 0.3)
      g.add(light)
      const inner = this.wrapChildren(g)
      inner.scale.set(fit.w / 0.235, 1, Math.max(fit.d, 0.15) / 0.235)
      inner.position.y = -0.02
      g.userData.sparks = sparks
      this.addAccessory('crown', g)
    }

    // --- head: beanie (rare) — натянута на главный луч
    {
      const g = new THREE.Group()
      const tip = this.tipR(A0)
      const r = Math.max(tip - 0.32, 1)
      const fit = this.rayFit(A0, r)
      const v = new THREE.Vector2(-Math.sin(A0), Math.cos(A0))
      g.position.set(fit.c.x + v.x * fit.off, fit.c.y + v.y * fit.off, 0)
      g.rotation.z = A0 - Math.PI / 2 + 0.1
      const knit = new THREE.MeshStandardMaterial({ color: '#8fd6c0', roughness: 0.95 })
      const dome = new THREE.Mesh(new THREE.SphereGeometry(0.34, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2), knit)
      dome.scale.set(1, 1.05, 0.66)
      const brim = new THREE.Mesh(new THREE.TorusGeometry(0.33, 0.07, 12, 40), knit)
      brim.rotation.x = Math.PI / 2
      brim.scale.set(1, 0.66, 1)
      const pom = new THREE.Mesh(new THREE.SphereGeometry(0.11, 20, 16), new THREE.MeshStandardMaterial({ color: '#ffd0e4', roughness: 1 }))
      pom.position.y = 0.38
      g.add(dome, brim, pom)
      const inner = this.wrapChildren(g)
      const sx = Math.max(fit.w + 0.05, 0.2) / 0.33
      const sy = Math.max((tip - r + 0.1) / 0.36, 0.8)
      inner.scale.set(sx, sy, (Math.max(fit.d, 0.15) + 0.05) / (0.33 * 0.66))
      inner.position.y = -0.03
      this.addAccessory('beanie', g)
    }

    // --- head: claw clip (common) — зелёная «черепаховая» заколка-краб с золотой пружиной
    {
      const cx = Math.cos(A0) * 1.08 + Math.sin(A0) * 0.22
      const cy = Math.sin(A0) * 1.08 - Math.cos(A0) * 0.22
      const g = new THREE.Group()
      g.position.set(cx, cy, this.surfZ(cx, cy) + 0.03)
      g.rotation.z = -0.5

      const tex = tortoiseTexture()
      this.textures.push(tex)
      const m = new THREE.MeshPhysicalMaterial({ map: tex, roughness: 0.1, clearcoat: 1, clearcoatRoughness: 0.04 })
      ;([[-1, 0.36], [1, 0.3]] as const).forEach(([sd, ht]) => {
        const curve = new THREE.QuadraticBezierCurve3(
          new THREE.Vector3(sd * 0.07, -ht / 2, 0),
          new THREE.Vector3(sd * 0.1, 0, 0.06),
          new THREE.Vector3(sd * 0.07, ht / 2, 0),
        )
        const band = new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.048, 14, false), m)
        band.scale.z = 0.6
        g.add(band)
        ;[-1, 1].forEach(e => {
          const cap = new THREE.Mesh(new THREE.SphereGeometry(0.048, 14, 10), m)
          cap.scale.z = 0.6
          cap.position.set(sd * 0.07, (e * ht) / 2, 0)
          g.add(cap)
        })
      })

      const metal = new THREE.MeshStandardMaterial({ color: '#e7c46a', metalness: 1, roughness: 0.22, emissive: '#7a5200', emissiveIntensity: 0.12 })
      const fz = 0.05
      const FW = 0.17
      const FH = 0.12
      const tb = 0.016
      ;([[0, FH / 2, FW, tb], [0, -FH / 2, FW, tb], [-FW / 2, 0, tb, FH], [FW / 2, 0, tb, FH]] as const).forEach(([x, y, w, h]) => {
        const bar = new THREE.Mesh(new THREE.BoxGeometry(w, h, tb), metal)
        bar.position.set(x, y + 0.02, fz)
        g.add(bar)
      })
      const spring = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.018, 0.13, 12), metal)
      spring.rotation.z = Math.PI / 2
      spring.position.set(0, -0.045, fz - 0.01)
      g.add(spring)
      for (let k = 0; k < 5; k++) {
        const coil = new THREE.Mesh(new THREE.TorusGeometry(0.021, 0.005, 6, 12), metal)
        coil.rotation.y = Math.PI / 2
        coil.position.set(-0.05 + k * 0.025, -0.045, fz - 0.01)
        g.add(coil)
      }
      this.addAccessory('clip', g)
    }

    // --- head: bow (common) — крупная версия бантика-частицы
    {
      // по другую сторону главного луча от заколки
      const bx = Math.cos(A0) * 1.02 - Math.sin(A0) * 0.3
      const by = Math.sin(A0) * 1.02 + Math.cos(A0) * 0.3
      const g = new THREE.Group()
      g.position.set(bx, by, this.surfZ(bx, by) + 0.04)
      g.rotation.z = 0.5 + (A0 - Math.PI / 2)
      const m = new THREE.MeshPhysicalMaterial({ color: '#ff8fbd', roughness: 0.2, clearcoat: 1, sheen: 1, sheenColor: new THREE.Color('#ffd0e4') })
      const wing = new THREE.ConeGeometry(0.13, 0.24, 24)
      const l = new THREE.Mesh(wing, m)
      l.rotation.z = -Math.PI / 2
      l.position.x = -0.12
      l.scale.set(1, 1, 0.55)
      const r = new THREE.Mesh(wing, m)
      r.rotation.z = Math.PI / 2
      r.position.x = 0.12
      r.scale.set(1, 1, 0.55)
      const knot = new THREE.Mesh(new THREE.SphereGeometry(0.06, 20, 16), m)
      knot.scale.set(1, 1.1, 0.8)
      g.add(l, r, knot)
      this.addAccessory('bow', g)
    }

    // --- eyes: glasses (rare) — чёрные овальные очки с дужками
    {
      const g = new THREE.Group()
      g.position.set(0, EY, this.surfZ(EX, EY) + 0.13)
      g.rotation.z = 0.03
      const frame = new THREE.MeshPhysicalMaterial({ color: '#0c0c0e', roughness: 0.12, clearcoat: 1, clearcoatRoughness: 0.03 })
      const lens = new THREE.MeshPhysicalMaterial({ color: '#2b2c33', roughness: 0.04, transparent: true, opacity: 0.78, clearcoat: 1 })
      const ellipse = <T extends THREE.Path>(p: T, rx: number, ry: number, clockwise = false) => {
        p.absellipse(0, 0, rx, ry, 0, Math.PI * 2, !clockwise)
        return p
      }
      ;[-1, 1].forEach(sd => {
        const rim = ellipse(new THREE.Shape(), 0.3, 0.2)
        rim.holes.push(ellipse(new THREE.Path(), 0.245, 0.15, true))
        const fr = new THREE.Mesh(
          new THREE.ExtrudeGeometry(rim, { depth: 0.03, bevelEnabled: true, bevelThickness: 0.018, bevelSize: 0.016, bevelSegments: 4, curveSegments: 48 }),
          frame,
        )
        fr.position.set(sd * (EX + 0.015), 0, -0.03)
        fr.rotation.z = sd * -0.06
        const l = new THREE.Mesh(new THREE.ShapeGeometry(ellipse(new THREE.Shape(), 0.25, 0.155), 48), lens)
        l.position.set(sd * (EX + 0.015), 0, -0.012)
        l.rotation.z = sd * -0.06
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.045, 0.3), frame)
        arm.position.set(sd * (EX + 0.31), 0.03, -0.16)
        g.add(fr, l, arm)
      })
      const bridge = new THREE.Mesh(new THREE.TorusGeometry(0.05, 0.028, 10, 18, Math.PI), frame)
      bridge.position.y = 0.02
      g.add(bridge)
      this.addAccessory('glasses', g)
    }

    // --- eyes: heart glasses (epic)
    {
      const g = new THREE.Group()
      g.position.set(0, EY + 0.01, this.surfZ(EX, EY) + 0.13)
      g.rotation.z = -0.05
      const frame = new THREE.MeshPhysicalMaterial({ color: '#ff2f6d', roughness: 0.12, clearcoat: 1, emissive: '#ff2f6d', emissiveIntensity: 0.15 })
      const lens = new THREE.MeshPhysicalMaterial({ color: '#ff5f8f', roughness: 0.05, transparent: true, opacity: 0.5, clearcoat: 1 })
      const outer = heartShape(0.27)
      const inner = heartShape(0.21)
      const ringShape = heartShape(0.27)
      ringShape.holes.push(new THREE.Path(inner.getPoints(40).reverse()))
      const ringGeo = new THREE.ExtrudeGeometry(ringShape, { depth: 0.04, bevelEnabled: true, bevelThickness: 0.012, bevelSize: 0.012, bevelSegments: 3, curveSegments: 24 })
      const lensGeo = new THREE.ShapeGeometry(outer, 24)
      ;[-1, 1].forEach(sd => {
        const r = new THREE.Mesh(ringGeo, frame)
        r.position.set(sd * EX, 0, -0.02)
        const l = new THREE.Mesh(lensGeo, lens)
        l.position.set(sd * EX, 0, -0.01)
        l.scale.setScalar(0.92)
        g.add(r, l)
      })
      const bridge = new THREE.Mesh(new THREE.TorusGeometry(0.06, 0.024, 8, 16, Math.PI), frame)
      bridge.position.y = 0.05
      g.add(bridge)
      this.addAccessory('heart_glasses', g)
    }

    // --- ray: bracelet (common) — бусины по сечению луча, ближайшего к 18°
    {
      const ang = nearestRayAngle(this.shape, (18 * Math.PI) / 180)
      const d = 1 + (this.tipR(ang) - 1) * 0.5
      const u = new THREE.Vector3(Math.cos(ang), Math.sin(ang), 0)
      const v = new THREE.Vector3(-Math.sin(ang), Math.cos(ang), 0)
      const c = u.clone().multiplyScalar(d)
      let a = 0.05
      while (a < 0.8 && this.hitZ(c.x + v.x * a, c.y + v.y * a) !== null) a += 0.01
      const b = this.surfZ(c.x, c.y)
      const g = new THREE.Group()
      g.position.copy(c)
      const beadGeo = new THREE.SphereGeometry(0.055, 16, 12)
      for (let k = 0; k < 14; k++) {
        const ph = (k / 14) * Math.PI * 2
        const m = new THREE.Mesh(beadGeo, new THREE.MeshPhysicalMaterial({ color: '#ffffff', roughness: 0.1, clearcoat: 1 }))
        m.position
          .copy(v.clone().multiplyScalar(Math.cos(ph) * (a + 0.045)))
          .add(new THREE.Vector3(0, 0, Math.sin(ph) * (b + 0.045)))
        g.add(m)
        this.beads.push(m)
      }
      this.addAccessory('bracelet', g)
    }

    // --- ray: ring (rare) — золотое кольцо на луче, ближайшем к 162°
    {
      const ang = nearestRayAngle(this.shape, (162 * Math.PI) / 180)
      const d = 1 + (this.tipR(ang) - 1) * 0.55
      const u = new THREE.Vector3(Math.cos(ang), Math.sin(ang), 0)
      const v = new THREE.Vector3(-Math.sin(ang), Math.cos(ang), 0)
      const c = u.clone().multiplyScalar(d)
      let a = 0.05
      while (a < 0.8 && this.hitZ(c.x + v.x * a, c.y + v.y * a) !== null) a += 0.01
      const b = this.surfZ(c.x, c.y)
      const pts: THREE.Vector3[] = []
      for (let k = 0; k < 48; k++) {
        const ph = (k / 48) * Math.PI * 2
        pts.push(
          v.clone().multiplyScalar(Math.cos(ph) * (a + 0.02))
            .add(new THREE.Vector3(0, 0, Math.sin(ph) * (b + 0.02))),
        )
      }
      const curve = new THREE.CatmullRomCurve3(pts, true)
      const g = new THREE.Group()
      g.position.copy(c)
      g.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 64, 0.035, 10, true), gold))
      const gem = new THREE.Mesh(
        new THREE.OctahedronGeometry(0.07),
        new THREE.MeshPhysicalMaterial({ color: '#ff5fa2', emissive: '#ff2f86', emissiveIntensity: 0.5, roughness: 0.05, clearcoat: 1 }),
      )
      gem.position.set(0, 0, b + 0.08)
      gem.scale.set(1, 1.3, 1)
      g.add(gem)
      g.userData.gem = gem
      this.addAccessory('ring', g)
    }

    // --- aura: halo (epic) — не крутится вместе с телом
    {
      const g = new THREE.Group()
      const top = this.tipR(A0)
      g.position.set(Math.cos(A0) * (top + 0.3), Math.sin(A0) * (top + 0.3), -0.1)
      g.rotation.x = 1.25
      g.userData.baseY = g.position.y
      const haloMat = new THREE.MeshBasicMaterial({ color: '#fff1b0', toneMapped: false })
      g.add(new THREE.Mesh(new THREE.TorusGeometry(0.42, 0.045, 16, 64), haloMat))
      const glow = new THREE.Mesh(
        new THREE.TorusGeometry(0.42, 0.13, 12, 64),
        new THREE.MeshBasicMaterial({ color: '#ffe08a', transparent: true, opacity: 0.22, depthWrite: false, toneMapped: false }),
      )
      g.add(glow)
      const light = new THREE.PointLight(0xffe7a0, 1.6, 3.5)
      light.position.set(0, 0, 0)
      g.add(light)
      g.userData.glow = glow
      this.addAccessory('halo', g, this.auraGroup)
    }

    // --- aura: star dust (secret)
    {
      const g = new THREE.Group()
      g.rotation.x = 1.2
      g.rotation.y = 0.25
      const geo = new THREE.OctahedronGeometry(0.055)
      for (let k = 0; k < 40; k++) {
        const m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: '#ffffff', toneMapped: false }))
        const a = (k / 40) * Math.PI * 2 + Math.random() * 0.1
        const r = 2.05 + Math.random() * 0.4
        m.position.set(Math.cos(a) * r, Math.sin(a) * r, (Math.random() - 0.5) * 0.25)
        m.userData = { ph: Math.random() * 6.28, h: Math.random() }
        g.add(m)
      }
      this.addAccessory('dust', g, this.auraGroup)
    }
  }

  // Эволюция: маленькие звёздочки-спутники и больше свечения.
  private buildSatellites() {
    const geo = new THREE.ExtrudeGeometry(starShape(0.11, 0.05), {
      depth: 0.04, bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.015, bevelSegments: 2,
    })
    geo.center()
    for (let i = 0; i < MAX_SATELLITES; i++) {
      const m = new THREE.Mesh(
        geo,
        new THREE.MeshPhysicalMaterial({ color: '#ffffff', roughness: 0.1, clearcoat: 1, emissive: '#ffffff', emissiveIntensity: 0.4 }),
      )
      m.visible = false
      m.scale.setScalar(0.001)
      m.userData = { a: (i / MAX_SATELLITES) * Math.PI * 2, s: 0 }
      this.root.add(m)
      this.satellites.push(m)
    }
  }

  private buildBurst() {
    const geo = new THREE.OctahedronGeometry(0.06)
    for (let i = 0; i < 22; i++) {
      const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: '#ffffff', toneMapped: false }))
      mesh.visible = false
      this.burstGroup.add(mesh)
      this.burst.push({ mesh, vel: new THREE.Vector3(), life: 1, size: 1 })
    }
  }

  // Перенос design-reference/character/Cosmi Capsule.dc.html:
  // перламутровая капсула из двух полусфер, шов-кольцо с защёлкой,
  // свет внутри, искры, лучи и спрайт свечения, вспышка, конфетти.
  private buildCapsule() {
    const C = (h: string) => new THREE.Color(h)
    const R = CAPSULE_R
    const H = CAPSULE_H

    // Лучи за капсулой (видны после открытия).
    this.raysMat = new THREE.ShaderMaterial({
      uniforms: { uT: { value: 0 }, uA: { value: 0 }, uC: { value: new THREE.Vector3(1, 1, 1) } },
      vertexShader:
        'varying vec2 vU; void main(){ vU=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
      fragmentShader:
        'uniform float uT; uniform float uA; uniform vec3 uC; varying vec2 vU;' +
        'void main(){ vec2 p=vU-0.5; float r=length(p); float a=atan(p.y,p.x);' +
        'float ry=pow(0.5+0.5*sin(a*9.0+uT*0.5),7.0)*0.8+pow(0.5+0.5*sin(a*14.0-uT*0.35),10.0)*0.5;' +
        'float f=smoothstep(0.5,0.08,r); float core=exp(-r*r*30.0)*0.9;' +
        'float v=clamp((ry*f+core)*uA,0.0,1.0); gl_FragColor=vec4(uC,v); }',
      transparent: true,
      depthWrite: false,
      toneMapped: false,
    })
    this.rays = new THREE.Mesh(new THREE.PlaneGeometry(11, 11), this.raysMat)
    this.rays.position.set(0, 0.1, -2.2)
    this.rays.visible = false
    this.scene.add(this.rays)

    // Профиль полусферы с цилиндрическим пояском у шва.
    const prof = (dir: number) => {
      const p = [new THREE.Vector2(R, 0), new THREE.Vector2(R, H * dir)]
      for (let i = 1; i <= 32; i++) {
        const a = (i / 32) * (Math.PI / 2)
        p.push(new THREE.Vector2(Math.max(0.0001, Math.cos(a) * R), (H + Math.sin(a) * R) * dir))
      }
      return p
    }

    this.capTopMat = new THREE.MeshPhysicalMaterial({
      color: '#ffffff', transmission: 1, roughness: 0.32, thickness: 0.45, ior: 1.25,
      clearcoat: 1, clearcoatRoughness: 0.04,
      iridescence: 0.9, iridescenceIOR: 1.3, iridescenceThicknessRange: [150, 460],
      side: THREE.DoubleSide, attenuationColor: C('#f4ecff'), attenuationDistance: 5, specularIntensity: 1,
    })
    const botMat = new THREE.MeshPhysicalMaterial({
      color: '#ebe3f5', roughness: 0.2, clearcoat: 1, clearcoatRoughness: 0.06,
      iridescence: 1, iridescenceIOR: 1.6, iridescenceThicknessRange: [260, 720],
      sheen: 1, sheenColor: C('#ffd0ea'), sheenRoughness: 0.4, side: THREE.DoubleSide,
    })
    this.capTop.add(new THREE.Mesh(new THREE.LatheGeometry(prof(1), 96), this.capTopMat))
    this.capBot.add(new THREE.Mesh(new THREE.LatheGeometry(prof(-1), 96), botMat))

    this.capSeamMat = new THREE.MeshPhysicalMaterial({
      color: '#ffffff', metalness: 0.5, roughness: 0.14, clearcoat: 1,
      emissive: C('#ffd6ea'), emissiveIntensity: 0.1,
    })
    const seam = new THREE.Mesh(new THREE.TorusGeometry(R + 0.01, 0.055, 18, 128), this.capSeamMat)
    seam.rotation.x = Math.PI / 2
    this.capBot.add(seam)
    const latch = new THREE.Mesh(new THREE.CapsuleGeometry(0.06, 0.22, 6, 16), this.capSeamMat)
    latch.rotation.z = Math.PI / 2
    latch.position.set(0, 0, R + 0.07)
    this.capBot.add(latch)

    this.cap.add(this.capTop, this.capBot)
    this.root.add(this.cap)

    this.capLight = new THREE.PointLight(0xffd0ec, 0, 6)
    this.capLight.position.set(0, 0.1, 0.3)
    this.root.add(this.capLight)

    const sparkMat = new THREE.MeshBasicMaterial({ color: '#ffffff', toneMapped: false, transparent: true })
    const sparkGeo = new THREE.OctahedronGeometry(0.035)
    for (let k = 0; k < 18; k++) {
      const m = new THREE.Mesh(sparkGeo, sparkMat)
      m.userData = {
        a: Math.random() * Math.PI * 2,
        r: 1.05 + Math.random() * 0.35,
        y: 0.15 + Math.random() * 1.1,
        sp: 0.3 + Math.random() * 0.5,
        ph: Math.random() * Math.PI * 2,
      }
      m.visible = false
      this.cap.add(m)
      this.capSparks.push(m)
    }

    // Мягкое свечение из капсулы.
    const gcv = document.createElement('canvas')
    gcv.width = gcv.height = 128
    const gc = gcv.getContext('2d')
    if (gc) {
      const grd = gc.createRadialGradient(64, 64, 0, 64, 64, 64)
      grd.addColorStop(0, 'rgba(255,255,255,1)')
      grd.addColorStop(0.35, 'rgba(255,240,250,.55)')
      grd.addColorStop(1, 'rgba(255,255,255,0)')
      gc.fillStyle = grd
      gc.fillRect(0, 0, 128, 128)
    }
    const glowTex = new THREE.CanvasTexture(gcv)
    this.textures.push(glowTex)
    this.capGlow = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: glowTex, transparent: true, opacity: 0, depthWrite: false, toneMapped: false }),
    )
    this.capGlow.position.set(0, 0, 0.6)
    this.root.add(this.capGlow)

    // Вспышка на весь кадр — плоскость прямо перед камерой.
    this.flashMat = new THREE.MeshBasicMaterial({
      color: '#ffffff', transparent: true, opacity: 0, depthTest: false, depthWrite: false, toneMapped: false,
    })
    const flash = new THREE.Mesh(new THREE.PlaneGeometry(6, 6), this.flashMat)
    flash.position.z = -1
    flash.renderOrder = 999
    this.camera.add(flash)

    this.confGeo = [
      new THREE.DodecahedronGeometry(0.06),
      new THREE.CylinderGeometry(0.07, 0.07, 0.012, 6),
      new THREE.SphereGeometry(0.05, 12, 10),
      new THREE.OctahedronGeometry(0.065),
      new THREE.TorusGeometry(0.05, 0.018, 8, 16),
    ]
  }

  private burstConfetti() {
    const T = ARCHETYPES[this.lastType ?? 'chameleon']
    const pal =
      this.lastType === 'chameleon'
        ? ['#ff5236', '#ffb3cc', '#b7a2ff', '#9fe3ff', '#f2c75c']
        : [T.body, T.accent, T.glowCol]
    pal.push('#ffffff', '#f6c453')
    for (let i = 0; i < 90; i++) {
      const gi = Math.floor(Math.random() * this.confGeo.length)
      const col = new THREE.Color(pal[i % pal.length])
      const mat =
        gi === 1 || gi === 3
          ? new THREE.MeshStandardMaterial({ color: col, metalness: 1, roughness: 0.15, emissive: col, emissiveIntensity: 0.35 })
          : new THREE.MeshPhysicalMaterial({ color: col, roughness: 0.15, clearcoat: 1, emissive: col, emissiveIntensity: 0.15 })
      const mesh = new THREE.Mesh(this.confGeo[gi], mat)
      const d = new THREE.Vector3(Math.random() * 2 - 1, Math.random() * 2 - 1, Math.random() * 2 - 1).normalize()
      mesh.position.copy(d).multiplyScalar(0.4)
      const vel = d.multiplyScalar(3.5 + Math.random() * 5)
      vel.y += 2.2
      vel.z = Math.abs(vel.z) * 0.6 + 1
      mesh.rotation.set(Math.random() * 6, Math.random() * 6, Math.random() * 6)
      mesh.scale.setScalar(0.001)
      this.root.add(mesh)
      this.confetti.push({
        mesh,
        vel,
        spin: new THREE.Vector3(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5).multiplyScalar(14),
        size: 0.7 + Math.random() * 0.8,
        life: 0,
        max: 2 + Math.random() * 1.2,
      })
    }
  }

  private clearConfetti() {
    this.confetti.forEach(c => {
      this.root.remove(c.mesh)
      ;(c.mesh.material as THREE.Material).dispose()
    })
    this.confetti.length = 0
  }

  private startBurst() {
    this.capPhase = 'burst'
    this.capPt = 0
    this.capRevealSent = false
    this.topV.set(0.8 + Math.random() * 0.6, 6.5, 2.5)
    this.topSpin.set(2.4, 1, -3.2)
    this.botV.set(-0.6 - Math.random() * 0.6, -5.5, 2)
    this.botSpin.set(-2, -0.6, 2.6)
    this.capSparks.forEach(m => { m.visible = false })
    this.burstConfetti()
    this.spawnBurst()
    const T = ARCHETYPES[this.lastType ?? 'chameleon']
    const rc = new THREE.Color(T.glowCol).lerp(this.white, 0.55)
    this.raysMat.uniforms.uC.value.set(rc.r, rc.g, rc.b)
    this.rays.visible = true
    this.opts.onCapsuleBurst?.()
  }

  private finishCapsule() {
    this.capPhase = 'done'
    this.capPt = 0
    this.canvas.style.cursor = this.opts.interactive ? 'grab' : 'default'
    this.cap.visible = false
    this.capGlow.material.opacity = 0
    this.capLight.intensity = 0
    this.flashMat.opacity = 0
    this.capZ = 1
    this.rotY = 0
    this.rotX = 0
    this.bodyMat.color.copy(this.white)
    this.faceParts.forEach(o => { o.visible = true })
    this.pGroup.visible = true
    this.pGroup.scale.setScalar(1)
    this.auraGroup.visible = true
    this.camera.position.z = this.camZ
    if (!this.capRevealSent) {
      this.capRevealSent = true
      this.opts.onCapsuleRevealed?.()
    }
  }

  // Капсула: всё, что поверх обычного кадра персонажа.
  private capsuleFrame(dt: number, t: number, k: number) {
    const ph = this.capPhase
    if (ph === 'none') return

    const { cur, bodyMat } = this
    const tx = this.gcx
    const ty = this.gcy

    // лучи — общие для всех фаз
    this.raysMat.uniforms.uT.value = t
    this.rays.rotation.z = t * 0.05

    // конфетти
    for (let i = this.confetti.length - 1; i >= 0; i--) {
      const c = this.confetti[i]
      c.life += dt
      c.vel.y -= 5.5 * dt
      c.vel.multiplyScalar(1 - dt * 1.1)
      c.mesh.position.addScaledVector(c.vel, dt)
      c.mesh.rotation.x += c.spin.x * dt
      c.mesh.rotation.y += c.spin.y * dt
      c.mesh.rotation.z += c.spin.z * dt
      const s = c.size * Math.min(1, c.life * 8) * (1 - sstep(c.max - 0.6, c.max, c.life))
      c.mesh.scale.setScalar(Math.max(0.001, s))
      if (c.life > c.max) {
        this.root.remove(c.mesh)
        ;(c.mesh.material as THREE.Material).dispose()
        this.confetti.splice(i, 1)
      }
    }

    // фон: нейтральное лавандовое свечение → цвет персонажа
    const glowTarget = ph === 'burst' || ph === 'done' ? 1 : 0
    this.capGlowMix += (glowTarget - this.capGlowMix) * k
    if (this.capGlowMix < 0.999) {
      this.glowMixColor.copy(this.capLavender).lerp(cur.glowCol, this.capGlowMix)
      this.glowMixColor.getRGB(this.srgb, THREE.SRGBColorSpace)
      this.bgMat.uniforms.uGlow.value.set(this.srgb.r, this.srgb.g, this.srgb.b)
      const amt = this.bgMat.uniforms.uAmt.value as number
      this.bgMat.uniforms.uAmt.value = 0.45 + (amt - 0.45) * this.capGlowMix
    }

    if (ph === 'done') {
      const u = this.raysMat.uniforms.uA
      u.value += (0.42 - u.value) * k
      this.camera.position.z = this.camZ
      return
    }

    const cdt = ph === 'charge' || ph === 'burst' ? dt * this.capSpeed : dt
    this.capPt += cdt
    const pt = this.capPt
    this.capHop *= Math.exp(-dt * 3.5)
    const hp = Math.sin(t * 18) * 0.07 * this.capHop

    let mix = 0
    let flash = 0
    let faceOn = false
    let eyeOpen = 1
    let starScale = STAR_IN_CAPSULE
    const cap = this.cap

    if (ph === 'locked' || ph === 'ready') {
      const ready = ph === 'ready'
      const cyc = t % 2.8
      const wig = ready && cyc < 0.7 ? Math.sin(cyc * 34) * 0.07 * (1 - cyc / 0.7) : 0
      cap.position.set(0, 0, 0)
      cap.rotation.set(-ty * 0.12 + 0.05, tx * 0.35 + Math.sin(t * 0.6) * 0.1, wig + hp * 0.6 + Math.sin(t * 0.8) * 0.03)
      cap.scale.set(1 - hp * 0.5, 1 + hp, 1 - hp * 0.5)
      this.capTopMat.roughness += ((ready ? 0.2 : 0.36 - this.capProgress * 0.1) - this.capTopMat.roughness) * k
      this.capSeamMat.emissiveIntensity = ready
        ? 0.5 + (Math.sin(t * 3.2) * 0.5 + 0.5) * 1.1
        : 0.08 + this.capProgress * 0.35
      this.capLight.intensity += ((ready ? 6 : this.capProgress * 2.4) - this.capLight.intensity) * k
      this.capSpinY = cap.rotation.y + t * 0.5
      this.star.rotation.set(cap.rotation.x, this.capSpinY, cap.rotation.z)
      starScale = STAR_IN_CAPSULE * (1 + hp * 0.3)
      this.capSparks.forEach(m => {
        const u = m.userData as { a: number; r: number; y: number; sp: number; ph: number }
        m.visible = ready
        if (!ready) return
        const a = u.a + t * u.sp
        m.position.set(Math.cos(a) * u.r, u.y * 0.9, Math.sin(a) * u.r)
        m.scale.setScalar(0.5 + Math.max(0, Math.sin(t * 4 + u.ph)) * 1.2)
        m.rotation.y = t * 2
      })
      this.capZ = 1
    } else if (ph === 'charge') {
      const c = Math.min(1, pt / CHARGE_SEC)
      const sh = c * c
      cap.position.set((Math.random() - 0.5) * 0.14 * sh, (Math.random() - 0.5) * 0.06 * sh, 0)
      cap.rotation.z = Math.sin(t * 52) * 0.11 * sh
      cap.rotation.y += (0 - cap.rotation.y) * k * 2
      cap.rotation.x += (0 - cap.rotation.x) * k * 2
      cap.scale.set(1 + 0.05 * sh, 1 - 0.06 * sh, 1 + 0.05 * sh)
      this.capTop.position.y = sh * 0.05
      this.capSeamMat.emissiveIntensity = 1 + sh * 5
      this.capLight.intensity = 6 + sh * 50
      this.capGlow.material.opacity = sh * 0.7
      this.capGlow.scale.setScalar(1.5 + sh * 2.5)
      this.capSpinY += cdt * (1 + sh * 10)
      this.star.rotation.set(cap.rotation.x, this.capSpinY, 0)
      this.capZ = 1 - sh * 0.06
      this.capSparks.forEach(m => {
        const u = m.userData as { a: number; r: number; y: number; sp: number }
        const a = u.a + t * u.sp * (1 + sh * 6)
        const r = u.r * (1 - sh * 0.5)
        m.position.set(Math.cos(a) * r, u.y * 0.9 * (1 - sh * 0.6), Math.sin(a) * r)
      })
      if (pt >= CHARGE_SEC) this.startBurst()
    } else if (ph === 'burst') {
      flash = Math.max(0, 1 - pt / 0.55)
      const up = Math.min(1, pt / 1.1)
      const halves: [THREE.Group, THREE.Vector3, THREE.Vector3][] = [
        [this.capTop, this.topV, this.topSpin],
        [this.capBot, this.botV, this.botSpin],
      ]
      halves.forEach(([g, v, s]) => {
        if (!g.visible) return
        v.y -= 6 * cdt * (v.y > 0 ? 1 : -1) * 0.3
        g.position.addScaledVector(v, cdt)
        g.rotation.x += s.x * cdt
        g.rotation.y += s.y * cdt
        g.rotation.z += s.z * cdt
        g.scale.setScalar(Math.max(0.001, 1 - up * 0.5))
        if (pt > 1.2) g.visible = false
      })
      cap.position.multiplyScalar(0.8)
      cap.rotation.z *= 0.8
      cap.scale.lerp(new THREE.Vector3(1, 1, 1), Math.min(1, k * 3))
      this.capLight.intensity = Math.max(0, 56 * (1 - pt / 0.6))
      this.capGlow.material.opacity = Math.max(0, 0.9 * (1 - pt / 0.8))
      this.capGlow.scale.setScalar(4 + pt * 9)
      this.raysMat.uniforms.uA.value = pt < 0.15 ? pt / 0.15 : Math.max(0.45, 1 - (pt - 0.15) * 0.5)
      this.capZ += (1.02 - this.capZ) * k * 2

      mix = sstep(0.02, 0.6, pt)
      starScale = STAR_IN_CAPSULE + (1 - STAR_IN_CAPSULE) * springOut(pt * 0.9)
      const spin = 1 - Math.pow(1 - Math.min(1, pt / 1.3), 3)
      this.star.rotation.set(0, (1 - spin) * -Math.PI * 2 + tx * 0.3, Math.sin(pt * 10) * 0.08 * (1 - spin))
      faceOn = pt > 0.5
      eyeOpen = Math.max(0.04, springOut((pt - 0.5) * 1.2))

      if (pt > 1.5 && !this.capRevealSent) {
        this.capRevealSent = true
        this.opts.onCapsuleRevealed?.()
      }
      if (pt > 1.8) {
        this.finishCapsule()
        return
      }
    }

    // Персонаж-силуэт: тёмный, матовый, без лица → проявление.
    bodyMat.color.copy(this.capDark).lerp(this.white, mix)
    // До взрыва тело непрозрачное (transmission 0): иначе three.js не
    // рисует его в проход, который видно сквозь стеклянную крышку.
    bodyMat.transmission = mix > 0.001 ? cur.tr * mix : 0
    bodyMat.roughness = 0.45 + (cur.rough - 0.45) * mix
    bodyMat.iridescence = cur.irid * mix
    bodyMat.sheen = cur.sheen * mix
    bodyMat.emissiveIntensity = cur.em * mix + (1 - mix) * 0.6 * flash

    const sq = Math.sin(t * 16) * 0.09 * this.squash
    this.star.scale.set(starScale * (1 - sq * 0.6), starScale * (1 + sq), starScale * (1 - sq * 0.6))

    this.faceParts.forEach(o => { o.visible = faceOn })
    if (faceOn) this.eyes.forEach(e => { e.g.scale.y = cur.eye * eyeOpen })
    this.pGroup.visible = mix > 0.05
    this.pGroup.scale.setScalar(Math.max(0.001, mix))
    this.auraGroup.visible = mix > 0.9
    Object.values(this.acc).forEach(a => { if (!faceOn) a.g.visible = false })
    this.satellites.forEach(m => { if (mix < 0.5) m.visible = false })

    this.flashMat.opacity = flash * flash * 0.85
    this.camera.position.z = this.camZ * this.capZ
  }

  // -------------------------
  // PUBLIC API
  // -------------------------

  setLook(type: ArchetypeKey, accentKey: ArchetypeKey | null, auraBoost = false) {
    const T = ARCHETYPES[type]
    const A = ARCHETYPES[accentKey ?? type]
    const { tgt, cur } = this

    tgt.body.set(T.body)
    tgt.accent.set(type === 'chameleon' ? '#ffffff' : (accentKey && accentKey !== type ? A.accent : T.accent))
    tgt.glowCol.set(T.glowCol).lerp(new THREE.Color(A.accent), type === 'chameleon' ? 0.2 : 0.35)
    tgt.tr = T.tr
    tgt.rough = T.rough
    tgt.em = T.em
    tgt.irid = T.irid
    tgt.sheen = T.sheen
    tgt.glow = T.glow
    tgt.lid = T.lid
    tgt.brow = T.brow
    tgt.browR = T.browR
    tgt.mouth = T.mouth
    tgt.smirk = T.smirk
    tgt.eye = T.eye
    tgt.rainbow = type === 'chameleon' ? 1 : 0
    tgt.purple = type === 'goth' ? 1 : 0
    if (auraBoost) tgt.glow = Math.min(1.2, tgt.glow + 0.25)

    this.burstColors = [new THREE.Color(T.accent), new THREE.Color(T.glowCol), new THREE.Color('#ffffff')]

    if (this.lastType && this.lastType !== type) this.squash = 1
    this.lastType = type

    if (this.firstLook) {
      cur.body.copy(tgt.body)
      cur.accent.copy(tgt.accent)
      cur.glowCol.copy(tgt.glowCol)
      cur.bg.copy(tgt.bg)
      NUM_KEYS.forEach(k => { cur[k] = tgt[k] })
      this.firstLook = false
      this.colorsDirty = true
    }

    this.refreshIdle()
  }

  setStage(hex: string) {
    this.tgt.bg.set(hex)
    if (this.firstLook) this.cur.bg.copy(this.tgt.bg)
    this.refreshIdle()
  }

  setEvolution(level: number) {
    this.tgt.evo = Math.max(0, Math.min(MAX_SATELLITES, level))
    this.refreshIdle()
  }

  setShelf(items: { group: ShadeKey; shade: string }[], density = 1) {
    items.forEach((it, i) => {
      const slot = this.shelfSlots[i]
      if (slot && slot.group === it.group && slot.density === density) return
      if (slot) slot.parts.forEach(p => { p.dying = true })
      const n = Math.max(1, Math.round((it.group === 'glitter' ? 11 : 6) * density))
      const parts: Particle[] = []
      for (let j = 0; j < n; j++) parts.push(this.spawnParticle(it.group, it.shade))
      this.shelfSlots[i] = { group: it.group, density, parts }
    })

    // Полка стала короче — лишние частицы растворяются.
    for (let i = items.length; i < this.shelfSlots.length; i++) {
      this.shelfSlots[i]?.parts.forEach(p => { p.dying = true })
    }
    this.shelfSlots.length = items.length

    if (items.length) {
      this.beads.forEach((m, k) => {
        ;(m.material as THREE.MeshPhysicalMaterial).color.set(items[k % items.length].shade)
      })
    }
    this.refreshIdle()
  }

  // instant — без анимации появления (первичная настройка сцены).
  setEquipped(equipped: Partial<Record<Slot, string | null>>, instant = false) {
    const on = new Set(Object.values(equipped).filter(Boolean) as string[])
    Object.entries(this.acc).forEach(([id, a]) => {
      const next = on.has(id) ? 1 : 0
      if (next && a.t === 0 && !instant) this.squash = Math.max(this.squash, 0.5)
      a.t = next
      if (instant) a.s = next
    })
    this.refreshIdle()
  }

  // Реакция на тап: подпрыгнуть, моргнуть, разбросать частицы.
  react() {
    this.squash = 1
    this.blinkStart = this.t
    this.spawnBurst()
  }

  // Вылет из капсулы при распаковке.
  playIntro() {
    this.intro = 0
    this.squash = 1
    this.spawnBurst()
  }

  // --- капсула

  // Закрыта (progress 0..1 — сколько собрано) или готова к открытию.
  setCapsule(phase: CapsulePhase, progress = 0) {
    if (this.capPhase === 'none') return
    this.capProgress = Math.max(0, Math.min(1, progress))
    const before = this.capPhase
    if (before !== 'locked' && before !== 'ready') return
    if (before === 'locked' && phase === 'ready') this.capHop = 1.4
    this.capPhase = phase
    this.canvas.style.cursor = phase === 'ready' ? 'pointer' : 'default'
    this.refreshIdle()
  }

  setCapsuleSpeed(speed: number) {
    this.capSpeed = Math.max(0.3, Math.min(3, speed))
  }

  // Подпрыгнуть (тап по закрытой капсуле).
  hopCapsule() {
    this.capHop = 1
  }

  // Заряд → взрыв → проявление. Идемпотентно.
  openCapsule() {
    if (this.capPhase !== 'locked' && this.capPhase !== 'ready') return
    this.capPhase = 'charge'
    this.capPt = 0
  }

  // Пропустить анимацию: сразу открытый персонаж.
  skipCapsule() {
    if (this.capPhase === 'none' || this.capPhase === 'done') return
    this.clearConfetti()
    this.raysMat.uniforms.uA.value = 0.42
    this.rays.visible = true
    const T = ARCHETYPES[this.lastType ?? 'chameleon']
    const rc = new THREE.Color(T.glowCol).lerp(this.white, 0.55)
    this.raysMat.uniforms.uC.value.set(rc.r, rc.g, rc.b)
    this.finishCapsule()
    this.playIntro()
  }

  get capsuleOpened() {
    return this.capPhase === 'burst' || this.capPhase === 'done'
  }

  setActive(active: boolean) {
    if (this.disposed) return
    if (active && !this.running) {
      this.running = true
      this.lastFrame = performance.now()
      this.raf = requestAnimationFrame(this.tick)
    } else if (!active && this.running) {
      this.running = false
      cancelAnimationFrame(this.raf)
    }
  }

  // Рендерит кадр и сразу отдаёт canvas (drawImage — в той же задаче).
  snapshot(): HTMLCanvasElement {
    this.safeRender()
    return this.canvas
  }

  dispose() {
    if (this.disposed) return
    this.disposed = true
    this.setActive(false)
    this.ro.disconnect()
    window.removeEventListener('pointermove', this.onLook)
    this.canvas.removeEventListener('webglcontextlost', this.handleContextLost)
    this.canvas.removeEventListener('pointerdown', this.onDown)
    this.canvas.removeEventListener('pointermove', this.onDrag)
    this.canvas.removeEventListener('pointerup', this.onUp)
    this.canvas.removeEventListener('pointercancel', this.onUp)

    const geos = new Set<THREE.BufferGeometry>()
    const mats = new Set<THREE.Material>()
    this.scene.traverse(obj => {
      if (obj instanceof THREE.Mesh) {
        geos.add(obj.geometry)
        const m = obj.material
        ;(Array.isArray(m) ? m : [m]).forEach(x => mats.add(x))
      }
    })
    Object.values(this.particleGeo).forEach(g => geos.add(g))
    this.confGeo.forEach(g => geos.add(g))
    if (this.capGlow) this.capGlow.material.dispose()
    geos.forEach(g => g.dispose())
    this.textures.forEach(t => t.dispose())
    mats.forEach(m => m.dispose())
    this.scene.environment?.dispose()
    this.renderer.dispose()
    this.renderer.forceContextLoss()
    this.canvas.remove()
  }

  // -------------------------
  // INTERNALS
  // -------------------------

  private handleContextLost = (event: Event) => {
    event.preventDefault()
    this.setActive(false)
    this.opts.onContextLost?.()
  }

  private resize() {
    const w = this.host.clientWidth
    const h = this.host.clientHeight
    if (!w || !h) return
    this.renderer.setSize(w, h, false)
    this.camera.aspect = w / h
    this.camZ = BASE_Z * this.zoom * Math.max(1, 0.82 / this.camera.aspect)
    this.camera.position.z = this.camZ * (this.capPhase === 'none' || this.capPhase === 'done' ? 1 : this.capZ)
    this.camera.updateProjectionMatrix()
    if (!this.running) this.safeRender()
  }

  private onDown = (e: PointerEvent) => {
    this.dragging = true
    this.lastX = this.downX = e.clientX
    this.lastY = this.downY = e.clientY
    this.downAt = performance.now()
    this.velX = this.velY = 0
    this.canvas.setPointerCapture(e.pointerId)
    if (this.opts.interactive && !this.capsuleBusy) this.canvas.style.cursor = 'grabbing'
  }

  // Капсула ещё закрыта/открывается — крутить нельзя, только тап.
  private get capsuleBusy() {
    return this.capPhase !== 'none' && this.capPhase !== 'done'
  }

  private onDrag = (e: PointerEvent) => {
    if (!this.dragging || this.capsuleBusy) return
    if (!this.opts.interactive) return
    const dx = e.clientX - this.lastX
    const dy = e.clientY - this.lastY
    this.lastX = e.clientX
    this.lastY = e.clientY
    this.rotY += dx * 0.01
    this.rotX = Math.max(-0.7, Math.min(0.7, this.rotX + dy * 0.006))
    this.velY = dx * 0.01
    this.velX = dy * 0.006
    this.idleT = 0
    if (!this.dragged && Math.abs(e.clientX - this.downX) > 8) {
      this.dragged = true
      this.opts.onFirstDrag?.()
    }
  }

  private onUp = (e: PointerEvent) => {
    if (!this.dragging) return
    this.dragging = false
    const moved = Math.hypot(e.clientX - this.downX, e.clientY - this.downY)
    const held = performance.now() - this.downAt
    const isTap = this.capsuleBusy ? moved < 8 && held < 400 : moved < 6 && held < 350
    if (this.capsuleBusy) {
      this.canvas.style.cursor = this.capPhase === 'ready' ? 'pointer' : 'default'
      if (isTap && (this.capPhase === 'locked' || this.capPhase === 'ready')) {
        this.hopCapsule()
        this.opts.onTap?.()
      }
      return
    }
    this.canvas.style.cursor = this.opts.interactive ? 'grab' : 'default'
    if (!this.opts.interactive) {
      if (isTap) this.opts.onTap?.()
      return
    }
    if (isTap) {
      this.react()
      this.opts.onTap?.()
    }
  }

  private onLook = (e: PointerEvent) => {
    const r = this.host.getBoundingClientRect()
    if (!r.width || !r.height) return
    this.gx = Math.max(-1, Math.min(1, (e.clientX - (r.left + r.width / 2)) / (r.width / 2)))
    this.gy = Math.max(-1, Math.min(1, -(e.clientY - (r.top + r.height * 0.45)) / (r.height / 2)))
  }

  private spawnBurst() {
    const colors = this.burstColors
    this.burst.forEach((b, i) => {
      const a = Math.random() * Math.PI * 2
      const { s } = shapeRadius(this.shape, a)
      const r = 0.45 + Math.random() * 0.4
      b.mesh.position.set(Math.cos(a) * r * s * 0.7, Math.sin(a) * r * s * 0.7, 0.3)
      b.vel.set(Math.cos(a), Math.sin(a), 0.4 + Math.random() * 0.6)
        .multiplyScalar(2 + Math.random() * 1.8)
      b.life = 0
      b.size = 0.6 + Math.random() * 0.9
      ;(b.mesh.material as THREE.MeshBasicMaterial).color.copy(colors[i % colors.length])
      b.mesh.visible = true
    })
  }

  private tick = (now: number) => {
    if (!this.running) return
    this.raf = requestAnimationFrame(this.tick)
    this.frame(now, false)
  }

  // Когда цикл на паузе (персонаж скрыт/вкладка неактивна), после
  // изменения данных рисуем один «установившийся» кадр, чтобы на экране
  // никогда не оставался дефолтный вид.
  private refreshIdle() {
    if (this.running || this.disposed) return
    this.frame(performance.now(), true)
  }

  private frame(now: number, idle: boolean) {
    if (idle) {
      this.particles.forEach(p => { p.s = p.dying ? 0 : 1 })
      Object.values(this.acc).forEach(a => { a.s = a.t })
      this.satellites.forEach((m, i) => { m.userData.s = i < Math.round(this.tgt.evo) ? 1 : 0 })
    }

    const rawDt = idle ? 0 : (now - this.lastFrame) / 1000
    if (!idle) this.lastFrame = now
    const dt = Math.min(Math.max(rawDt, 0), 0.05)
    this.t += dt
    const t = this.t

    // Замер производительности на первых кадрах.
    if (!this.perfReported && rawDt > 0 && rawDt < 1) {
      this.perfFrames++
      this.perfTotal += rawDt * 1000
      if (this.perfFrames >= 90) {
        this.perfReported = true
        this.opts.onPerfSample?.(this.perfTotal / this.perfFrames)
      }
    }

    const { cur, tgt, bodyMat } = this
    const k = idle ? 1 : 1 - Math.exp(-dt * 3.2)

    // --- плавный переход внешности
    const before = cur.body.r + cur.body.g + cur.body.b + cur.accent.r + cur.accent.g + cur.accent.b + cur.rainbow
    cur.body.lerp(tgt.body, k)
    cur.accent.lerp(tgt.accent, k)
    cur.glowCol.lerp(tgt.glowCol, k)
    cur.bg.lerp(tgt.bg, Math.min(1, k * 1.5))
    NUM_KEYS.forEach(key => { cur[key] += (tgt[key] - cur[key]) * k })
    const after = cur.body.r + cur.body.g + cur.body.b + cur.accent.r + cur.accent.g + cur.accent.b + cur.rainbow
    if (Math.abs(after - before) > 1e-4) this.colorsDirty = true

    if (this.colorsDirty) {
      const arr = this.vcol.array as Float32Array
      const B = cur.body
      const A = cur.accent
      const R = cur.rainbow
      const rb = this.rainbow
      for (let i = 0; i < this.vertexCount; i++) {
        const tf = Math.min(1, this.tipF[i] * 1.1)
        const r = B.r + (A.r - B.r) * tf
        const g = B.g + (A.g - B.g) * tf
        const b = B.b + (A.b - B.b) * tf
        arr[i * 3] = r + (rb[i * 3] - r) * R
        arr[i * 3 + 1] = g + (rb[i * 3 + 1] - g) * R
        arr[i * 3 + 2] = b + (rb[i * 3 + 2] - b) * R
      }
      this.vcol.needsUpdate = true
      this.colorsDirty = false
    }

    // Пока персонаж в капсуле, материал ведёт capsuleFrame: двойная
    // запись 0 ↔ >0 в transmission/iridescence/sheen меняла бы version
    // материала каждый кадр (пересборка программы).
    const inCapsule = this.capsuleBusy
    if (!inCapsule) {
      bodyMat.transmission = cur.tr
      bodyMat.roughness = cur.rough
      bodyMat.iridescence = cur.irid
      bodyMat.sheen = cur.sheen
    }
    bodyMat.sheenColor.copy(cur.accent).lerp(this.violet, cur.purple)
    this.emColor.copy(cur.body).lerp(cur.accent, 0.45).lerp(this.white, cur.rainbow * 0.5)
    bodyMat.emissive.copy(this.emColor)
    if (!inCapsule) bodyMat.emissiveIntensity = (cur.em + cur.evo * 0.03) * (1 + Math.sin(t * 1.6) * 0.12)
    bodyMat.attenuationColor.copy(cur.body).lerp(this.white, 0.35)

    this.tmpColor.copy(cur.body).lerp(this.cham, cur.rainbow).multiplyScalar(0.9)
    this.lidMat.color.copy(this.tmpColor)
    this.cheekMat.color.copy(cur.accent).lerp(this.cheekPink, cur.rainbow)
    this.cheekMat.opacity = 0.38 + 0.2 * (1 - cur.purple * 0.4)
    this.purple.intensity = cur.purple * 18
    this.purple2.intensity = cur.purple * 8

    cur.bg.getRGB(this.srgb, THREE.SRGBColorSpace)
    this.bgMat.uniforms.uBg.value.set(this.srgb.r, this.srgb.g, this.srgb.b)
    cur.glowCol.getRGB(this.srgb, THREE.SRGBColorSpace)
    this.bgMat.uniforms.uGlow.value.set(this.srgb.r, this.srgb.g, this.srgb.b)
    this.bgMat.uniforms.uAmt.value = (cur.glow + cur.evo * 0.06) * (cur.bg.r < 0.1 ? 0.5 : 0.62)

    // --- вращение: инерция после drag и возврат лицом к зрителю
    if (!this.dragging) {
      this.rotY += this.velY
      this.rotX += this.velX
      this.velY *= 0.93
      this.velX *= 0.85
      this.idleT += dt
      if (this.idleT > 2.5) {
        const target = Math.round(this.rotY / (Math.PI * 2)) * Math.PI * 2
        this.rotY += (target - this.rotY) * dt * 1.5
        this.rotX += (0 - this.rotX) * dt * 2
      }
      this.rotX = Math.max(-0.7, Math.min(0.7, this.rotX))
    }

    // --- вылет из капсулы
    let introScale = 1
    let introSpin = 0
    if (this.intro < 1) {
      this.intro = Math.min(1, this.intro + dt / 1.1)
      const x = this.intro
      const c1 = 1.9
      introScale = Math.max(0.001, 1 + (c1 + 1) * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2))
      introSpin = (1 - x) * (1 - x) * Math.PI * 4
    }

    this.squash *= Math.exp(-dt * 3.2)
    const sq = Math.sin(t * 16) * 0.09 * this.squash
    const evoScale = 1 + cur.evo * 0.025
    this.star.scale.set(
      (1 - sq * 0.6) * introScale * evoScale,
      (1 + sq) * introScale * evoScale,
      (1 - sq * 0.6) * introScale * evoScale,
    )
    this.root.position.y = Math.sin(t * 1.3) * 0.06 + this.squash * Math.max(0, Math.sin(t * 8)) * 0.06
    this.star.rotation.set(
      this.rotX + Math.sin(t * 0.9) * 0.04,
      this.rotY + introSpin + Math.sin(t * 0.7) * 0.12,
      Math.sin(t * 0.8) * 0.05,
    )
    this.auraGroup.position.y = this.root.position.y
    this.auraGroup.scale.setScalar(introScale)

    // --- лицо: моргание, взгляд, брови, рот
    if (t > this.nextBlink) {
      this.blinkStart = t
      this.nextBlink = t + 2.2 + Math.random() * 3.2
    }
    const bp = (t - this.blinkStart) / 0.17
    const blink = bp >= 0 && bp <= 1 ? Math.sin(bp * Math.PI) : 0

    if (this.opts.eyesFollow !== false) {
      this.gcx += (this.gx - this.gcx) * k * 2
      this.gcy += (this.gy - this.gcy) * k * 2
    } else {
      this.gcx += (Math.sin(t * 0.5) * 0.6 - this.gcx) * k
      this.gcy += (Math.cos(t * 0.37) * 0.3 - this.gcy) * k
    }

    this.eyes.forEach(e => {
      const lid = Math.max(cur.lid, blink)
      e.lid.rotation.x = -1.6 + lid * 3.15
      e.g.scale.set(cur.eye, cur.eye, 0.5)
      e.iris.position.set(this.gcx * 0.04, this.gcy * 0.032 + 0.005, 0)
    })
    this.brows.forEach(b => {
      const sd = b.userData.sd as number
      b.rotation.z = Math.PI / 2 + sd * cur.brow
      b.position.y = 0.43 + (cur.eye - 1) * 0.2 + (sd > 0 ? cur.browR * 0.1 : 0) + cur.brow * -0.02 + blink * -0.015
    })
    const curve = 0.12 + cur.mouth * 0.9
    this.mouth.scale.set(1 + cur.smirk * 0.15, curve, 1)
    this.mouth.rotation.z = cur.smirk * 0.35
    const fx = 0.036
    this.fang.position.set(
      this.mouth.position.x + fx,
      this.mouth.position.y - Math.sqrt(0.075 * 0.075 - fx * fx) * curve + fx * Math.sin(cur.smirk * 0.35) - 0.03,
      this.mouthZ + 0.012,
    )

    // --- частицы внутри тела
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i]
      p.s += ((p.dying ? 0 : 1) - p.s) * Math.min(1, dt * 4)
      if (p.dying && p.s < 0.02) {
        this.pGroup.remove(p.mesh)
        p.mat.dispose()
        this.particles.splice(i, 1)
        continue
      }
      const w = t * p.sp + p.ph
      p.mesh.position.set(
        p.base.x + Math.sin(w) * p.amp,
        p.base.y + Math.cos(w * 0.8) * p.amp,
        p.base.z + Math.sin(w * 1.3) * p.amp * 0.4,
      )
      p.mesh.rotation.x += p.spin.x * dt
      p.mesh.rotation.y += p.spin.y * dt
      p.mesh.rotation.z += p.spin.z * dt
      p.mesh.scale.setScalar(Math.max(0.001, p.s * p.size))
    }

    // --- частицы тапа
    this.burst.forEach(b => {
      if (!b.mesh.visible) return
      b.life += dt / 0.9
      if (b.life >= 1) {
        b.mesh.visible = false
        return
      }
      b.vel.multiplyScalar(Math.exp(-dt * 2.6))
      b.mesh.position.addScaledVector(b.vel, dt)
      b.mesh.rotation.y += dt * 6
      const s = Math.max(0.001, (1 - b.life) * b.size)
      b.mesh.scale.set(s * 0.7, s * 1.4, s * 0.7)
    })

    // --- аксессуары (pop-in с лёгким перелётом)
    Object.values(this.acc).forEach(a => {
      a.s += (a.t - a.s) * Math.min(1, dt * 7)
      const elastic = a.t ? 1 + Math.sin(a.s * Math.PI) * 0.15 : 1
      a.g.visible = a.s > 0.01
      a.g.scale.setScalar(Math.max(0.001, a.s * elastic))
    })

    const crown = this.acc.crown.g
    if (crown.visible) {
      this.goldMat.emissiveIntensity = 0.15 + (Math.sin(t * 3) * 0.5 + 0.5) * 0.45
      ;(crown.userData.sparks as THREE.Group).children.forEach((m, i) => {
        const a = (m.userData.a as number) + t * 1.2
        m.position.set(Math.cos(a) * 0.48, 0.15 + Math.sin(t * 2 + i) * 0.08, Math.sin(a) * 0.48)
        const s = 0.6 + Math.max(0, Math.sin(t * 4 + i * 1.7)) * 0.9
        m.scale.set(0.5 * s, 1.3 * s, 0.5 * s)
        m.rotation.y = t * 3
      })
    }

    const ring = this.acc.ring.g
    if (ring.visible) (ring.userData.gem as THREE.Mesh).rotation.y = t * 2

    const halo = this.acc.halo.g
    if (halo.visible) {
      halo.position.y = (halo.userData.baseY as number) + Math.sin(t * 1.7) * 0.05
      ;((halo.userData.glow as THREE.Mesh).material as THREE.MeshBasicMaterial).opacity = 0.16 + (Math.sin(t * 2.4) * 0.5 + 0.5) * 0.14
    }

    const dust = this.acc.dust.g
    if (dust.visible) {
      dust.rotation.z = t * 0.25
      dust.children.forEach(m => {
        const u = m.userData as { ph: number; h: number }
        const tw = 0.5 + Math.max(0, Math.sin(t * 3 + u.ph)) * 1.1
        m.scale.set(tw * 0.7, tw * 1.4, tw * 0.7)
        m.rotation.z = -t * 0.25
        ;((m as THREE.Mesh).material as THREE.MeshBasicMaterial).color.setHSL((u.h + t * 0.08) % 1, 0.9, 0.72)
      })
    }

    // --- спутники эволюции
    this.satellites.forEach((m, i) => {
      const ud = m.userData as { a: number; s: number }
      const on = i < Math.round(this.tgt.evo) ? 1 : 0
      ud.s += (on - ud.s) * Math.min(1, dt * 4)
      m.visible = ud.s > 0.01
      if (!m.visible) return
      const a = ud.a + t * 0.6
      m.position.set(Math.cos(a) * 1.95, 0.25 + Math.sin(a * 2 + i) * 0.35, Math.sin(a) * 0.9)
      m.rotation.set(0, t * 1.5 + i, Math.sin(t + i) * 0.3)
      m.scale.setScalar(Math.max(0.001, ud.s * (0.9 + Math.sin(t * 3 + i) * 0.1)))
      const mat = m.material as THREE.MeshPhysicalMaterial
      mat.color.copy(cur.accent).lerp(this.white, 0.3)
      mat.emissive.copy(cur.glowCol)
    })

    this.capsuleFrame(dt, t, k)

    this.safeRender()
  }

  // Контекст WebGL могут отобрать (iOS в фоне, нехватка памяти).
  // Тогда останавливаемся и просим React показать картинку.
  private safeRender() {
    if (this.renderer.getContext().isContextLost()) {
      this.failed()
      return
    }
    try {
      this.renderer.render(this.scene, this.camera)
    } catch (error) {
      console.warn('cosmi star: render failed', error)
      this.failed()
    }
  }

  private failed() {
    if (this.disposed) return
    this.setActive(false)
    this.opts.onContextLost?.()
  }
}
