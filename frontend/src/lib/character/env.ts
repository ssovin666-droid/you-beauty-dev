import { useEffect, useState } from 'react'

import { getWebApp } from '../telegram'

export type ThemeMode = 'light' | 'dark'

// Цвет «сцены» за персонажем: под него подстраивается фон-шейдер
// и прозрачный материал, поэтому он задаётся явно, а не через CSS.
export const STAGE_COLORS: Record<ThemeMode, string> = {
  light: '#ece8ea',
  dark: '#1a181d',
}

function readTheme(): ThemeMode {
  const scheme = getWebApp()?.colorScheme
  if (scheme === 'dark' || scheme === 'light') return scheme
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function useTelegramTheme(): ThemeMode {
  const [theme, setTheme] = useState<ThemeMode>(readTheme)

  useEffect(() => {
    const webApp = getWebApp()
    const update = () => setTheme(readTheme())
    webApp?.onEvent?.('themeChanged', update)
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    media?.addEventListener?.('change', update)
    return () => {
      webApp?.offEvent?.('themeChanged', update)
      media?.removeEventListener?.('change', update)
    }
  }, [])

  return theme
}

// Вкладка видна и мини-апп не свёрнут.
// Стартуем всегда «активными»: Telegram (особенно iOS) может открыть
// предзагруженный WebView со visibilityState = 'hidden' и не прислать
// visibilitychange — тогда персонаж замирал до перезагрузки.
// Паузу ставим только по явному сигналу, снимаем по любому признаку жизни.
export function useAppActive(): boolean {
  const [active, setActive] = useState(true)

  useEffect(() => {
    const webApp = getWebApp()
    const wake = () => setActive(true)
    const sleep = () => setActive(false)
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') sleep()
      else wake()
    }

    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('focus', wake)
    window.addEventListener('pageshow', wake)
    window.addEventListener('pointerdown', wake, { passive: true })
    window.addEventListener('pagehide', sleep)
    webApp?.onEvent?.('activated', wake)
    webApp?.onEvent?.('deactivated', sleep)

    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('focus', wake)
      window.removeEventListener('pageshow', wake)
      window.removeEventListener('pointerdown', wake)
      window.removeEventListener('pagehide', sleep)
      webApp?.offEvent?.('activated', wake)
      webApp?.offEvent?.('deactivated', sleep)
    }
  }, [])

  return active
}

export function prefersReducedMotion() {
  return Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
}

let webglVerdict: 'ok' | 'weak' | 'none' | null = null

// Можно ли рисовать 3D: WebGL2/1 без «major performance caveat»
// и не совсем слабое железо. Иначе — статичная картинка.
export function webglSupport(): 'ok' | 'weak' | 'none' {
  if (webglVerdict) return webglVerdict

  try {
    const nav = navigator as Navigator & { deviceMemory?: number }
    const lowMemory = typeof nav.deviceMemory === 'number' && nav.deviceMemory <= 2
    const fewCores = typeof nav.hardwareConcurrency === 'number' && nav.hardwareConcurrency <= 2

    const canvas = document.createElement('canvas')
    const attrs: WebGLContextAttributes = { failIfMajorPerformanceCaveat: true }
    const gl =
      (canvas.getContext('webgl2', attrs) as WebGLRenderingContext | null) ||
      (canvas.getContext('webgl', attrs) as WebGLRenderingContext | null)

    if (!gl) {
      webglVerdict = 'none'
    } else {
      webglVerdict = lowMemory || fewCores ? 'weak' : 'ok'
      gl.getExtension('WEBGL_lose_context')?.loseContext()
    }
  } catch {
    webglVerdict = 'none'
  }

  return webglVerdict
}

// Если персонаж на устройстве тормозит, запоминаем и больше не мучаем его 3D.
const SLOW_KEY = 'cosmi_star_slow'

export function markDeviceSlow() {
  try {
    localStorage.setItem(SLOW_KEY, '1')
  } catch {
    // приватный режим
  }
}

export function isDeviceMarkedSlow() {
  try {
    return localStorage.getItem(SLOW_KEY) === '1'
  } catch {
    return false
  }
}
