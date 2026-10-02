import { useEffect, useState } from 'react'

import { BottomNav, type Tab } from './components/BottomNav'
import { Home } from './pages/Home'
import { Shelf } from './pages/Shelf'
import { Wishlist } from './pages/Wishlist'

import {
  getTelegramAuthHeaders,
  initTelegram,
} from './lib/telegram'

import {
  initAmplitude,
  trackOpenedYouBeauty,
} from './lib/amplitude'


const API_BASE =
  import.meta.env.VITE_API_BASE ||
  'https://you-beauty-dev-production.up.railway.app/api'


export default function App() {
  const [tab, setTab] =
    useState<Tab>('home')

  useEffect(() => {
    initTelegram()

    async function startAnalytics() {
      try {
        const headers =
          getTelegramAuthHeaders()

        if (
          !headers[
            'X-Telegram-Init-Data'
          ]
        ) {
          console.warn(
            'Telegram initData missing — Amplitude user not initialized'
          )

          return
        }

        const response = await fetch(
          `${API_BASE}/me`,
          {
            headers,
          }
        )

        if (!response.ok) {
          console.warn(
            'Telegram user validation failed — Amplitude disabled'
          )

          return
        }

        const user =
          await response.json()

        if (
          !user?.telegram_user_id
        ) {
          console.warn(
            'Validated Telegram user_id missing'
          )

          return
        }

        initAmplitude(
          user.telegram_user_id
        )

        trackOpenedYouBeauty()

      } catch (error) {
        console.error(
          'Amplitude initialization failed',
          error
        )
      }
    }

    startAnalytics()
  }, [])

  return (
    <div className="app-shell">
      {tab === 'home' && (
        <Home go={setTab} />
      )}

      {tab === 'wishlist' && (
        <Wishlist />
      )}

      {tab === 'shelf' && (
        <Shelf />
      )}

      <BottomNav
        active={tab}
        onChange={setTab}
      />
    </div>
  )
}
