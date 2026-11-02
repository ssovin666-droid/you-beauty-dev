import { useMemo } from 'react'

import { starSvgMarkup } from '../../lib/character/fallback'

type Props = {
  progress: number
  target: number
  ready?: boolean
  shaking?: boolean
  cracked?: boolean
  open?: boolean
  onClick?: () => void
}

// CSS-капсула — запасной вариант для устройств без WebGL (или
// помеченных медленными). Основная капсула — 3D в StarScene
// (режим capsule), её рендерит CosmiStar.
export function LockedCapsule({ progress, target, ready, shaking, cracked, open, onClick }: Props) {
  const silhouette = useMemo(() => starSvgMarkup('chameleon', null, { silhouette: true, size: 150 }), [])
  const fill = Math.max(0, Math.min(1, progress / target))

  const className = [
    'cs-capsule',
    ready ? 'is-ready' : '',
    shaking ? 'is-shaking' : '',
    cracked ? 'is-cracked' : '',
    open ? 'is-open' : '',
  ].join(' ')

  return (
    <div className={className} onClick={onClick} role={onClick ? 'button' : undefined}>
      <div className="cs-capsule-glow" style={{ opacity: 0.25 + fill * 0.75 }} />
      <div className="cs-capsule-half cs-capsule-top">
        <span className="cs-capsule-shine" />
      </div>
      <div className="cs-capsule-half cs-capsule-bottom">
        <span className="cs-capsule-level" style={{ height: `${fill * 100}%` }} />
      </div>
      <div
        className="cs-capsule-silhouette"
        // Разметка генерируется нами (без пользовательского ввода).
        dangerouslySetInnerHTML={{ __html: silhouette }}
      />
      <svg className="cs-capsule-cracks" viewBox="0 0 160 220" aria-hidden="true">
        <path d="M80 18 L72 52 L88 70 L76 104 L92 122" />
        <path d="M40 96 L58 108 L52 128 L70 140" />
        <path d="M124 84 L108 100 L118 118 L102 134" />
      </svg>
    </div>
  )
}
