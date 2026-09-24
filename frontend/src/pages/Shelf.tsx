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

export function Shelf() {
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
          Все 0
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
            Не получилось распознать товар
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
                  (result.confidence || 0) * 100
                )}
                %
              </div>
            </div>
          </div>
        </div>
      )}

      {!result &&
        !loading &&
        !error && (
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
              Мы сообщим, когда его будет
              <br />
              выгодно купить снова.
            </div>
          </div>
        )}
    </main>
  )
}
