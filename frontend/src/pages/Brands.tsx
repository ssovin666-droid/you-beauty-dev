const brands = [
  ['Medicube', '12 товаров со скидкой', 'blue'],
  ['Anua', 'Новые скидки сегодня', 'green'],
  ['Beauty of Joseon', '8 товаров со скидкой', 'rose'],
  ['SK-II', '15 товаров со скидкой', 'rose'],
]

export function Brands() {
  return (
    <main className="screen list-screen">
      <header className="list-header"><div><h1>Бренды</h1><div className="mono subhead">Следи за любимыми брендами и не пропускай скидки</div></div><button className="icon-btn">⌕</button></header>
      <div className="segments"><button className="active">Все</button><button>Отслеживаемые</button><button>На скидке</button></div>
      <div className="brand-list">
        {brands.map(([name, note, tone], index) => (
          <article className={`brand-card ${tone}`} key={name}>
            <div><h3>{name}</h3><div className="mono">{note}</div><button className={index === 0 ? 'follow active' : 'follow'}>{index === 0 ? '✓ Отслеживается' : '＋ Следить'}</button></div>
            <div className="brand-art"><div className="mini-bottle"/></div>
            <span className="arrow">›</span>
          </article>
        ))}
      </div>
    </main>
  )
}
