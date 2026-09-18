export function Home({ go }: { go: (tab: 'wishlist' | 'shelf' | 'brands') => void }) {
  return (
    <main className="screen home-screen">
      <header className="topbar">
        <div>
          <div className="eyebrow mono">BEAUTY PRICE TRACKING</div>
          <h1>You Beauty</h1>
        </div>
        <button className="icon-btn">◎</button>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <h2>Твоя косметика<br/>под контролем</h2>
          <p className="mono">Добавляй любимые средства и узнавай о скидках первой.</p>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orb orb-a"/><div className="orb orb-b"/><div className="hero-bottle"/>
        </div>
      </section>

      <section className="dashboard-cards">
        <button className="dashboard-card blue" onClick={() => go('wishlist')}>
          <div>
            <span className="big-icon">♡</span>
            <h3>Wishlist</h3>
            <p className="mono">То, что хочется купить</p>
            <div className="mono stats">12 товаров · <em>3 со скидкой</em></div>
          </div>
          <span className="arrow">›</span>
        </button>

        <button className="dashboard-card rose" onClick={() => go('shelf')}>
          <div>
            <span className="big-icon">▣</span>
            <h3>Полка</h3>
            <p className="mono">То, что хочется покупать снова</p>
            <div className="mono stats">8 товаров · <em>2 со скидкой</em></div>
          </div>
          <span className="arrow">›</span>
        </button>
      </section>

      <section className="brand-strip">
        <div className="section-heading"><h3>Бренды</h3><button onClick={() => go('brands')}>Все бренды →</button></div>
        <div className="brand-pills"><span>Medicube</span><span>COSRX</span><button onClick={() => go('brands')}>＋ Добавить</button></div>
      </section>
    </main>
  )
}
