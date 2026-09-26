declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        ready: () => void
        expand: () => void
        initData: string
        colorScheme?: string
      }
    }
  }
}

export function initTelegram() {
  const webApp = window.Telegram?.WebApp

  if (!webApp) return

  webApp.ready()
  webApp.expand()
}

export function getTelegramInitData() {
  return window.Telegram?.WebApp?.initData ?? ''
}

export function getTelegramAuthHeaders(): Record<string, string> {
  const initData = getTelegramInitData()

  if (!initData) {
    return {}
  }

  return {
    'X-Telegram-Init-Data': initData,
  }
}
