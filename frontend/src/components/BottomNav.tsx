export type Tab = 'home' | 'wishlist' | 'shelf' | 'brands'

export function BottomNav({ active, onChange }: { active: Tab; onChange: (tab: Tab) => void }) {
  const items: Array<[Tab, string, string]> = [
    ['home', '⌂', 'Главная'],
    ['wishlist', '♡', 'Wishlist'],
    ['shelf', '▣', 'Полка'],
    ['brands', '◇', 'Бренды'],
  ]

  return (
    <nav className="bottom-nav">
      {items.map(([tab, icon, label]) => (
        <button key={tab} className={active === tab ? 'nav-item active' : 'nav-item'} onClick={() => onChange(tab)}>
          <span className="nav-icon">{icon}</span>
          <span>{label}</span>
        </button>
      ))}
    </nav>
  )
}
