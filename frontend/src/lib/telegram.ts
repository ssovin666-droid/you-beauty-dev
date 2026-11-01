type SafeAreaInset = {
  top: number
  bottom: number
  left: number
  right: number
}

type TelegramEvent =
  | 'themeChanged'
  | 'activated'
  | 'deactivated'
  | 'safeAreaChanged'
  | 'contentSafeAreaChanged'

export type TelegramWebApp = {
  ready: () => void
  expand: () => void
  initData: string
  colorScheme?: 'light' | 'dark' | string
  version?: string
  themeParams?: Record<string, string | undefined>
  safeAreaInset?: SafeAreaInset
  contentSafeAreaInset?: SafeAreaInset
  isVersionAtLeast?: (version: string) => boolean
  onEvent?: (event: TelegramEvent, handler: () => void) => void
  offEvent?: (event: TelegramEvent, handler: () => void) => void
  openTelegramLink?: (url: string) => void
  shareToStory?: (
    mediaUrl: string,
    params?: {
      text?: string
      widget_link?: { url: string; name?: string }
    }
  ) => void
  HapticFeedback?: {
    impactOccurred: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void
    notificationOccurred: (type: 'error' | 'success' | 'warning') => void
    selectionChanged: () => void
  }
}

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp
    }
  }
}

export function getWebApp(): TelegramWebApp | undefined {
  return window.Telegram?.WebApp
}

export function initTelegram() {
  const webApp = window.Telegram?.WebApp

  if (!webApp) return

  webApp.ready()
  webApp.expand()

  applySafeArea()
  webApp.onEvent?.('safeAreaChanged', applySafeArea)
  webApp.onEvent?.('contentSafeAreaChanged', applySafeArea)
}

// Telegram (Bot API 8.0+) отдаёт safe area отдельно от env(safe-area-inset-*).
// Пробрасываем в CSS-переменные, CSS берёт максимум из обоих источников.
function applySafeArea() {
  const webApp = getWebApp()
  const root = document.documentElement
  const safe = webApp?.safeAreaInset
  const content = webApp?.contentSafeAreaInset

  root.style.setProperty('--tg-safe-top', `${(safe?.top ?? 0) + (content?.top ?? 0)}px`)
  root.style.setProperty('--tg-safe-bottom', `${(safe?.bottom ?? 0) + (content?.bottom ?? 0)}px`)
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

export function isVersionAtLeast(version: string) {
  const webApp = getWebApp()
  try {
    return Boolean(webApp?.isVersionAtLeast?.(version))
  } catch {
    return false
  }
}

export function haptic(
  kind: 'light' | 'medium' | 'heavy' | 'success' | 'selection'
) {
  const feedback = getWebApp()?.HapticFeedback
  if (!feedback || !isVersionAtLeast('6.1')) return
  try {
    if (kind === 'success') feedback.notificationOccurred('success')
    else if (kind === 'selection') feedback.selectionChanged()
    else feedback.impactOccurred(kind)
  } catch {
    // старые клиенты
  }
}
