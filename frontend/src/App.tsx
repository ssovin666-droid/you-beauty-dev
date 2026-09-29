import { useEffect, useState } from 'react'
import { BottomNav, type Tab } from './components/BottomNav'
import { Home } from './pages/Home'
import { Shelf } from './pages/Shelf'
import { Wishlist } from './pages/Wishlist'
import { initTelegram } from './lib/telegram'

export default function App() {
  const [tab, setTab] = useState<Tab>('home')

  useEffect(() => {
    initTelegram()
  }, [])

  return (
    <div className="app-shell">
      {tab === 'home' && <Home go={setTab} />}
      {tab === 'wishlist' && <Wishlist />}
      {tab === 'shelf' && <Shelf />}

      <BottomNav
        active={tab}
        onChange={setTab}
      />
    </div>
  )
}
