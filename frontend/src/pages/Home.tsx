import { useEffect, useState } from 'react'

import type { Tab } from '../components/BottomNav'
import { getTelegramAuthHeaders } from '../lib/telegram'

type HomeProps = {
  go: (tab: Tab) => void
}

type TrackedItem = {
  id: number
  list_type: 'wishlist' | 'shelf'
  notifications_enabled: boolean
  product: {
    id: number
    name: string
    variant: string | null
    size: string | null
    category: string | null
    image_url: string | null
    brand: {
      id: number
      name: string
      slug: string
      image_url: string | null
    } | null
  }
}

const API_BASE =
  import.meta.env.VITE_API_BASE ||
  'https://you-beauty-dev-production.up.railway.app/api'

export function Home({ go }: HomeProps) {
  const [wishlist, setWishlist] =
    useState<TrackedItem[]>([])

  const [shelf, setShelf] =
    useState<TrackedItem[]>([])

  const [loading, setLoading] =
    useState(true)

  const [error, setError] =
    useState<string | null>(null)

  async function loadHomeData() {
    setLoading(true)
    setError(null)

    try {
      const headers =
        getTelegramAuthHeaders()

      if (
        !headers[
          'X-Telegram-Init-Data'
        ]
      ) {
        setWishlist([])
        setShelf([])

        setError(
          'Открой You Beauty через Telegram, чтобы загрузить сохранения.'
        )

        return
      }

      const [
        wishlistResponse,
        shelfResponse,
      ] = await Promise.all([
        fetch(
          `${API_BASE}/tracked?list_type=wishlist`,
          {
            headers,
          }
        ),
        fetch(
          `${API_BASE}/tracked?list_type=shelf`,
          {
            headers,
          }
        ),
      ])

      const wishlistData =
        await wishlistResponse.json()

      const shelfData =
        await shelfResponse.json()

      if (!wishlistResponse.ok) {
        throw new Error(
          wishlistData?.detail ||
            `Ошибка Wishlist: ${wishlistResponse.status}`
        )
      }

      if (!shelfResponse.ok) {
        throw new Error(
          shelfData?.detail ||
            `Ошибка Полки: ${shelfResponse.status}`
        )
      }

      setWishlist(
        Array.isArray(wishlistData)
          ? wishlistData
          : []
      )

      setShelf(
        Array.isArray(shelfData)
          ? shelfData
          : []
      )
    } catch (err) {
      console.error(err)

      setError(
        err instanceof Error
          ? err.message
          : 'Не удалось загрузить данные'
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadHomeData()

    function handleVisibility() {
      if (
        document.visibilityState ===
        'visible'
      ) {
        loadHomeData()
      }
    }

    document.addEventListener(
      'visibilitychange',
      handleVisibility
    )

    window.addEventListener(
      'focus',
      loadHomeData
    )

    return () => {
      document.removeEventListener(
        'visibilitychange',
        handleVisibility
      )

      window.removeEventListener(
        'focus',
        loadHomeData
      )
    }
  }, [])

  return (
    <main className="screen home-screen">
      <header className="topbar">
        <div>
          <div className="eyebrow mono">
            BEAUTY PRICE TRACKING
          </div>

          <h1>
            You Beauty
          </h1>
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <h2>
            Твои текущие
            <br />
            скидки
          </h2>

          <p className="mono">
            Пока ни один из твоих
            товаров не на скидке
          </p>
        </div>

        <div
          className="hero-art"
          aria-hidden="true"
        >
          <div className="orb orb-a" />
          <div className="orb orb-b" />
          <div className="hero-bottle" />
        </div>
      </section>

      {error && (
        <div
          className="mono"
          style={{
            marginBottom: '18px',
            padding: '12px 15px',
            borderRadius: '16px',
            background: '#f6e9e9',
            fontSize: '11px',
            lineHeight: 1.5,
          }}
        >
          {error}
        </div>
      )}

      <section className="dashboard-cards">
        <button
          className="dashboard-card blue"
          onClick={() =>
            go('wishlist')
          }
        >
          <div>
            <span className="big-icon">
              ♡
            </span>

            <h3>
              Wishlist
            </h3>

            <p className="mono">
              То, что хочется купить
            </p>

            <div className="mono stats">
              {loading
                ? 'Загружаю...'
                : `${wishlist.length} ${
                    wishlist.length === 1
                      ? 'товар'
                      : 'товаров'
                  }`}
            </div>
          </div>

          <span className="arrow">
            ›
          </span>
        </button>

        <button
          className="dashboard-card rose"
          onClick={() =>
            go('shelf')
          }
        >
          <div>
            <span className="big-icon">
              ▣
            </span>

            <h3>
              Полка
            </h3>

            <p className="mono">
              То, что хочется
              покупать снова
            </p>

            <div className="mono stats">
              {loading
                ? 'Загружаю...'
                : `${shelf.length} ${
                    shelf.length === 1
                      ? 'товар'
                      : 'товаров'
                  }`}
            </div>
          </div>

          <span className="arrow">
            ›
          </span>
        </button>
      </section>
    </main>
  )
}
