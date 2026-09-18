type Props = {
  brand: string
  name: string
  meta: string
  price: string
  oldPrice?: string
  discount?: string
  store: string
  accent?: 'blue' | 'rose' | 'green'
}

export function ProductCard({ brand, name, meta, price, oldPrice, discount, store, accent = 'blue' }: Props) {
  return (
    <article className={`product-card accent-${accent}`}>
      <div className="product-photo placeholder-product" aria-hidden="true">
        <div className="bottle-shape" />
      </div>
      <div className="product-copy">
        <div className="mono brand-label">{brand}</div>
        <h3>{name}</h3>
        <div className="mono muted">{meta}</div>
        <div className="price-row">
          <strong>{price}</strong>
          {oldPrice && <span className="old-price">{oldPrice}</span>}
          {discount && <span className="discount">{discount}</span>}
        </div>
        <div className="store-row mono">{store}</div>
      </div>
      <button className="ghost-cta">Смотреть цены →</button>
    </article>
  )
}
