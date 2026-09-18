const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api'

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}
