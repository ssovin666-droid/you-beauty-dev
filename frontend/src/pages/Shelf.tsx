import { ProductCard } from '../components/ProductCard'

export function Shelf() {
  return (
    <main className="screen list-screen">
      <header className="list-header"><div><h1>Полка</h1><div className="mono subhead">Твои любимые средства всегда под контролем</div></div><div className="header-actions"><button className="icon-btn">⌕</button><button className="icon-btn">☷</button></div></header>
      <div className="chips"><button className="active">Все 4</button><button>Нужен повтор 2</button><button>Есть скидка 1</button></div>
      <button className="add-button">＋ Добавить товар</button>
      <div className="product-list">
        <ProductCard brand="Medicube" name="Zero Pore Serum 2.0" meta="Нужен повтор · 30 мл" price="2 290 ₽" oldPrice="3 490 ₽" discount="−34%" store="Золотое Яблоко" accent="blue"/>
        <ProductCard brand="COSRX" name="Advanced Snail 92 All in One Cream" meta="Заканчивается скоро · 100 мл" price="1 890 ₽" oldPrice="2 690 ₽" discount="−30%" store="Лэтуаль" accent="rose"/>
      </div>
    </main>
  )
}
