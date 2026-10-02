                  ? 'Сохраняю...'
                  : '＋ Добавить на Полку'}
              </button>
            </div>
          </div>
        </div>
      )}

      {loadingItems && (
        <div
          className="mono"
          style={{
            padding: '30px 10px',
            textAlign: 'center',
            opacity: 0.5,
          }}
        >
          Загружаю твою Полку…
        </div>
      )}

      {!loadingItems &&
        items.length > 0 && (
          <div
            className="product-list"
            style={{
              marginTop: '24px',
            }}
          >
            {items.map(item => (
              <article
                key={item.id}
                style={{
                  padding: '20px 22px',
                  marginBottom: '12px',
                  borderRadius: '24px',
                  background: '#ffffff',
                  boxShadow:
                    '0 12px 36px rgba(31,43,50,0.06)',
                }}
              >
                <div
                  className="mono"
                  style={{
                    opacity: 0.5,
                    fontSize: '11px',
                    textTransform:
                      'uppercase',
                  }}
                >
                  {item.product.category ||
                    'Beauty product'}
                </div>

                <h3
                  style={{
                    margin: '8px 0 4px',
                  }}
                >
                  {item.product.brand
                    ?.name ||
                    'Бренд не указан'}
                </h3>

                <div>
                  {item.product.name}
                </div>

                {(item.product.variant ||
                  item.product.size) && (
                  <div
                    className="mono"
                    style={{
                      marginTop: '9px',
                      opacity: 0.55,
                      fontSize: '12px',
                    }}
                  >
                    {[
                      item.product.variant,
                      item.product.size,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                )}

                <PriceBlock
                  offer={item.offer}
                />
              </article>
            ))}
          </div>
        )}

      {!result &&
        !loading &&
        !loadingItems &&
        items.length === 0 &&
        !accountError && (
          <div
            style={{
              padding: '58px 24px',
              textAlign: 'center',
            }}
          >
            <h3>
              На полке пока ничего нет
            </h3>

            <div
              className="mono"
              style={{
                marginTop: '9px',
                opacity: 0.55,
                lineHeight: 1.6,
                fontSize: '13px',
              }}
            >
              Добавь средство, которым пользуешься.
              <br />
              Теперь оно сохранится
              <br />
              в твоём Telegram-аккаунте.
            </div>
          </div>
        )}
    </main>
