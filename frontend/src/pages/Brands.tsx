import { useEffect, useMemo, useState } from 'react'

type Tab = 'all' | 'tracked' | 'sale'

type SavedBrand = {
  name: string
  followed: boolean
}

const STORAGE_KEY = 'you_beauty_followed_brands'

function getTone(name: string) {
  const tones = ['blue', 'green', 'rose']

  const sum = name
    .split('')
    .reduce(
      (total, char) =>
        total + char.charCodeAt(0),
      0
    )

  return tones[sum % tones.length]
}

export function Brands() {
  const [activeTab, setActiveTab] =
    useState<Tab>('all')

  const [searchOpen, setSearchOpen] =
    useState(false)

  const [query, setQuery] =
    useState('')

  const [brands, setBrands] =
    useState<SavedBrand[]>([])

  useEffect(() => {
    const saved =
      localStorage.getItem(STORAGE_KEY)

    if (!saved) return

    try {
      const parsed = JSON.parse(saved)

      if (Array.isArray(parsed)) {
        setBrands(parsed)
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY)
    }
  }, [])

  function saveBrands(next: SavedBrand[]) {
    setBrands(next)

    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(next)
    )

    window.dispatchEvent(
      new Event('you-beauty-data-changed')
    )
  }

  function followBrand(name: string) {
    const cleanName = name.trim()

    if (!cleanName) return

    const existing = brands.find(
      brand =>
        brand.name.toLowerCase() ===
        cleanName.toLowerCase()
    )

    if (existing) {
      const next = brands.map(brand =>
        brand.name.toLowerCase() ===
        cleanName.toLowerCase()
          ? {
              ...brand,
              followed: true,
            }
          : brand
      )

      saveBrands(next)
    } else {
      saveBrands([
        ...brands,
        {
          name: cleanName,
          followed: true,
        },
      ])
    }

    setQuery('')
    setSearchOpen(false)
  }

  function unfollowBrand(name: string) {
    const next = brands.filter(
      brand => brand.name !== name
    )

    saveBrands(next)
  }

  const followedBrands = useMemo(
    () =>
      brands.filter(
        brand => brand.followed
      ),
    [brands]
  )

  const normalizedQuery =
    query.trim()

  const exactExists =
    followedBrands.some(
      brand =>
        brand.name.toLowerCase() ===
        normalizedQuery.toLowerCase()
    )

  return (
    <main className="screen list-screen">
      <header className="list-header">
        <div>
          <h1>Бренды</h1>

          <div className="mono subhead">
            Следи за любимыми брендами
            и не пропускай скидки
          </div>
        </div>

        <button
          className="icon-btn"
          onClick={() =>
            setSearchOpen(
              value => !value
            )
          }
          aria-label="Поиск бренда"
        >
          ⌕
        </button>
      </header>

      {searchOpen && (
        <div
          style={{
            marginBottom: '18px',
          }}
        >
          <input
            autoFocus
            value={query}
            onChange={event =>
              setQuery(
                event.target.value
              )
            }
            placeholder="Название бренда"
            style={{
              width: '100%',
              boxSizing: 'border-box',
              padding: '15px 17px',
              borderRadius: '18px',
              border:
                '1px solid rgba(20,30,35,0.08)',
              background: '#ffffff',
              outline: 'none',
              fontSize: '16px',
            }}
          />

          {normalizedQuery &&
            !exactExists && (
              <article
                className={`brand-card ${getTone(
                  normalizedQuery
                )}`}
                style={{
                  marginTop: '12px',
                }}
              >
                <div>
                  <h3>
                    {normalizedQuery}
                  </h3>

                  <div className="mono">
                    Начать следить
                    за брендом
                  </div>

                  <button
                    className="follow"
                    onClick={() =>
                      followBrand(
                        normalizedQuery
                      )
                    }
                  >
                    ＋ Следить
                  </button>
                </div>

                <div className="brand-art">
                  <div className="mini-bottle" />
                </div>

                <span className="arrow">
                  ›
                </span>
              </article>
            )}
        </div>
      )}

      <div className="segments">
        <button
          className={
            activeTab === 'all'
              ? 'active'
              : ''
          }
          onClick={() =>
            setActiveTab('all')
          }
        >
          Все
        </button>

        <button
          className={
            activeTab === 'tracked'
              ? 'active'
              : ''
          }
          onClick={() =>
            setActiveTab('tracked')
          }
        >
          Отслеживаемые
        </button>

        <button
          className={
            activeTab === 'sale'
              ? 'active'
              : ''
          }
          onClick={() =>
            setActiveTab('sale')
          }
        >
          На скидке
        </button>
      </div>

      {activeTab === 'sale' ? (
        <div
          style={{
            marginTop: '28px',
            padding: '52px 24px',
            textAlign: 'center',
            borderRadius: '28px',
            background:
              'linear-gradient(180deg, #f4f7f8 0%, #faf9f7 100%)',
          }}
        >
          <h3>
            Скидок пока нет
          </h3>

          <div
            className="mono"
            style={{
              marginTop: '9px',
              opacity: 0.55,
              fontSize: '13px',
              lineHeight: 1.6,
            }}
          >
            Когда у отслеживаемых
            брендов появятся скидки,
            они будут собраны здесь.
          </div>
        </div>
      ) : followedBrands.length > 0 ? (
        <div className="brand-list">
          {followedBrands.map(
            brand => (
              <article
                className={`brand-card ${getTone(
                  brand.name
                )}`}
                key={brand.name}
              >
                <div>
                  <h3>
                    {brand.name}
                  </h3>

                  <div className="mono">
                    Отслеживаем бренд
                  </div>

                  <button
                    className="follow active"
                    onClick={() =>
                      unfollowBrand(
                        brand.name
                      )
                    }
                  >
                    ✓ Отслеживается
                  </button>
                </div>

                <div className="brand-art">
                  <div className="mini-bottle" />
                </div>

                <span className="arrow">
                  ›
                </span>
              </article>
            )
          )}
        </div>
      ) : (
        <div
          style={{
            marginTop: '28px',
            padding: '52px 24px',
            textAlign: 'center',
            borderRadius: '28px',
            background:
              'linear-gradient(180deg, #f4f7f8 0%, #faf9f7 100%)',
          }}
        >
          <div
            style={{
              width: '66px',
              height: '66px',
              margin: '0 auto 18px',
              display: 'grid',
              placeItems: 'center',
              borderRadius: '22px',
              background: '#ffffff',
              fontSize: '26px',
            }}
          >
            ♡
          </div>

          <h3>
            Любимых брендов пока нет
          </h3>

          <div
            className="mono"
            style={{
              marginTop: '9px',
              opacity: 0.55,
              fontSize: '13px',
              lineHeight: 1.6,
            }}
          >
            Нажми поиск сверху
            и введи название бренда.
            <br />
            Мы будем следить
            за его скидками.
          </div>
        </div>
      )}
    </main>
  )
}
