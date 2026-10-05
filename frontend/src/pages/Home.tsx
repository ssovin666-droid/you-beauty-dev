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
              width: '170px',
              height: '170px',
              right: '5%',
              top: '50%',
              transform:
                'translateY(-50%)',
            }}
          >
            <div
              style={{
                position: 'absolute',
                width: '150px',
                height: '150px',
                left: '6px',
                top: '8px',
                borderRadius: '50%',
                background:
                  'radial-gradient(circle at 38% 30%, rgba(255,255,255,.88), rgba(206,224,237,.28) 44%, rgba(237,207,218,.2) 68%, transparent 74%)',
                filter: 'blur(1px)',
              }}
            />

            <div
              style={{
                position: 'absolute',
                width: '108px',
                height: '132px',
                left: '25px',
                top: '16px',
                borderRadius:
                  '54% 46% 58% 42% / 45% 55% 45% 55%',
                transform:
                  'rotate(17deg)',
                background:
                  'linear-gradient(145deg, rgba(255,255,255,.9) 3%, rgba(221,236,244,.7) 32%, rgba(187,211,229,.52) 58%, rgba(237,203,214,.42) 100%)',
                border:
                  '1px solid rgba(255,255,255,.88)',
                boxShadow:
                  'inset 15px 12px 28px rgba(255,255,255,.65), inset -12px -14px 28px rgba(111,145,170,.09), 0 22px 38px rgba(72,97,116,.12)',
                backdropFilter:
                  'blur(12px)',
              }}
            />

            <div
              style={{
                position: 'absolute',
                width: '74px',
                height: '104px',
                right: '18px',
                bottom: '16px',
                borderRadius:
                  '48% 52% 44% 56% / 55% 45% 55% 45%',
                transform:
                  'rotate(-24deg)',
                background:
                  'linear-gradient(155deg, rgba(255,255,255,.76), rgba(226,212,228,.46) 48%, rgba(181,211,229,.46))',
                border:
                  '1px solid rgba(255,255,255,.78)',
                boxShadow:
                  'inset 8px 10px 20px rgba(255,255,255,.6), 0 15px 28px rgba(79,103,122,.08)',
              }}
            />

            <div
              style={{
                position: 'absolute',
                width: '47px',
                height: '47px',
                left: '63px',
                top: '61px',
                borderRadius: '50%',
                background:
                  'radial-gradient(circle at 32% 27%, #ffffff 0 14%, #edf5f8 24%, #d7e7ee 54%, #e4cdd2 100%)',
                border:
                  '1px solid rgba(255,255,255,.95)',
                boxShadow:
                  '0 10px 24px rgba(72,101,122,.16), inset 5px 5px 8px rgba(255,255,255,.88)',
                zIndex: 4,
              }}
            />

            <div
              style={{
                position: 'absolute',
                width: '38px',
                height: '8px',
                left: '38px',
                top: '39px',
                borderRadius: '999px',
                transform:
                  'rotate(-36deg)',
                background:
                  'rgba(255,255,255,.8)',
                filter: 'blur(1.5px)',
                zIndex: 5,
              }}
            />

            <div
              style={{
                position: 'absolute',
                right: '9px',
                top: '22px',
                width: '22px',
                height: '22px',
              }}
            >
              <span
                style={{
                  position: 'absolute',
                  left: '10px',
                  top: 0,
                  width: '2px',
                  height: '22px',
                  borderRadius: '999px',
                  background:
                    'rgba(255,255,255,.9)',
                }}
              />

              <span
                style={{
                  position: 'absolute',
                  left: 0,
                  top: '10px',
                  width: '22px',
                  height: '2px',
                  borderRadius: '999px',
                  background:
                    'rgba(255,255,255,.9)',
                }}
              />
            </div>

            <div
              style={{
                position: 'absolute',
                left: '13px',
                bottom: '23px',
                width: '10px',
                height: '10px',
                borderRadius: '50%',
                background:
                  'rgba(255,255,255,.88)',
                boxShadow:
                  '0 0 18px rgba(255,255,255,.95)',
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
