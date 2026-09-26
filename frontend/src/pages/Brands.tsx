import { useEffect, useMemo, useState } from 'react'

import { getTelegramAuthHeaders } from '../lib/telegram'

type Tab = 'all' | 'tracked' | 'sale'

type Brand = {
  id: number
  name: string
  slug: string
  image_url: string | null
}

type BrandSubscription = {
  id: number
  enabled: boolean
  brand: Brand
}

const API_BASE =
  import.meta.env.VITE_API_BASE ||
  'https://you-beauty-dev-production.up.railway.app/api'

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
    useState<BrandSubscription[]>([])

  const [loading, setLoading] =
    useState(true)

  const [saving, setSaving] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)

  useEffect(() => {
    loadBrands()
  }, [])

  async function loadBrands() {
    setLoading(true)
    setError(null)

    try {
      const headers =
        getTelegramAuthHeaders()

      if (
        !headers['X-Telegram-Init-Data']
      ) {
        throw new Error(
          'Открой You Beauty через Telegram, чтобы загрузить бренды.'
        )
      }

      const response = await fetch(
        `${API_BASE}/brand-subscriptions`,
        {
          headers,
        }
      )

      const data =
        await response.json()

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            `Ошибка загрузки: ${response.status}`
        )
      }

      setBrands(
        Array.isArray(data)
          ? data
          : []
      )
    } catch (err) {
      console.error(err)

      setError(
        err instanceof Error
          ? err.message
          : 'Не удалось загрузить бренды'
      )
    } finally {
      setLoading(false)
    }
  }

  async function followBrand() {
    const cleanName =
      query.trim()

    if (!cleanName) return

    setSaving(true)
    setError(null)

    try {
      const authHeaders =
        getTelegramAuthHeaders()

      if (
        !authHeaders[
          'X-Telegram-Init-Data'
        ]
      ) {
        throw new Error(
          'Открой You Beauty через Telegram, чтобы сохранить бренд.'
        )
      }

      const response = await fetch(
        `${API_BASE}/brand-subscriptions`,
        {
          method: 'POST',
          headers: {
            'Content-Type':
              'application/json',
            ...authHeaders,
          },
          body: JSON.stringify({
            name: cleanName,
          }),
        }
      )

      const data =
        await response.json()

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            `Ошибка сохранения: ${response.status}`
        )
      }

      setQuery('')
      setSearchOpen(false)

      await loadBrands()
    } catch (err) {
      console.error(err)

      setError(
        err instanceof Error
          ? err.message
          : 'Не удалось добавить бренд'
      )
    } finally {
      setSaving(false)
    }
  }

  async function unfollowBrand(
    brandId: number
  ) {
    setError(null)

    try {
      const authHeaders =
        getTelegramAuthHeaders()

      const response = await fetch(
        `${API_BASE}/brand-subscriptions/${brandId}`,
        {
          method: 'DELETE',
          headers: authHeaders,
        }
      )

      const data =
        await response.json()

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            `Ошибка удаления: ${response.status}`
        )
      }

      setBrands(current =>
        current.filter(
          item =>
            item.brand.id !== brandId
        )
      )
    } catch (err) {
      console.error(err)

      setError(
        err instanceof Error
          ? err.message
          : 'Не удалось удалить бренд'
      )
    }
  }

  const normalizedQuery =
    query.trim()

  const exactExists =
    brands.some(
      item =>
        item.brand.name
          .toLowerCase() ===
        normalizedQuery
          .toLowerCase()
    )

  const visibleBrands =
    useMemo(() => {
      if (activeTab === 'sale') {
        return []
      }

      return brands
    }, [brands, activeTab])

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
                    Начать следить за брендом
                  </div>

                  <button
                    className="follow"
                    onClick={followBrand}
                    disabled={saving}
                  >
                    {saving
                      ? 'Сохраняю...'
                      : '＋ Следить'}
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

      {error && (
        <div
          style={{
            marginTop: '18px',
            padding: '16px 18px',
            borderRadius: '20px',
            background: '#f6e9e9',
          }}
        >
          <div
            className="mono"
            style={{
              fontSize: '12px',
              lineHeight: 1.5,
            }}
          >
            {error}
          </div>
        </div>
      )}

      {loading ? (
        <div
          className="mono"
          style={{
            padding: '40px 10px',
            textAlign: 'center',
            opacity: 0.5,
          }}
        >
          Загружаю бренды…
        </div>
      ) : activeTab === 'sale' ? (
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
      ) : visibleBrands.length > 0 ? (
        <div className="brand-list">
          {visibleBrands.map(
            item => (
              <article
                className={`brand-card ${getTone(
                  item.brand.name
                )}`}
                key={item.id}
              >
                <div>
                  <h3>
                    {item.brand.name}
                  </h3>

                  <div className="mono">
                    Отслеживаем бренд
                  </div>

                  <button
                    className="follow active"
                    onClick={() =>
                      unfollowBrand(
                        item.brand.id
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
            Мы сохраним его
            в твоём Telegram-аккаунте.
          </div>
        </div>
      )}
    </main>
  )
}
