import { useEffect, useState } from 'react'

import { getTelegramAuthHeaders } from '../lib/telegram'

type Tab = 'wishlist' | 'shelf' | 'brands'

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

type SavedBrand = {
  name: string
  followed: boolean
}

const API_BASE =
  import.meta.env.VITE_API_BASE ||
  'https://you-beauty-dev-production.up.railway.app/api'

const BRANDS_KEY =
  'you_beauty_followed_brands'

function readBrands(): SavedBrand[] {
  try {
    const raw =
      localStorage.getItem(BRANDS_KEY)

    if (!raw) return []

    const parsed = JSON.parse(raw)

    return Array.isArray(parsed)
      ? parsed.filter(
          brand => brand.followed
        )
      : []
  } catch {
    return []
  }
}

export function Home({ go }: HomeProps) {
  const [wishlist, setWishlist] =
    useState<TrackedItem[]>([])

  const [shelf, setShelf] =
    useState<TrackedItem[]>([])

  const [brands, setBrands] =
    useState<SavedBrand[]>([])

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
        setBrands(readBrands())

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

      setBrands(
        readBrands()
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

        <button
          className="icon-btn"
          aria-label="Профиль"
          onClick={() => {
            alert(
              'Профиль пользователя подключим следующим этапом.'
            )
          }}
        >
          ◎
        </button>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <h2>
            Твоя косметика
            <br />
            под контролем
          </h2>

          <p className="mono">
            Добавляй любимые средства
            и узнавай о скидках первой.
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

      <section className="brand-strip">
        <div className="section-heading">
          <h3>
            Бренды
          </h3>

          <button
            onClick={() =>
              go('brands')
            }
          >
            Все бренды →
          </button>
        </div>

        <div className="brand-pills">
          {brands
            .slice(0, 3)
            .map(brand => (
              <span key={brand.name}>
                {brand.name}
              </span>
            ))}

          <button
            onClick={() =>
              go('brands')
            }
          >
            ＋ Добавить
          </button>
        </div>

        {brands.length === 0 && (
          <div
            className="mono"
            style={{
              marginTop: '12px',
              opacity: 0.5,
              fontSize: '12px',
            }}
          >
            Ты пока не отслеживаешь
            ни одного бренда
          </div>
        )}
      </section>
    </main>
  )
}
