import { ProductCard } from '../components/ProductCard'

export function Wishlist() {
  return (
    <main className="screen list-screen">
      <header className="list-header">
        <div><h1>Wishlist</h1><div className="mono subhead">14 товаров · 5 скидок сегодня</div></div>
        <div className="header-actions"><button className="icon-btn">⌕</button><button className="icon-btn">☷</button></div>
      </header>
      <div className="segments"><button>Все</button><button className="active">Со скидкой</button><button>Бренды</button></div>
      <button className="add-button">＋ Добавить товар</button>
      <div className="product-list">
        <ProductCard brand="Medicube" name="Zero Pore Serum 2.0" meta="30 мл · сыворотка · сужение пор" price="2 290 ₽" oldPrice="3 490 ₽" discount="−34%" store="Золотое Яблоко" accent="blue"/>
        <ProductCard brand="COSRX" name="Advanced Snail 92 All in One Cream" meta="100 мл · крем · восстановление" price="1 890 ₽" oldPrice="2 690 ₽" discount="−30%" store="Лэтуаль" accent="rose"/>
        <ProductCard brand="Anua" name="Heartleaf 77% Soothing Toner" meta="250 мл · тонер · успокоение" price="1 290 ₽" oldPrice="1 990 ₽" discount="−35%" store="Магнит Косметик" accent="green"/>
      </div>
    </main>
  )
}
