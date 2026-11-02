import { useEffect, useRef, useState } from 'react'

import capsuleBase from '../../assets/character/capsule-base.webp'
import capsuleLit from '../../assets/character/capsule-lit.webp'
import capsuleMask from '../../assets/character/capsule-mask.png'

type Props = {
  progress: number
  target: number
  ready?: boolean
  shaking?: boolean
  cracked?: boolean
  onClick?: () => void
}

// Капсула на главной — одна заранее отрисованная картинка для всех
// (кадр 3D-капсулы из design-reference «Cosmi Capsule»), всё движение
// на CSS (transform/opacity) — без WebGL, почти бесплатно для телефона.
// Наполнение: цветная «жидкость» поднимается по мере добавления средств,
// изнутри разгорается свет, шов начинает светиться. На каждое новое
// средство капсула подпрыгивает. Готова — покачивается, вокруг искры.
// Она же — запасной вариант распаковки без WebGL (shaking/cracked).
export function LockedCapsule({ progress, target, ready, shaking, cracked, onClick }: Props) {
  const fill = ready ? 1 : Math.max(0, Math.min(1, progress / Math.max(1, target)))
  const [bump, setBump] = useState(false)
  const prev = useRef(progress)

  useEffect(() => {
    if (progress > prev.current) {
      setBump(true)
      const t = window.setTimeout(() => setBump(false), 700)
      prev.current = progress
      return () => window.clearTimeout(t)
    }
    prev.current = progress
  }, [progress])

  const className = [
    'cs-capsule',
    ready ? 'is-ready' : '',
    bump ? 'is-bump' : '',
    shaking ? 'is-shaking' : '',
    cracked ? 'is-cracked' : '',
  ].join(' ')

  return (
    <div
      className={className}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      style={{
        ['--fill' as string]: fill,
        ['--cap-mask' as string]: `url(${capsuleMask})`,
      }}
    >
      <div className="cs-capsule-aura" />
      <div className="cs-capsule-body">
        <img className="cs-capsule-img" src={capsuleBase} alt="" draggable={false} />
        <img className="cs-capsule-img cs-capsule-lit" src={capsuleLit} alt="" draggable={false} />
        <div className="cs-capsule-fill" aria-hidden="true">
          <div className="cs-capsule-liquid">
            <span className="cs-capsule-wave" />
            <i /><i /><i /><i /><i />
          </div>
        </div>
        <div className="cs-capsule-inner" aria-hidden="true" />
        <svg className="cs-capsule-cracks" viewBox="0 0 160 182" aria-hidden="true">
          <path d="M80 14 L72 44 L88 60 L76 90 L92 106" />
          <path d="M34 80 L52 92 L46 110 L64 122" />
          <path d="M128 70 L112 86 L122 102 L106 118" />
        </svg>
      </div>
      {ready && (
        <div className="cs-capsule-sparks" aria-hidden="true">
          <i /><i /><i /><i /><i /><i />
        </div>
      )}
    </div>
  )
}
