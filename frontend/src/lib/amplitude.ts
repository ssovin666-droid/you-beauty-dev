import * as amplitude from '@amplitude/unified'

let initialized = false
let openedTracked = false

const API_KEY =
  import.meta.env.VITE_AMPLITUDE_API_KEY

export function initAmplitude(
  telegramUserId: number | string
) {
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
