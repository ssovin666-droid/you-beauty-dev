const API_BASE =
  import.meta.env.VITE_API_BASE ??
  'http://localhost:8000/api'

export async function apiGet<T>(
  path: string
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)

  if (!res.ok) {
    throw new Error(`API ${res.status}`)
  }

  return res.json()
}

export async function recognizeProduct(
  file: File
) {
  const formData = new FormData()

  formData.append('file', file)

  const res = await fetch(
    `${API_BASE}/recognize`,
    {
      method: 'POST',
      body: formData,
    }
  )

  const data = await res.json()

  if (!res.ok) {
    throw new Error(
      data?.detail ||
      `Recognition failed: ${res.status}`
    )
  }

  return data
}
