import { useRef, useState } from 'react'
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

  function openFilePicker() {
    fileInputRef.current?.click()
  }

  async function handleFileChange(
    event: ChangeEvent<HTMLInputElement>
  ) {
    const file = event.target.files?.[0]

    if (!file) return

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

      {error && (
        <div
          style={{
            padding: '16px',
            marginTop: '18px',
            borderRadius: '20px',
            background: '#f6e9e9',
          }}
        >
          <strong>
            Не получилось распознать товар
          </strong>

          <div
            className="mono"
            style={{ marginTop: '8px' }}
          >
            {error}
          </div>
        </div>
      )}

      {result && (
        <div
          style={{
            padding: '20px',
            marginTop: '18px',
            borderRadius: '24px',
            background: '#ffffff',
          }}
        >
          <div className="mono subhead">
            ТОВАР РАСПОЗНАН
          </div>

          <h2
            style={{
              marginTop: '12px',
              marginBottom: '6px',
            }}
          >
            {result.brand ||
              'Бренд не определён'}
          </h2>

          <div
            style={{
              fontSize: '17px',
              marginBottom: '12px',
            }}
          >
            {result.product_name ||
              'Название не определено'}
          </div>

          {result.variant && (
            <div className="mono">
              Вариант: {result.variant}
            </div>
          )}

          {result.size && (
            <div className="mono">
              Размер: {result.size}
            </div>
          )}

          {result.category && (
            <div className="mono">
              Категория: {result.category}
            </div>
          )}

          <div
            className="mono"
            style={{ marginTop: '12px' }}
          >
            Уверенность:{' '}
            {Math.round(
              (result.confidence || 0) * 100
            )}
            %
          </div>
        </div>
      )}

      {!result && !loading && !error && (
        <div
          style={{
            padding: '48px 24px',
            textAlign: 'center',
          }}
        >
          <h3>Wishlist пока пуст</h3>

          <div
            className="mono"
            style={{
              marginTop: '8px',
              opacity: 0.6,
              lineHeight: 1.6,
            }}
          >
            Добавь косметику по фотографии,
            чтобы следить за ценой и скидками.
          </div>
        </div>
      )}
    </main>
  )
}
