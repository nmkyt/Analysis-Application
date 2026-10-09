-- Таблицы учётной системы сети металлобаз.
-- Скрипт пересоздаёт все объекты, существующие данные удаляются.

\set ON_ERROR_STOP on

DROP MATERIALIZED VIEW IF EXISTS mv_daily_sales;
DROP VIEW IF EXISTS v_sales, v_stock_on_hand;
DROP TABLE IF EXISTS
    stock_movements, stock_transfer_lines, stock_transfers,
    purchase_receipt_lines, purchase_receipts,
    order_services, sales_order_lines, sales_orders,
    price_history, metal_price_index, calendar,
    customers, services, products, suppliers, categories, branches
    CASCADE;


-- ===== Справочники =====

-- Металлобазы и пункты выдачи
CREATE TABLE branches (
    id          smallint PRIMARY KEY,
    code        text NOT NULL UNIQUE,
    name        text NOT NULL,
    city        text NOT NULL,
    format      text NOT NULL CHECK (format IN ('hypermarket', 'supermarket', 'minimarket', 'pickup_point')),
    address     text NOT NULL,
    hub_id      smallint REFERENCES branches (id),  -- база, с которой пополняется; NULL - закупает у поставщиков
    is_seasonal boolean NOT NULL DEFAULT false,      -- работает только в дачный сезон
    opened_on   date NOT NULL
);

-- Дерево категорий каталога
CREATE TABLE categories (
    id        integer PRIMARY KEY,
    parent_id integer REFERENCES categories (id),
    slug      text NOT NULL UNIQUE,
    name      text NOT NULL
);

CREATE TABLE suppliers (
    id             integer PRIMARY KEY,
    name           text NOT NULL,
    specialization text NOT NULL,
    city           text NOT NULL,
    lead_time_days smallint NOT NULL CHECK (lead_time_days > 0)  -- типичный срок поставки
);

-- Номенклатура. Количество во всех документах указывается в единицах unit,
-- kg_per_unit позволяет пересчитать его в тонны
CREATE TABLE products (
    id              integer PRIMARY KEY,
    sku             text NOT NULL UNIQUE,
    name            text NOT NULL,
    category_id     integer NOT NULL REFERENCES categories (id),
    supplier_id     integer NOT NULL REFERENCES suppliers (id),
    unit            text NOT NULL CHECK (unit IN ('m', 'pcs', 'sheet', 'roll', 'pack', 'kg')),
    kg_per_unit     numeric(12, 4) NOT NULL CHECK (kg_per_unit > 0),
    stick_length_m  numeric(5, 2),  -- длина хлыста для длинномерного проката
    steel_grade     text,
    standard        text,           -- ГОСТ / ТУ
    quality         text NOT NULL DEFAULT 'standard'
                    CHECK (quality IN ('standard', 'substandard')),
    attributes      jsonb NOT NULL DEFAULT '{}',  -- размеры, покрытие, цвет и т. п.
    introduced_on   date NOT NULL,
    discontinued_on date
);

-- Дополнительные услуги: металлообработка, доставка
CREATE TABLE services (
    id    smallint PRIMARY KEY,
    code  text NOT NULL UNIQUE,
    name  text NOT NULL,
    unit  text NOT NULL
);

CREATE TABLE customers (
    id             integer PRIMARY KEY,
    kind           text NOT NULL CHECK (kind IN ('individual', 'sole_trader', 'company')),
    segment        text NOT NULL
                   CHECK (segment IN ('private', 'small_builder', 'construction', 'manufacturing', 'reseller')),
    name           text,  -- у физических лиц не хранится
    city           text NOT NULL,
    home_branch_id smallint NOT NULL REFERENCES branches (id),
    registered_on  date NOT NULL
);


-- ===== Внешние данные =====

-- Производственный календарь
CREATE TABLE calendar (
    date           date PRIMARY KEY,
    is_working_day boolean NOT NULL,
    holiday_name   text
);

-- Индекс цен на металлопрокат (100 = начало периода)
CREATE TABLE metal_price_index (
    date  date PRIMARY KEY,
    value numeric(8, 2) NOT NULL
);


-- ===== Цены =====

-- Розничная и оптовая цена за единицу товара, действует с valid_from до следующей записи
CREATE TABLE price_history (
    product_id      integer NOT NULL REFERENCES products (id),
    valid_from      date NOT NULL,
    retail_price    numeric(12, 2) NOT NULL CHECK (retail_price > 0),
    wholesale_price numeric(12, 2) NOT NULL CHECK (wholesale_price > 0),
    PRIMARY KEY (product_id, valid_from)
);


-- ===== Продажи =====

CREATE TABLE sales_orders (
    id             bigint PRIMARY KEY,
    number         text NOT NULL UNIQUE,
    branch_id      smallint NOT NULL REFERENCES branches (id),
    customer_id    integer REFERENCES customers (id),  -- NULL - анонимная розничная покупка
    created_at     timestamp NOT NULL,
    channel        text NOT NULL CHECK (channel IN ('walk_in', 'phone', 'website')),
    price_type     text NOT NULL CHECK (price_type IN ('retail', 'wholesale')),
    payment_method text NOT NULL CHECK (payment_method IN ('cash', 'card', 'bank_transfer', 'cash_on_delivery')),
    with_delivery  boolean NOT NULL,
    status         text NOT NULL CHECK (status IN ('completed', 'cancelled'))
);

CREATE TABLE sales_order_lines (
    order_id     bigint NOT NULL REFERENCES sales_orders (id) ON DELETE CASCADE,
    line_no      smallint NOT NULL,
    product_id   integer NOT NULL REFERENCES products (id),
    quantity     numeric(12, 3) NOT NULL CHECK (quantity > 0),
    unit_price   numeric(12, 2) NOT NULL,
    discount_pct numeric(4, 2) NOT NULL DEFAULT 0,
    amount       numeric(14, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE order_services (
    order_id   bigint NOT NULL REFERENCES sales_orders (id) ON DELETE CASCADE,
    service_id smallint NOT NULL REFERENCES services (id),
    quantity   numeric(10, 2) NOT NULL CHECK (quantity > 0),
    amount     numeric(12, 2) NOT NULL,
    PRIMARY KEY (order_id, service_id)
);


-- ===== Закупки и перемещения =====

CREATE TABLE purchase_receipts (
    id          bigint PRIMARY KEY,
    number      text NOT NULL UNIQUE,
    supplier_id integer NOT NULL REFERENCES suppliers (id),
    branch_id   smallint NOT NULL REFERENCES branches (id),
    ordered_on  date NOT NULL,
    received_on date NOT NULL CHECK (received_on >= ordered_on)
);

CREATE TABLE purchase_receipt_lines (
    receipt_id bigint NOT NULL REFERENCES purchase_receipts (id) ON DELETE CASCADE,
    line_no    smallint NOT NULL,
    product_id integer NOT NULL REFERENCES products (id),
    quantity   numeric(12, 3) NOT NULL CHECK (quantity > 0),
    unit_cost  numeric(12, 2) NOT NULL,
    PRIMARY KEY (receipt_id, line_no)
);

CREATE TABLE stock_transfers (
    id             bigint PRIMARY KEY,
    number         text NOT NULL UNIQUE,
    from_branch_id smallint NOT NULL REFERENCES branches (id),
    to_branch_id   smallint NOT NULL REFERENCES branches (id),
    shipped_on     date NOT NULL,
    received_on    date NOT NULL CHECK (received_on >= shipped_on)
);

CREATE TABLE stock_transfer_lines (
    transfer_id bigint NOT NULL REFERENCES stock_transfers (id) ON DELETE CASCADE,
    line_no     smallint NOT NULL,
    product_id  integer NOT NULL REFERENCES products (id),
    quantity    numeric(12, 3) NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (transfer_id, line_no)
);

-- Регистр движения товаров: остаток = сумма quantity (приход > 0, расход < 0).
-- adjustment - начальные остатки на дату ввода системы
CREATE TABLE stock_movements (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    moved_on      date NOT NULL,
    branch_id     smallint NOT NULL REFERENCES branches (id),
    product_id    integer NOT NULL REFERENCES products (id),
    movement_type text NOT NULL
                  CHECK (movement_type IN ('adjustment', 'receipt', 'sale', 'transfer_in', 'transfer_out', 'write_off')),
    quantity      numeric(12, 3) NOT NULL CHECK (quantity <> 0),
    document_id   bigint  -- заказ, приходная накладная или перемещение, в зависимости от типа
);


-- ===== Индексы =====

CREATE INDEX ON products (category_id);
CREATE INDEX ON customers (segment);
CREATE INDEX ON sales_orders (created_at);
CREATE INDEX ON sales_orders (customer_id);
CREATE INDEX ON sales_orders (branch_id, created_at);
CREATE INDEX ON sales_order_lines (product_id);
CREATE INDEX ON purchase_receipt_lines (product_id);
CREATE INDEX ON stock_movements (branch_id, product_id, moved_on);
CREATE INDEX ON stock_movements (moved_on);


-- ===== Представления для аналитики =====

-- Строки выполненных заказов с датой, клиентом и весом
CREATE VIEW v_sales AS
SELECT o.id                                   AS order_id,
       o.created_at::date                     AS sale_date,
       o.branch_id,
       o.customer_id,
       COALESCE(c.segment, 'private')         AS segment,
       o.channel,
       o.price_type,
       l.product_id,
       p.category_id,
       l.quantity,
       round(l.quantity * p.kg_per_unit / 1000, 4) AS weight_t,
       l.amount
FROM sales_order_lines l
JOIN sales_orders o ON o.id = l.order_id
JOIN products p ON p.id = l.product_id
LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'completed';

-- Текущие остатки
CREATE VIEW v_stock_on_hand AS
SELECT branch_id, product_id, sum(quantity) AS quantity
FROM stock_movements
GROUP BY branch_id, product_id
HAVING sum(quantity) <> 0;

-- Продажи по дням, базам и товарам: основа для прогнозирования спроса
CREATE MATERIALIZED VIEW mv_daily_sales AS
SELECT sale_date,
       branch_id,
       product_id,
       sum(quantity)            AS quantity,
       sum(weight_t)            AS weight_t,
       sum(amount)              AS amount,
       count(DISTINCT order_id) AS orders
FROM v_sales
GROUP BY sale_date, branch_id, product_id
WITH NO DATA;

CREATE UNIQUE INDEX ON mv_daily_sales (sale_date, branch_id, product_id);
CREATE INDEX ON mv_daily_sales (product_id, branch_id, sale_date);
