import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

import type { ThemeMode } from '../../lib/character/env'

type Props = {
  open: boolean
  onClose: () => void
  title: string
  theme: ThemeMode
  children: ReactNode
  tall?: boolean
}

export function BottomSheet({ open, onClose, title, theme, children, tall }: Props) {
  // Держим в DOM до конца анимации закрытия.
  const [mounted, setMounted] = useState(open)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (open) {
      setMounted(true)
      const id = requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)))
      return () => cancelAnimationFrame(id)
    }
    setVisible(false)
    const timer = window.setTimeout(() => setMounted(false), 260)
    return () => window.clearTimeout(timer)
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [open, onClose])

  if (!mounted) return null

  return createPortal(
    <div className={`cs-sheet-root ${visible ? 'is-open' : ''}`} data-theme={theme}>
      <div className="cs-sheet-backdrop" onClick={onClose} />
      <section
        className={`cs-sheet ${tall ? 'is-tall' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="cs-sheet-grip" />
        <header className="cs-sheet-head">
          <h3>{title}</h3>
          <button type="button" className="cs-icon-btn" onClick={onClose} aria-label="Закрыть">
            ✕
          </button>
        </header>
        <div className="cs-sheet-body">{children}</div>
      </section>
    </div>,
    document.body,
  )
}
