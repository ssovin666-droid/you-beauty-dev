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

    const preview =
      URL.createObjectURL(file)

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
            0 товаров · 0 скидок сегодня
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
                backdropFilter: 'blur(10px)',
                fontSize: '11px',
                letterSpacing: '0.08em',
              }}
            >
              AI SEARCH
            </div>
          </div>

          <div
            style={{
              padding: '20px 22px 24px',
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
            Не получилось определить товар
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
                  position: 'absolute',
                  top: '16px',
                  left: '16px',
                  padding: '8px 12px',
                  borderRadius: '100px',
                  background:
                    'rgba(255,255,255,0.92)',
                  backdropFilter: 'blur(12px)',
                  fontSize: '11px',
                  letterSpacing: '0.08em',
                }}
              >
                FOUND
              </div>

              <div
                style={{
                  position: 'absolute',
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
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
              }}
            >
              {result.category ||
                'Beauty product'}
            </div>

            <h2
              style={{
                margin: '11px 0 4px',
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
                      background: '#eff3f6',
                      padding: '8px 11px',
                      borderRadius: '100px',
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
                      background: '#eff3f6',
                      padding: '8px 11px',
                      borderRadius: '100px',
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
                  letterSpacing: '0.07em',
                }}
              >
                AI MATCH
              </div>

              <strong>
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
              marginTop: '28px',
              padding: '52px 25px',
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
                margin: '0 auto 18px',
                borderRadius: '22px',
                background: '#ffffff',
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
              Добавляй средства, которые хочешь попробовать.
              <br />
              Мы будем следить за ценами
              <br />
              и сообщим о скидках.
            </div>
          </div>
        )}
    </main>
  )
}
