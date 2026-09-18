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
