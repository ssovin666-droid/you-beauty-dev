// Последнее известное состояние персонажа на этом устройстве.
// Нужно, чтобы при повторном заходе сразу показывать своё существо,
// а не капсулу, пока /character ещё грузится. Данные — только для
// первого кадра: после ответа сервера всё берётся из ответа.

import { getTelegramInitData } from '../telegram'
import type { CharacterState } from './api'

const PREFIX = 'cosmi_character_v1:'

// ID пользователя Telegram из initData (кэш на устройстве — свой у каждого аккаунта).
function userKey(): string | null {
  try {
    const raw = new URLSearchParams(getTelegramInitData()).get('user')
    if (!raw) return null
    const id = (JSON.parse(raw) as { id?: number }).id
    return id ? PREFIX + id : null
  } catch {
    return null
  }
}

export function readCachedCharacter(): CharacterState | null {
  const key = userKey()
  if (!key) return null
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const state = JSON.parse(raw) as CharacterState
    if (!state || !state.status || !state.progress) return null
    return state
  } catch {
    return null
  }
}

export function writeCachedCharacter(state: CharacterState) {
  const key = userKey()
  if (!key) return
  try {
    // Награды не кэшируем: их показ решает только свежий ответ сервера.
    localStorage.setItem(key, JSON.stringify({ ...state, pending_rewards: [] }))
  } catch {
    // приватный режим / переполнено — просто без кэша
  }
}
