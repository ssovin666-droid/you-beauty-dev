import { useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'

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

export function Wishlist() {
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [loading, setLoading] = useState(false)
  const [result, setResult] =
    useState<RecognitionResult | null>(null)
  const [error, setError] =
    useState<string | null>(null)

  const [imagePreview, setImagePreview] =
    useState<string | null>(null)

  useEffect(() => {
    return () => {
      if (imagePreview) {
        URL.revokeObjectURL(imagePreview)
      }
    }
  }, [imagePreview])

  function openFilePicker() {
    fileInputRef.current?.click()
  }

  async function handleFileChange(
    event: ChangeEvent<HTMLInputElement>
  ) {
    const file = event.target.files?.[0]

    if (!file) return

    if (imagePreview) {
      URL.revokeObjectURL(imagePreview)
    }

    const preview = URL.createObjectURL(file)

    setImagePreview(preview)
    setLoading(true)
    setResult(null)
    setError(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch(
        `${API_BASE}/recognize`,
        {
          method: 'POST',
          body: formData,
        }
      )

      const data = await response.json()

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

  return (
    <main className="screen list-screen">
      <header className="list-header">
        <div>
          <h1>Wishlist</h1>

          <div className="mono subhead">
            0 товаров
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

      <div className="segments">
        <button className="active">
          Все
        </button>

        <button>
          Со скидкой
        </button>

        <button>
          Бренды
        </button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        onChange={handleFileChange}
        style={{ display: 'none' }}
      />

      <button
        className="add-button"
        onClick={openFilePicker}
        disabled={loading}
      >
        {loading
          ? 'Распознаю товар...'
          : '＋ Добавить товар'}
      </button>

      {loading && imagePreview && (
        <div
          style={{
            marginTop: '20px',
            borderRadius: '28px',
            overflow: 'hidden',
            background: '#fff',
          }}
        >
          <img
            src={imagePreview}
            alt="Загруженный товар"
            style={{
              display: 'block',
              width: '100%',
              height: '310px',
              objectFit: 'cover',
              opacity: 0.8,
            }}
          />

          <div
            style={{
              padding: '18px 20px 22px',
            }}
          >
            <div
              className="mono"
              style={{
                fontSize: '12px',
                opacity: 0.6,
              }}
            >
              AI ANALYSIS
            </div>

            <div
              style={{
                marginTop: '8px',
                fontSize: '18px',
                fontWeight: 600,
              }}
            >
              Определяю продукт…
            </div>
          </div>
        </div>
      )}

      {error && (
        <div
          style={{
            padding: '18px',
            marginTop: '20px',
            borderRadius: '22px',
            background: '#f6e9e9',
          }}
        >
          <strong>
            Не получилось распознать товар
          </strong>

          <div
            className="mono"
            style={{
              marginTop: '8px',
              opacity: 0.7,
            }}
          >
            {error}
          </div>
        </div>
      )}

      {result && (
        <div
          style={{
            marginTop: '20px',
            borderRadius: '28px',
            overflow: 'hidden',
            background: '#ffffff',
            boxShadow:
              '0 18px 50px rgba(30, 45, 55, 0.08)',
          }}
        >
          {imagePreview && (
            <div
              style={{
                position: 'relative',
                background: '#f2f5f7',
              }}
            >
              <img
                src={imagePreview}
                alt={
                  result.product_name ||
                  'Распознанный продукт'
                }
                style={{
                  display: 'block',
                  width: '100%',
                  height: '330px',
                  objectFit: 'cover',
                }}
              />

              <div
                style={{
                  position: 'absolute',
                  left: '16px',
                  top: '16px',
                  padding: '8px 12px',
                  borderRadius: '999px',
                  background:
                    'rgba(255,255,255,0.9)',
                  backdropFilter: 'blur(10px)',
                  fontSize: '11px',
                  fontWeight: 600,
                  letterSpacing: '0.08em',
                }}
                className="mono"
              >
                НАЙДЕНО AI
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
                fontSize: '12px',
                letterSpacing: '0.09em',
                opacity: 0.55,
                textTransform: 'uppercase',
              }}
            >
              {result.category ||
                'Beauty product'}
            </div>

            <h2
              style={{
                margin:
                  '10px 0 6px 0',
                fontSize: '25px',
                lineHeight: 1.1,
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
                  marginTop: '18px',
                }}
              >
                {result.variant && (
                  <span
                    className="mono"
                    style={{
                      padding: '8px 11px',
                      borderRadius: '999px',
                      background: '#eff3f6',
                      fontSize: '12px',
                    }}
                  >
                    {result.variant}
                  </span>
                )}

                {result.size && (
                  <span
                    className="mono"
                    style={{
                      padding: '8px 11px',
                      borderRadius: '999px',
                      background: '#eff3f6',
                      fontSize: '12px',
                    }}
                  >
                    {result.size}
                  </span>
                )}
              </div>
            )}

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent:
                  'space-between',
                marginTop: '22px',
                paddingTop: '18px',
                borderTop:
                  '1px solid rgba(0,0,0,0.06)',
              }}
            >
              <span
                className="mono"
                style={{
                  fontSize: '12px',
                  opacity: 0.55,
                }}
              >
                УВЕРЕННОСТЬ AI
              </span>

              <strong
                style={{
                  fontSize: '16px',
                }}
              >
                {Math.round(
                  (result.confidence || 0) *
                    100
                )}
                %
              </strong>
            </div>
          </div>
        </div>
      )}

      {!result &&
        !loading &&
        !error && (
          <div
            style={{
              padding: '60px 24px',
              textAlign: 'center',
            }}
          >
            <div
              style={{
                width: '72px',
                height: '72px',
                margin: '0 auto 20px',
                borderRadius: '24px',
                display: 'grid',
                placeItems: 'center',
                background: '#edf3f6',
                fontSize: '30px',
              }}
            >
              ♡
            </div>

            <h3
              style={{
                marginBottom: '8px',
              }}
            >
              Wishlist пока пуст
            </h3>

            <div
              className="mono"
              style={{
                opacity: 0.55,
                lineHeight: 1.6,
                fontSize: '13px',
              }}
            >
              Добавь косметику по фотографии.
              <br />
              You Beauty распознает товар
              <br />
              и начнёт следить за ценой.
            </div>
          </div>
        )}
    </main>
  )
}
