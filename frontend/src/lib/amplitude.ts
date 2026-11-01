import * as amplitude from '@amplitude/unified'

const ANALYTICS_ENABLED =
  import.meta.env.VITE_APP_ENV === 'production' &&
  import.meta.env.VITE_ANALYTICS_ENABLED === 'true'

let initialized = false
let openedTracked = false

const pendingCharacterEvents: Array<
  [string, Record<string, string | number | boolean | null> | undefined]
> = []

const API_KEY =
  import.meta.env.VITE_AMPLITUDE_API_KEY

export function initAmplitude(
  telegramUserId: number | string
) {
  if (!ANALYTICS_ENABLED) return
  if (!API_KEY) {
    console.warn(
      'Amplitude API key missing — analytics disabled'
    )
    return
  }

  if (!initialized) {
    amplitude.initAll(
      API_KEY,
      {
        analytics: {
          autocapture: true,
        },
        sessionReplay: {
          sampleRate: 1,
        },
      }
    )

    initialized = true
  }

  amplitude.setUserId(
    String(telegramUserId)
  )

  flushPendingCharacterEvents()
}

export function trackOpenedYouBeauty() {
  if (
    !initialized ||
    openedTracked
  ) {
    return
  }

  amplitude.track(
    'Opened You Beauty',
    {
      prompt_version: 'BA400.4',
    }
  )

  openedTracked = true
}

export function trackStartedAddingProductToWishlist() {
  if (!initialized) {
    return
  }

  amplitude.track(
    'Started Adding Product to Wishlist'
  )
}

export function trackAddedProductToWishlist() {
  if (!initialized) {
    return
  }

  amplitude.track(
    'Added Product to Wishlist'
  )
}

export function trackStartedAddingProductToShelf() {
  if (!initialized) {
    return
  }

  amplitude.track(
    'Started Adding Product to Shelf'
  )
}

export function trackAddedProductToShelf() {
  if (!initialized) {
    return
  }

  amplitude.track(
    'Added Product to Shelf'
  )
}

// -------------------------
// CHARACTER (геймификация)
// -------------------------

export type CharacterEvent =
  | 'character_progress_viewed'
  | 'character_unbox_clicked'
  | 'character_unbox_started'
  | 'character_unbox_failed'
  | 'item_equipped'
  | 'item_unequipped'
  | 'item_equip_failed'
  | 'character_help_opened'
  | 'character_share_opened'
  | 'character_quest_clicked'
  | 'character_shared'
  | 'character_tapped'
  | 'item_received'
  | 'quest_completed'
  | 'inventory_opened'

export function trackCharacterEvent(
  event: CharacterEvent,
  properties?: Record<string, string | number | boolean | null>
) {
  if (!ANALYTICS_ENABLED || !API_KEY) return
  if (!initialized) {
    // Главная грузится раньше, чем /me → initAmplitude.
    // Держим немного событий и отправляем после инициализации.
    if (pendingCharacterEvents.length < 20) {
      pendingCharacterEvents.push([event, properties])
    }
    return
  }

  amplitude.track(event, properties, properties?.reward_id != null
    ? { insert_id: `${event}:${properties.reward_id}` }
    : undefined)
}

function flushPendingCharacterEvents() {
  const queue = pendingCharacterEvents.splice(0)
  queue.forEach(([event, properties]) =>
    amplitude.track(event, properties, properties?.reward_id != null
      ? { insert_id: `${event}:${properties.reward_id}` }
      : undefined)
  )
}
