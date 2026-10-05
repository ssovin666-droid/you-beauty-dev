import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'

import { getTelegramAuthHeaders } from '../lib/telegram'
import {
  trackAddedProductToWishlist,
  trackStartedAddingProductToWishlist,
} from '../lib/amplitude'

const API_BASE =
  import.meta.env.VITE_API_BASE ||
  'https://you-beauty-dev-production.up.railway.app/api'

type RecognitionResult = {
  brand: string | null
  product_name: string | null
  variant: string | null
  size: string | null
  category: string | null
  confidence: number
}

type SavedProduct = {
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
  list_type: string
  notifications_enabled: boolean
  product: SavedProduct
  offer: Offer | null
}

function formatPrice(
  value: number | null,
  currency: string | null
) {
  if (value === null) return null

  const formatted = new Intl.NumberFormat(
    'ru-RU',
    {
      maximumFractionDigits:
        Number.isInteger(value) ? 0 : 2,
    }
  ).format(value)

  if (currency === 'RUB') {
    return `${formatted} ₽`
  }

  if (currency) {
    return `${formatted} ${currency}`
  }

  return formatted
}

function PriceBlock({
  offer,
}: {
  offer: Offer | null
}) {
  if (
    !offer ||
    offer.current_price === null
  ) {
    return (
      <div
        className="mono"
        style={{
          marginTop: '16px',
          paddingTop: '14px',
          borderTop:
            '1px solid rgba(20,30,35,0.07)',
          fontSize: '11px',
          opacity: 0.45,
        }}
      >
        Цена пока не найдена
      </div>
    )
  }

  return (
    <div
      style={{
        marginTop: '16px',
        paddingTop: '14px',
        borderTop:
          '1px solid rgba(20,30,35,0.07)',
      }}
    >
      {offer.has_discount ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: '10px',
            flexWrap: 'wrap',
          }}
        >
          {offer.old_price !== null && (
            <span
              className="mono"
              style={{
                fontSize: '13px',
                opacity: 0.45,
                textDecoration:
                  'line-through',
              }}
            >
              {formatPrice(
                offer.old_price,
                offer.currency
              )}
            </span>
          )}

          <strong
            style={{
              fontSize: '20px',
              color: '#c94f5c',
            }}
          >
            {formatPrice(
              offer.current_price,
              offer.currency
            )}
          </strong>

          {offer.discount_percent !== null && (
            <span
              className="mono"
              style={{
                fontSize: '11px',
                color: '#c94f5c',
              }}
            >
              −{offer.discount_percent}%
            </span>
          )}
        </div>
      ) : (
        <strong
          style={{
            fontSize: '19px',
          }}
        >
          {formatPrice(
            offer.current_price,
            offer.currency
          )}
        </strong>
      )}
    </div>
  )
}

export function Wishlist() {
  const fileInputRef =
    useRef<HTMLInputElement>(null)

  const [loading, setLoading] =
    useState(false)

  const [saving, setSaving] =
    useState(false)

  const [loadingItems, setLoadingItems] =
    useState(true)

  const [result, setResult] =
    useState<RecognitionResult | null>(null)

  const [error, setError] =
    useState<string | null>(null)

  const [accountError, setAccountError] =
    useState<string | null>(null)

  const [success, setSuccess] =
    useState<string | null>(null)

  const [imagePreview, setImagePreview] =
    useState<string | null>(null)

  const [items, setItems] =
    useState<TrackedItem[]>([])

  const [deletingItemId, setDeletingItemId] =
    useState<number | null>(null)

  useEffect(() => {
    loadWishlist()
  }, [])

  useEffect(() => {
    return () => {
      if (imagePreview) {
        URL.revokeObjectURL(imagePreview)
      }
    }
  }, [imagePreview])

  async function loadWishlist() {
    setLoadingItems(true)
    setAccountError(null)

    try {
      const headers =
        getTelegramAuthHeaders()

      if (
        !headers['X-Telegram-Init-Data']
      ) {
        setAccountError(
          'Открой You Beauty через Telegram, чтобы загрузить сохранённый Wishlist.'
        )

        setItems([])
        return
      }

      const response = await fetch(
        `${API_BASE}/tracked?list_type=wishlist`,
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

      setItems(
        Array.isArray(data)
          ? data
          : []
      )
    } catch (err) {
      console.error(err)

      setAccountError(
        err instanceof Error
          ? err.message
          : 'Не удалось загрузить Wishlist'
      )
    } finally {
      setLoadingItems(false)
    }
  }

  function openFilePicker() {
    trackStartedAddingProductToWishlist()
    fileInputRef.current?.click()
  }

  async function handleFileChange(
    event: ChangeEvent<HTMLInputElement>
  ) {
    const file =
      event.target.files?.[0]

    if (!file) return

    if (imagePreview) {
      URL.revokeObjectURL(
        imagePreview
      )
    }

    const preview =
      URL.createObjectURL(file)

    setImagePreview(preview)
    setLoading(true)
    setResult(null)
    setError(null)
    setSuccess(null)

    try {
      const formData =
        new FormData()

      formData.append(
        'file',
        file
      )

      const response = await fetch(
        `${API_BASE}/recognize`,
        {
          method: 'POST',
          body: formData,
        }
      )

      const data =
        await response.json()

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            `Ошибка распознавания: ${response.status}`
        )
      }

      setResult(data.result)
    } catch (err) {
      console.error(err)

      setError(
        err instanceof Error
          ? err.message
          : 'Не удалось распознать товар'
      )
    } finally {
      setLoading(false)
      event.target.value = ''
    }
  }

  async function saveToWishlist() {
    if (!result) return

    if (!result.product_name) {
      setError(
        'AI не определил название товара. Попробуй другое фото.'
      )
      return
    }

    setSaving(true)
    setError(null)
    setAccountError(null)
    setSuccess(null)

    try {
      const authHeaders =
        getTelegramAuthHeaders()

      if (
        !authHeaders[
          'X-Telegram-Init-Data'
        ]
      ) {
        throw new Error(
          'Открой You Beauty через Telegram, чтобы сохранить товар в аккаунт.'
        )
      }

      const response = await fetch(
        `${API_BASE}/tracked/recognized`,
        {
          method: 'POST',
          headers: {
            'Content-Type':
              'application/json',
            ...authHeaders,
          },
          body: JSON.stringify({
            list_type: 'wishlist',
            brand: result.brand,
            product_name:
              result.product_name,
            variant:
              result.variant,
            size: result.size,
            category:
              result.category,
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

      trackAddedProductToWishlist()

      await loadWishlist()

      setSuccess(
        'Товар сохранён в твой Wishlist'
      )

      setResult(null)

      if (imagePreview) {
        URL.revokeObjectURL(
          imagePreview
        )
      }

      setImagePreview(null)
    } catch (err) {
      console.error(err)

      setAccountError(
        err instanceof Error
          ? err.message
          : 'Не удалось сохранить товар'
      )
    } finally {
      setSaving(false)
    }
  }

  async function deleteWishlistItem(
    trackedItemId: number
  ) {
    const confirmed = window.confirm(
      'Удалить этот товар из Wishlist?'
    )

    if (!confirmed) return

    setDeletingItemId(trackedItemId)
    setAccountError(null)
    setSuccess(null)

    try {
      const authHeaders =
        getTelegramAuthHeaders()

      if (
        !authHeaders[
          'X-Telegram-Init-Data'
        ]
      ) {
        throw new Error(
          'Открой You Beauty через Telegram, чтобы удалить товар.'
        )
      }

      const response = await fetch(
        `${API_BASE}/tracked/${trackedItemId}`,
        {
          method: 'DELETE',
          headers: authHeaders,
        }
      )

      const data = await response
        .json()
        .catch(() => null)

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            `Ошибка удаления: ${response.status}`
        )
      }

      setItems(currentItems =>
        currentItems.filter(
          item =>
            item.id !== trackedItemId
        )
      )

      setSuccess(
        'Товар удалён из Wishlist'
      )
    } catch (err) {
      console.error(err)

      setAccountError(
        err instanceof Error
          ? err.message
          : 'Не удалось удалить товар'
      )
    } finally {
      setDeletingItemId(null)
    }
  }

  const discountCount = items.filter(
    item => item.offer?.has_discount
  ).length

  const discountLabel =
    discountCount === 1
      ? '1 скидка сегодня'
      : discountCount >= 2 &&
          discountCount <= 4
        ? `${discountCount} скидки сегодня`
        : `${discountCount} скидок сегодня`

  return (
    <main className="screen list-screen">
      <header className="list-header">
        <div>
          <h1>Wishlist</h1>

          <div className="mono subhead">
            {items.length}{' '}
            {items.length === 1
              ? 'товар'
              : 'товаров'}
            {' · '}
            {discountLabel}
          </div>
        </div>

        <div
          aria-hidden="true"
          style={{
            position: 'relative',
            width: '58px',
            height: '58px',
            flex: '0 0 auto',
          }}
        >
          <div
            style={{
              position: 'absolute',
              width: '44px',
              height: '52px',
              left: '5px',
              top: '2px',
              borderRadius:
                '54% 46% 58% 42% / 45% 55% 45% 55%',
              transform:
                'rotate(17deg)',
              background:
                'linear-gradient(145deg, rgba(255,255,255,.92) 3%, rgba(221,236,244,.72) 34%, rgba(187,211,229,.54) 60%, rgba(237,203,214,.44) 100%)',
              border:
                '1px solid rgba(255,255,255,.9)',
              boxShadow:
                'inset 6px 5px 12px rgba(255,255,255,.68), 0 8px 15px rgba(72,97,116,.10)',
            }}
          />

          <div
            style={{
              position: 'absolute',
              width: '31px',
              height: '39px',
              right: '2px',
              bottom: '3px',
              borderRadius:
                '48% 52% 44% 56% / 55% 45% 55% 45%',
              transform:
                'rotate(-24deg)',
              background:
                'linear-gradient(155deg, rgba(255,255,255,.78), rgba(226,212,228,.48) 48%, rgba(181,211,229,.48))',
              border:
                '1px solid rgba(255,255,255,.8)',
              boxShadow:
                'inset 4px 5px 9px rgba(255,255,255,.6), 0 6px 12px rgba(79,103,122,.08)',
            }}
          />

          <div
            style={{
              position: 'absolute',
              width: '18px',
              height: '18px',
              left: '21px',
              top: '20px',
              borderRadius: '50%',
              background:
                'radial-gradient(circle at 32% 27%, #ffffff 0 14%, #edf5f8 24%, #d7e7ee 54%, #e4cdd2 100%)',
              border:
                '1px solid rgba(255,255,255,.95)',
              boxShadow:
                '0 4px 9px rgba(72,101,122,.14), inset 2px 2px 4px rgba(255,255,255,.88)',
              zIndex: 3,
            }}
          />

          <div
            style={{
              position: 'absolute',
              width: '14px',
              height: '3px',
              left: '12px',
              top: '12px',
              borderRadius: '999px',
              transform:
                'rotate(-36deg)',
              background:
                'rgba(255,255,255,.8)',
              filter: 'blur(.4px)',
              zIndex: 4,
            }}
          />
        </div>
      </header>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileChange}
        style={{
          display: 'none',
        }}
      />

      <button
        className="add-button"
        onClick={openFilePicker}
        disabled={loading || saving}
      >
        {loading
          ? 'Распознаю товар...'
          : '＋ Добавить товар'}
      </button>

      {success && (
        <div
          style={{
            marginTop: '18px',
            padding: '16px 18px',
            borderRadius: '20px',
            background: '#edf4ef',
          }}
        >
          <strong>
            ✓ {success}
          </strong>
        </div>
      )}

      {accountError && (
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
            {accountError}
          </div>
        </div>
      )}

      {loading && imagePreview && (
        <div
          style={{
            marginTop: '22px',
            background: '#ffffff',
            borderRadius: '26px',
            overflow: 'hidden',
            boxShadow:
              '0 18px 50px rgba(31, 43, 50, 0.07)',
          }}
        >
          <div
            style={{
              position: 'relative',
            }}
          >
            <img
              src={imagePreview}
              alt="Добавляемый товар"
              style={{
                width: '100%',
                height: '330px',
                objectFit: 'cover',
                display: 'block',
                opacity: 0.84,
              }}
            />

            <div
              className="mono"
              style={{
                position: 'absolute',
                top: '16px',
                left: '16px',
                padding: '8px 12px',
                borderRadius: '100px',
                background:
                  'rgba(255,255,255,0.9)',
                backdropFilter:
                  'blur(10px)',
                fontSize: '11px',
                letterSpacing:
                  '0.08em',
              }}
            >
              AI SEARCH
            </div>
          </div>

          <div
            style={{
              padding:
                '20px 22px 24px',
            }}
          >
            <div
              className="mono subhead"
              style={{
                marginBottom: '7px',
              }}
            >
              ИЩУ ТОЧНЫЙ ТОВАР
            </div>

            <div
              style={{
                fontSize: '19px',
                fontWeight: 600,
              }}
            >
              Анализирую фото…
            </div>

            <div
              className="mono"
              style={{
                marginTop: '7px',
                opacity: 0.5,
                fontSize: '12px',
              }}
            >
              бренд · название · вариант · объём
            </div>
          </div>
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: '20px',
            padding: '18px 20px',
            borderRadius: '22px',
            background: '#f4e7e7',
          }}
        >
          <strong>
            Не получилось
          </strong>

          <div
            className="mono"
            style={{
              marginTop: '7px',
              opacity: 0.65,
              fontSize: '12px',
            }}
          >
            {error}
          </div>
        </div>
      )}

      {result && (
        <div
          style={{
            marginTop: '22px',
            background: '#ffffff',
            borderRadius: '28px',
            overflow: 'hidden',
            boxShadow:
              '0 20px 60px rgba(31, 43, 50, 0.08)',
          }}
        >
          {imagePreview && (
            <div
              style={{
                position: 'relative',
                background: '#eef3f5',
              }}
            >
              <img
                src={imagePreview}
                alt={
                  result.product_name ||
                  'Распознанный товар'
                }
                style={{
                  width: '100%',
                  height: '350px',
                  objectFit: 'cover',
                  display: 'block',
                }}
              />

              <div
                className="mono"
                style={{
                  position:
                    'absolute',
                  top: '16px',
                  left: '16px',
                  padding:
                    '8px 12px',
                  borderRadius:
                    '100px',
                  background:
                    'rgba(255,255,255,0.92)',
                  backdropFilter:
                    'blur(12px)',
                  fontSize: '11px',
                  letterSpacing:
                    '0.08em',
                }}
              >
                FOUND
              </div>

              <div
                style={{
                  position:
                    'absolute',
                  right: '16px',
                  top: '16px',
                  width: '42px',
                  height: '42px',
                  borderRadius: '50%',
                  display: 'grid',
                  placeItems: 'center',
                  background:
                    'rgba(255,255,255,0.92)',
                  fontSize: '20px',
                }}
              >
                ♡
              </div>
            </div>
          )}

          <div
            style={{
              padding: '24px',
            }}
          >
            <div
              className="mono"
              style={{
                opacity: 0.5,
                fontSize: '11px',
                textTransform:
                  'uppercase',
                letterSpacing:
                  '0.1em',
              }}
            >
              {result.category ||
                'Beauty product'}
            </div>

            <h2
              style={{
                margin:
                  '11px 0 4px',
                fontSize: '26px',
                lineHeight: 1.08,
              }}
            >
              {result.brand ||
                'Бренд не определён'}
            </h2>

            <div
              style={{
                fontSize: '17px',
                lineHeight: 1.45,
              }}
            >
              {result.product_name ||
                'Название не определено'}
            </div>

            {(result.variant ||
              result.size) && (
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '8px',
                  marginTop: '17px',
                }}
              >
                {result.variant && (
                  <span
                    className="mono"
                    style={{
                      background:
                        '#eff3f6',
                      padding:
                        '8px 11px',
                      borderRadius:
                        '100px',
                      fontSize:
                        '12px',
                    }}
                  >
                    {result.variant}
                  </span>
                )}

                {result.size && (
                  <span
                    className="mono"
                    style={{
                      background:
                        '#eff3f6',
                      padding:
                        '8px 11px',
                      borderRadius:
                        '100px',
                      fontSize:
                        '12px',
                    }}
                  >
                    {result.size}
                  </span>
                )}
              </div>
            )}

            <div
              style={{
                marginTop: '22px',
                paddingTop: '18px',
                borderTop:
                  '1px solid rgba(20,30,35,0.07)',
                display: 'flex',
                justifyContent:
                  'space-between',
                alignItems: 'center',
              }}
            >
              <div
                className="mono"
                style={{
                  fontSize: '11px',
                  opacity: 0.5,
                  letterSpacing:
                    '0.07em',
                }}
              >
                AI MATCH
              </div>

              <strong>
                {Math.round(
                  (result.confidence ||
                    0) * 100
                )}
                %
              </strong>
            </div>

            <button
              className="add-button"
              onClick={saveToWishlist}
              disabled={
                saving ||
                !result.product_name
              }
              style={{
                marginTop: '22px',
                width: '100%',
              }}
            >
              {saving
                ? 'Сохраняю...'
                : '♡ Добавить в Wishlist'}
            </button>
          </div>
        </div>
      )}

      {loadingItems && (
        <div
          className="mono"
          style={{
            padding: '30px 10px',
            textAlign: 'center',
            opacity: 0.5,
          }}
        >
          Загружаю твой Wishlist…
        </div>
      )}

      {!loadingItems &&
        items.length > 0 && (
          <div
            className="product-list"
            style={{
              marginTop: '24px',
            }}
          >
            {items.map(item => (
              <article
                key={item.id}
                style={{
                  padding:
                    '20px 22px',
                  marginBottom: '12px',
                  borderRadius:
                    '24px',
                  background:
                    '#ffffff',
                  boxShadow:
                    '0 12px 36px rgba(31,43,50,0.06)',
                }}
              >
                <div
                  className="mono"
                  style={{
                    opacity: 0.5,
                    fontSize: '11px',
                    textTransform:
                      'uppercase',
                  }}
                >
                  {item.product
                    .category ||
                    'Beauty product'}
                </div>

                <h3
                  style={{
                    margin:
                      '8px 0 4px',
                  }}
                >
                  {item.product.brand
                    ?.name ||
                    'Бренд не указан'}
                </h3>

                <div>
                  {item.product.name}
                </div>

                {(item.product
                  .variant ||
                  item.product
                    .size) && (
                  <div
                    className="mono"
                    style={{
                      marginTop:
                        '9px',
                      opacity: 0.55,
                      fontSize:
                        '12px',
                    }}
                  >
                    {[
                      item.product
                        .variant,
                      item.product
                        .size,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                )}

                <PriceBlock
                  offer={item.offer}
                />

                {item.offer &&
                  (item.offer.affiliate_url ||
                    item.offer.product_url) && (
                    <a
                      href={`${API_BASE}/out/${item.offer.id}?source=wishlist`}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent:
                          'space-between',
                        width: '100%',
                        boxSizing:
                          'border-box',
                        marginTop: '14px',
                        padding:
                          '14px 16px',
                        borderRadius:
                          '16px',
                        background:
                          '#f1f5f6',
                        color: '#1f2b30',
                        textDecoration:
                          'none',
                        fontSize: '13px',
                        fontWeight: 600,
                      }}
                    >
                      <span>
                        Открыть в Золотом Яблоке
                      </span>

                      <span>
                        →
                      </span>
                    </a>
                  )}

                <button
                  type="button"
                  onClick={() =>
                    deleteWishlistItem(
                      item.id
                    )
                  }
                  disabled={
                    deletingItemId ===
                    item.id
                  }
                  style={{
                    width: '100%',
                    marginTop: '10px',
                    padding:
                      '12px 16px',
                    borderRadius:
                      '16px',
                    border:
                      '1px solid rgba(155,76,86,0.14)',
                    background:
                      '#fffafa',
                    color:
                      '#9b4c56',
                    fontSize:
                      '12px',
                    fontWeight: 600,
                    cursor:
                      deletingItemId ===
                      item.id
                        ? 'default'
                        : 'pointer',
                    opacity:
                      deletingItemId ===
                      item.id
                        ? 0.55
                        : 1,
                  }}
                >
                  {deletingItemId ===
                  item.id
                    ? 'Удаляю…'
                    : 'Удалить из Wishlist'}
                </button>
              </article>
            ))}
          </div>
        )}

      {!result &&
        !loading &&
        !loadingItems &&
        items.length === 0 &&
        !accountError && (
          <div
            style={{
              marginTop: '28px',
              padding:
                '52px 25px',
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
                display: 'grid',
                placeItems: 'center',
                margin:
                  '0 auto 18px',
                borderRadius:
                  '22px',
                background:
                  '#ffffff',
                fontSize: '27px',
              }}
            >
              ♡
            </div>

            <h3
              style={{
                margin: 0,
                fontSize: '20px',
              }}
            >
              Твой Wishlist пока пуст
            </h3>

            <div
              className="mono"
              style={{
                marginTop: '10px',
                opacity: 0.52,
                fontSize: '12px',
                lineHeight: 1.65,
              }}
            >
              Добавляй средства,
              которые хочешь попробовать.
              <br />
              Теперь они сохраняются
              в твоём Telegram-аккаунте.
            </div>
          </div>
        )}
    </main>
  )
}
