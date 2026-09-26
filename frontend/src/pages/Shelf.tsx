import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'

import { getTelegramAuthHeaders } from '../lib/telegram'

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

type TrackedItem = {
  id: number
  list_type: string
  notifications_enabled: boolean
  product: SavedProduct
}

export function Shelf() {
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

  useEffect(() => {
    loadShelf()
  }, [])

  useEffect(() => {
    return () => {
      if (imagePreview) {
        URL.revokeObjectURL(imagePreview)
      }
    }
  }, [imagePreview])

  async function loadShelf() {
    setLoadingItems(true)
    setAccountError(null)

    try {
      const headers =
        getTelegramAuthHeaders()

      if (
        !headers['X-Telegram-Init-Data']
      ) {
        setAccountError(
          'Открой You Beauty через Telegram, чтобы загрузить сохранённую Полку.'
        )

        setItems([])
        return
      }

      const response = await fetch(
        `${API_BASE}/tracked?list_type=shelf`,
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
          : 'Не удалось загрузить Полку'
      )
    } finally {
      setLoadingItems(false)
    }
  }

  function openFilePicker() {
    fileInputRef.current?.click()
  }

  async function handleFileChange(
    event: ChangeEvent<HTMLInputElement>
  ) {
    const file =
      event.target.files?.[0]

    if (!file) return

    if (imagePreview) {
      URL.revokeObjectURL(imagePreview)
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

  async function saveToShelf() {
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
            list_type: 'shelf',
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

      await loadShelf()

      setSuccess(
        'Товар сохранён на твою Полку'
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

  return (
    <main className="screen list-screen">
      <header className="list-header">
        <div>
          <h1>Полка</h1>

          <div className="mono subhead">
            Твои любимые средства всегда под контролем
          </div>
        </div>

        <div className="header-actions">
          <button className="icon-btn">
            ⌕
          </button>

          <button className="icon-btn">
            ☷
          </button>
        </div>
      </header>

      <div className="chips">
        <button className="active">
          Все {items.length}
        </button>

        <button>
          Нужен повтор 0
        </button>

        <button>
          Есть скидка 0
        </button>
      </div>

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
            marginTop: '20px',
            borderRadius: '24px',
            overflow: 'hidden',
            background: '#ffffff',
          }}
        >
          <img
            src={imagePreview}
            alt="Добавляемый товар"
            style={{
              display: 'block',
              width: '100%',
              height: '300px',
              objectFit: 'cover',
              opacity: 0.82,
            }}
          />

          <div
            style={{
              padding: '18px 20px 22px',
            }}
          >
            <div className="mono subhead">
              AI распознаёт средство
            </div>
          </div>
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: '20px',
            padding: '18px 20px',
            borderRadius: '24px',
            background: '#f6e9e9',
          }}
        >
          <strong>
            Не получилось
          </strong>

          <div
            className="mono"
            style={{
              marginTop: '8px',
              opacity: 0.65,
            }}
          >
            {error}
          </div>
        </div>
      )}

      {result && (
        <div className="product-list">
          <div
            style={{
              marginTop: '20px',
              borderRadius: '24px',
              overflow: 'hidden',
              background: '#ffffff',
              boxShadow:
                '0 16px 42px rgba(30, 45, 55, 0.07)',
            }}
          >
            {imagePreview && (
              <img
                src={imagePreview}
                alt={
                  result.product_name ||
                  'Распознанный товар'
                }
                style={{
                  display: 'block',
                  width: '100%',
                  height: '300px',
                  objectFit: 'cover',
                }}
              />
            )}

            <div
              style={{
                padding: '22px',
              }}
            >
              <div className="mono subhead">
                {result.category ||
                  'Косметическое средство'}
              </div>

              <h2
                style={{
                  margin: '10px 0 5px',
                }}
              >
                {result.brand ||
                  'Бренд не определён'}
              </h2>

              <div
                style={{
                  fontSize: '16px',
                  lineHeight: 1.45,
                }}
              >
                {result.product_name ||
                  'Название не определено'}
              </div>

              {(result.variant ||
                result.size) && (
                <div
                  className="mono"
                  style={{
                    marginTop: '12px',
                    opacity: 0.65,
                  }}
                >
                  {[
                    result.variant,
                    result.size,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </div>
              )}

              <div
                className="mono"
                style={{
                  marginTop: '18px',
                  fontSize: '12px',
                  opacity: 0.55,
                }}
              >
                AI уверен на{' '}
                {Math.round(
                  (result.confidence || 0) *
                    100
                )}
                %
              </div>

              <button
                className="add-button"
                onClick={saveToShelf}
                disabled={
                  saving ||
                  !result.product_name
                }
                style={{
                  width: '100%',
                  marginTop: '22px',
                }}
              >
                {saving
                  ? 'Сохраняю...'
                  : '＋ Добавить на Полку'}
              </button>
            </div>
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
          Загружаю твою Полку…
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
                  padding: '20px 22px',
                  marginBottom: '12px',
                  borderRadius: '24px',
                  background: '#ffffff',
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
                  {item.product.category ||
                    'Beauty product'}
                </div>

                <h3
                  style={{
                    margin: '8px 0 4px',
                  }}
                >
                  {item.product.brand
                    ?.name ||
                    'Бренд не указан'}
                </h3>

                <div>
                  {item.product.name}
                </div>

                {(item.product.variant ||
                  item.product.size) && (
                  <div
                    className="mono"
                    style={{
                      marginTop: '9px',
                      opacity: 0.55,
                      fontSize: '12px',
                    }}
                  >
                    {[
                      item.product.variant,
                      item.product.size,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                )}
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
              padding: '58px 24px',
              textAlign: 'center',
            }}
          >
            <h3>
              На полке пока ничего нет
            </h3>

            <div
              className="mono"
              style={{
                marginTop: '9px',
                opacity: 0.55,
                lineHeight: 1.6,
                fontSize: '13px',
              }}
            >
              Добавь средство, которым пользуешься.
              <br />
              Теперь оно сохранится
              <br />
              в твоём Telegram-аккаунте.
            </div>
          </div>
        )}
    </main>
  )
}
