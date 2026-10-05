import { useEffect, useState } from 'react'

import type { Tab } from '../components/BottomNav'
import { getTelegramAuthHeaders } from '../lib/telegram'

type HomeProps = {
  go: (tab: Tab) => void
}

type Offer = {
  id: number
  store: {
    id: number
    name: string
    slug: string
  }
  current_price: number | null
  old_price: number | null
  currency: string | null
  has_discount: boolean
  discount_percent: number | null
  in_stock: boolean
  product_url: string
  affiliate_url: string | null
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
  offer: Offer | null
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

  const allTrackedItems = [
    ...wishlist,
    ...shelf,
  ]

  const discountedItems =
    allTrackedItems.filter(
      item =>
        item.offer?.has_discount === true
    )

  const discountCount =
    discountedItems.length

  const maxDiscount =
    discountedItems.reduce(
      (max, item) => {
        const discount =
          item.offer?.discount_percent ?? 0

        return Math.max(
          max,
          discount
        )
      },
      0
    )

  function getDiscountMessage() {
    if (loading) {
      return 'Проверяю цены на твои товары…'
    }

    if (discountCount === 0) {
      return (
        <>
          Пока ни один из твоих
          <br />
          товаров не на скидке
        </>
      )
    }

    if (discountCount === 1) {
      return (
        <>
          1 твой товар сейчас
          <br />
          продаётся со скидкой
        </>
      )
    }

    if (
      discountCount >= 2 &&
      discountCount <= 4
    ) {
      return (
        <>
          {discountCount} твоих товара сейчас
          <br />
          продаются со скидкой
        </>
      )
    }

    return (
      <>
        {discountCount} твоих товаров сейчас
        <br />
        продаются со скидкой
      </>
    )
  }

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
            {getDiscountMessage()}
          </p>

          {!loading &&
            discountCount > 0 &&
            maxDiscount > 0 && (
              <div
                className="mono"
                style={{
                  marginTop: '10px',
                  fontSize: '11px',
                  opacity: 0.6,
                  letterSpacing:
                    '0.04em',
                }}
              >
                Максимальная скидка −
                {maxDiscount}%
              </div>
            )}
        </div>

        <div
          className="hero-art"
          aria-hidden="true"
        >
          <div className="orb orb-a" />
          <div className="orb orb-b" />

          <div
            style={{
              position: 'absolute',
              width: '160px',
              height: '160px',
              right: '8%',
              top: '50%',
              transform:
                'translateY(-50%) rotate(-8deg)',
              filter:
                'drop-shadow(0 20px 28px rgba(86,111,130,0.14))',
            }}
          >
            <span
              style={{
                position: 'absolute',
                width: '74px',
                height: '74px',
                left: '8px',
                top: '8px',
                borderRadius:
                  '60% 42% 58% 44%',
                transform:
                  'rotate(-8deg)',
                background:
                  'linear-gradient(145deg, rgba(255,255,255,.95), rgba(198,220,235,.58) 52%, rgba(239,211,217,.48))',
                border:
                  '1px solid rgba(255,255,255,.9)',
                boxShadow:
                  'inset 8px 10px 18px rgba(255,255,255,.72), 0 9px 20px rgba(83,108,126,.10)',
              }}
            />

            <span
              style={{
                position: 'absolute',
                width: '74px',
                height: '74px',
                right: '8px',
                top: '8px',
                borderRadius:
                  '60% 42% 58% 44%',
                transform:
                  'rotate(82deg)',
                background:
                  'linear-gradient(145deg, rgba(255,255,255,.95), rgba(205,226,236,.55) 50%, rgba(238,206,218,.5))',
                border:
                  '1px solid rgba(255,255,255,.9)',
                boxShadow:
                  'inset 8px 10px 18px rgba(255,255,255,.72), 0 9px 20px rgba(83,108,126,.10)',
              }}
            />

            <span
              style={{
                position: 'absolute',
                width: '74px',
                height: '74px',
                left: '8px',
                bottom: '8px',
                borderRadius:
                  '60% 42% 58% 44%',
                transform:
                  'rotate(-98deg)',
                background:
                  'linear-gradient(145deg, rgba(255,255,255,.95), rgba(213,228,237,.52) 48%, rgba(242,214,218,.52))',
                border:
                  '1px solid rgba(255,255,255,.9)',
                boxShadow:
                  'inset 8px 10px 18px rgba(255,255,255,.72), 0 9px 20px rgba(83,108,126,.10)',
              }}
            />

            <span
              style={{
                position: 'absolute',
                width: '74px',
                height: '74px',
                right: '8px',
                bottom: '8px',
                borderRadius:
                  '60% 42% 58% 44%',
                transform:
                  'rotate(172deg)',
                background:
                  'linear-gradient(145deg, rgba(255,255,255,.95), rgba(198,219,234,.55) 50%, rgba(240,208,216,.48))',
                border:
                  '1px solid rgba(255,255,255,.9)',
                boxShadow:
                  'inset 8px 10px 18px rgba(255,255,255,.72), 0 9px 20px rgba(83,108,126,.10)',
              }}
            />

            <span
              style={{
                position: 'absolute',
                width: '42px',
                height: '42px',
                left: '50%',
                top: '50%',
                transform:
                  'translate(-50%, -50%)',
                borderRadius: '50%',
                background:
                  'radial-gradient(circle at 32% 26%, #ffffff 0 18%, #dceaf1 44%, #e9cfd3 100%)',
                border:
                  '1px solid rgba(255,255,255,.92)',
                boxShadow:
                  '0 7px 20px rgba(73,102,125,.16), inset 4px 5px 8px rgba(255,255,255,.82)',
                zIndex: 2,
              }}
            />

            <span
              style={{
                position: 'absolute',
                width: '37px',
                height: '12px',
                left: '28px',
                top: '32px',
                borderRadius: '999px',
                background:
                  'rgba(255,255,255,.72)',
                filter: 'blur(2px)',
                transform:
                  'rotate(-28deg)',
                zIndex: 3,
              }}
            />
          </div>
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
