import { useEffect, useState } from 'react'

type Tab = 'wishlist' | 'shelf' | 'brands'

type HomeProps = {
  go: (tab: Tab) => void
}

type SavedBrand = {
  name: string
  followed: boolean
}

type SavedProduct = {
  id?: number | string
  discount?: number | null
  has_discount?: boolean
}

const WISHLIST_KEY = 'you_beauty_wishlist'
const SHELF_KEY = 'you_beauty_shelf'
const BRANDS_KEY = 'you_beauty_followed_brands'

function readProducts(key: string): SavedProduct[] {
  try {
    const raw = localStorage.getItem(key)

    if (!raw) return []

    const parsed = JSON.parse(raw)

    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function readBrands(): SavedBrand[] {
  try {
    const raw = localStorage.getItem(BRANDS_KEY)

    if (!raw) return []

    const parsed = JSON.parse(raw)

    return Array.isArray(parsed)
      ? parsed.filter(brand => brand.followed)
      : []
  } catch {
    return []
  }
}

function countDiscounted(
  products: SavedProduct[]
) {
  return products.filter(product => {
    if (product.has_discount === true) {
      return true
    }

    return (
      typeof product.discount === 'number' &&
      product.discount > 0
    )
  }).length
}

export function Home({ go }: HomeProps) {
  const [wishlist, setWishlist] =
    useState<SavedProduct[]>([])

  const [shelf, setShelf] =
    useState<SavedProduct[]>([])

  const [brands, setBrands] =
    useState<SavedBrand[]>([])

  function refreshData() {
    setWishlist(
      readProducts(WISHLIST_KEY)
    )

    setShelf(
      readProducts(SHELF_KEY)
    )

    setBrands(
      readBrands()
    )
  }

  useEffect(() => {
    refreshData()

    window.addEventListener(
      'storage',
      refreshData
    )

    window.addEventListener(
      'you-beauty-data-changed',
      refreshData
    )

    return () => {
      window.removeEventListener(
        'storage',
        refreshData
      )

      window.removeEventListener(
        'you-beauty-data-changed',
        refreshData
      )
    }
  }, [])

  const wishlistDiscounts =
    countDiscounted(wishlist)

  const shelfDiscounts =
    countDiscounted(shelf)

  return (
    <main className="screen home-screen">
      <header className="topbar">
        <div>
          <div className="eyebrow mono">
            BEAUTY PRICE TRACKING
          </div>

          <h1>You Beauty</h1>
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

            <h3>Wishlist</h3>

            <p className="mono">
              То, что хочется купить
            </p>

            <div className="mono stats">
              {wishlist.length}{' '}
              {wishlist.length === 1
                ? 'товар'
                : 'товаров'}

              {wishlistDiscounts > 0 && (
                <>
                  {' · '}
                  <em>
                    {wishlistDiscounts}{' '}
                    со скидкой
                  </em>
                </>
              )}
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

            <h3>Полка</h3>

            <p className="mono">
              То, что хочется покупать снова
            </p>

            <div className="mono stats">
              {shelf.length}{' '}
              {shelf.length === 1
                ? 'товар'
                : 'товаров'}

              {shelfDiscounts > 0 && (
                <>
                  {' · '}
                  <em>
                    {shelfDiscounts}{' '}
                    со скидкой
                  </em>
                </>
              )}
            </div>
          </div>

          <span className="arrow">
            ›
          </span>
        </button>
      </section>

      <section className="brand-strip">
        <div className="section-heading">
          <h3>Бренды</h3>

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
