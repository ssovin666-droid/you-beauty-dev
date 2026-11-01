import { getTelegramAuthHeaders } from '../telegram'
import type { ArchetypeKey, Rarity, ShadeKey, Slot } from './config'

const API_BASE =
  import.meta.env.VITE_API_BASE ||
  'https://you-beauty-dev-production.up.railway.app/api'

export type CharacterItem = {
  code: string
  name: string
  slot: Slot
  rarity: Rarity
  asset_key: string
}

export type InventoryItem = CharacterItem & {
  owned: boolean
  equipped: boolean
  obtained_at: string | null
}

export type Quest = {
  code: 'unlock' | 'first_item' | 'purchase'
  progress: number
  target: number
  completed: boolean
  reward: string
}

export type PendingReward = {
  id: number
  kind: 'item' | 'evolution'
  source: string | null
  item: CharacterItem | null
  rolled_rarity: Rarity | null
  created_at: string | null
}

export type CharacterState = {
  status: 'locked' | 'ready_to_unbox' | 'active'
  archetype: ArchetypeKey
  accent: ArchetypeKey | null
  evolution: number
  // Уникальная форма звезды; null, пока персонаж закрыт.
  shape_seed: number | null
  progress: {
    shelf_count: number
    shelf_target: number
    classified_count: number
  }
  distribution: Record<ShadeKey, number>
  unlocked_at: string | null
  unboxed_at: string | null
  shared_at: string | null
  quest: Quest
  inventory: InventoryItem[]
  equipped: Record<Slot, string | null>
  pending_rewards: PendingReward[]
  rarity_odds: Record<Rarity, number>
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const auth = getTelegramAuthHeaders()
  if (!auth['X-Telegram-Init-Data']) {
    throw new Error('Открой cosmi через Telegram')
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init.body && !(init.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...auth,
      ...(init.headers ?? {}),
    },
  })

  const data = await response.json().catch(() => null)

  if (!response.ok) {
    throw new Error(data?.detail || `API ${response.status}`)
  }

  return data as T
}

export const characterApi = {
  get: () => request<CharacterState>('/character'),

  unbox: () => request<CharacterState>('/character/unbox', { method: 'POST' }),

  equip: (itemCode: string, equip: boolean) =>
    request<CharacterState>('/character/equip', {
      method: 'POST',
      body: JSON.stringify({ item_code: itemCode, equip }),
    }),

  ackRewards: (ids: number[]) =>
    request<{ ok: boolean }>('/character/rewards/ack', {
      method: 'POST',
      body: JSON.stringify({ reward_ids: ids }),
    }),

  markShared: () => request<{ ok: boolean }>('/character/shared', { method: 'POST' }),

  uploadShareCard: (png: Blob) => {
    const form = new FormData()
    form.append('file', png, 'cosmi-story.png')
    return request<{ ok: boolean; url: string }>('/character/share-card', {
      method: 'POST',
      body: form,
    })
  },
}
