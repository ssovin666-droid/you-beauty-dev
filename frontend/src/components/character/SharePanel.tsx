import { useEffect, useRef, useState } from 'react'

import { trackCharacterEvent } from '../../lib/amplitude'
import { characterApi } from '../../lib/character/api'
import { BOT_USERNAME, makeShareCard } from '../../lib/character/card'
import { ARCHETYPES, type ArchetypeKey } from '../../lib/character/config'
import type { ThemeMode } from '../../lib/character/env'
import { getWebApp, haptic, isVersionAtLeast } from '../../lib/telegram'
import type { CosmiStarHandle } from './CosmiStar'

type Props = {
  starRef: React.RefObject<CosmiStarHandle | null>
  archetype: ArchetypeKey
  accent: ArchetypeKey | null
  theme: ThemeMode
  source: 'unboxing' | 'home'
  onClose: () => void
}

type CardState =
  | { status: 'building' }
  | { status: 'ready'; previewUrl: string; publicUrl: string | null; blob: Blob }
  | { status: 'error'; message: string }

const BOT_LINK = `https://t.me/${BOT_USERNAME}`

export function SharePanel({ starRef, archetype, accent, theme, source, onClose }: Props) {
  const [card, setCard] = useState<CardState>({ status: 'building' })
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const uploadRef = useRef<Promise<string> | null>(null)
  const T = ARCHETYPES[archetype]
  const canStory = Boolean(getWebApp()?.shareToStory) && isVersionAtLeast('7.8')

  useEffect(() => {
    let cancelled = false
    let previewUrl: string | null = null

    async function build() {
      try {
        const frame = await starRef.current?.snapshot()
        const blob = await makeShareCard(frame ?? null, archetype, theme)
        if (cancelled) return
        previewUrl = URL.createObjectURL(blob)
        setCard({ status: 'ready', previewUrl, publicUrl: null, blob })

        // Загружаем заранее, чтобы «В сторис» срабатывал сразу.
        uploadRef.current = characterApi.uploadShareCard(blob).then(res => res.url)
        uploadRef.current
          .then(url => {
            if (!cancelled) {
              setCard(prev => (prev.status === 'ready' ? { ...prev, publicUrl: url } : prev))
            }
          })
          .catch(() => {
            uploadRef.current = null
          })
      } catch (error) {
        console.error(error)
        if (!cancelled) setCard({ status: 'error', message: 'Не получилось собрать карточку' })
      }
    }

    // Даём существу один кадр «устояться» после анимации.
    const timer = window.setTimeout(build, 120)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [starRef, archetype, accent, theme])

  async function shareStory() {
    if (card.status !== 'ready') return
    setBusy(true)
    setNote(null)
    try {
      const { publicUrl, blob } = card
      const pending =
        uploadRef.current ??
        characterApi.uploadShareCard(blob).then(res => res.url)
      const url: string = publicUrl ?? (await pending)

      const webApp = getWebApp()
      if (canStory && webApp?.shareToStory) {
        webApp.shareToStory(url, {
          text: `моя косметичка — это ${T.name} ✨ а твоя? @${BOT_USERNAME}`,
          widget_link: { url: BOT_LINK, name: 'Собрать своё' },
        })
      } else if (navigator.canShare?.({ files: [new File([card.blob], 'cosmi.png', { type: 'image/png' })] })) {
        await navigator.share({
          files: [new File([card.blob], 'cosmi.png', { type: 'image/png' })],
          title: 'моя косметичка выглядит так',
        })
      } else {
        setNote('Сторис доступны в свежей версии Telegram — обнови приложение')
        return
      }

      haptic('success')
      trackCharacterEvent('character_shared', { channel: 'story', archetype, source })
      characterApi.markShared().catch(() => undefined)
    } catch (error) {
      console.error(error)
      setNote('Не вышло загрузить картинку, попробуй ещё раз')
    } finally {
      setBusy(false)
    }
  }

  function sendToFriend() {
    const text = `моя косметичка — это ${T.name}. собери своё существо из косметики 👇`
    const link = `https://t.me/share/url?url=${encodeURIComponent(BOT_LINK)}&text=${encodeURIComponent(text)}`
    const webApp = getWebApp()
    if (webApp?.openTelegramLink) webApp.openTelegramLink(link)
    else window.open(link, '_blank', 'noopener')

    haptic('light')
    trackCharacterEvent('character_shared', { channel: 'friend', archetype, source })
    characterApi.markShared().catch(() => undefined)
  }

  return (
    <div className="cs-share">
      <div className="cs-share-card">
        {card.status === 'ready' && <img src={card.previewUrl} alt="Карточка для сторис" />}
        {card.status === 'building' && <div className="cs-share-placeholder">собираю карточку…</div>}
        {card.status === 'error' && <div className="cs-share-placeholder">{card.message}</div>}
      </div>

      <div className="cs-share-actions">
        <button
          type="button"
          className="cs-btn cs-btn-primary"
          onClick={shareStory}
          disabled={card.status !== 'ready' || busy}
        >
          {busy ? 'Загружаю…' : 'Выложить в сторис'}
        </button>
        <button type="button" className="cs-btn cs-btn-ghost" onClick={sendToFriend}>
          Отправить подруге
        </button>
        <button type="button" className="cs-btn cs-btn-text" onClick={onClose}>
          Позже
        </button>
      </div>
      {note && <p className="cs-share-note">{note}</p>}
    </div>
  )
}
