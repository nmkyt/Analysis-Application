"""Предобработка данных для прогноза спроса.

build_panel() строит недельную панель «неделя × база × позиция»:
  - ряд существует с момента появления позиции на базе до её вывода из ассортимента;
  - недели без продаж - нули, недели, когда база закрыта, - пропуски;
  - продажи разделены на базовый спрос и спрос юрлиц (крупные строки);
  - недели, в которых позиция заканчивалась на складе, помечены как censored:
    продажи в них - нижняя граница спроса, при обучении они исключаются.

add_features() считает признаки для горизонта прогноза h: всё, что зависит от истории,
берётся по состоянию на неделю origin = week - h, то есть известно на момент прогноза.
"""
import numpy as np
import pandas as pd

from ..storage import connect

# Сегменты юрлиц: их спрос прогнозируется отдельно от базового
B2B_SEGMENTS = ['construction', 'manufacturing', 'reseller']

SERIES_KEY = ['branch_id', 'product_id']
KEY_COLUMNS = ['week', 'origin_week', 'horizon'] + SERIES_KEY
# Целевые переменные: суммарный спрос и его компоненты
TARGET_COLUMNS = ['qty', 'qty_base', 'qty_b2b', 'b2b_orders', 'weight_t']
# Значения целевой недели, которые в момент прогноза неизвестны: только для анализа, не признаки
DIAGNOSTIC_COLUMNS = ['orders', 'customers', 'max_line', 'stockout_days', 'censored']
EXTRA_LAGS = 3                   # лаги h, h+1, ..., h+EXTRA_LAGS
ROLLING_WINDOWS = (4, 8, 13, 26)
WEEKS_PER_YEAR = 52.18
ATTRIBUTE_FEATURES = ['thickness_mm', 'diameter_mm', 'wall_mm', 'width_mm', 'height_mm']

WEEKLY_SALES_SQL = """
SELECT date_trunc('week', o.created_at)::date                                       AS week,
       o.branch_id,
       l.product_id,
       sum(l.quantity)::float8                                                      AS qty,
       coalesce(sum(l.quantity) FILTER (WHERE c.segment = ANY(%(b2b)s)), 0)::float8 AS qty_b2b,
       count(DISTINCT o.id)                                                         AS orders,
       count(DISTINCT o.id) FILTER (WHERE c.segment = ANY(%(b2b)s))                 AS b2b_orders,
       count(DISTINCT o.customer_id)                                                AS customers,
       max(l.quantity)::float8                                                      AS max_line
FROM sales_order_lines l
JOIN sales_orders o ON o.id = l.order_id
LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'completed'
GROUP BY 1, 2, 3
"""

# Ряд - пара база × позиция, по которой было движение товара (то есть позиция в ассортименте базы)
SERIES_SQL = """
SELECT m.branch_id, m.product_id,
       min(m.moved_on)                         AS first_move,
       p.introduced_on, p.discontinued_on,
       p.category_id, c.parent_id              AS parent_category_id,
       p.supplier_id, s.lead_time_days,
       p.unit, p.kg_per_unit::float8           AS kg_per_unit,
       p.stick_length_m::float8                AS stick_length_m,
       p.quality = 'substandard'               AS is_substandard,
       p.attributes,
       b.format                                AS branch_format,
       b.opened_on, b.is_seasonal
FROM stock_movements m
JOIN products p ON p.id = m.product_id
JOIN categories c ON c.id = p.category_id
JOIN suppliers s ON s.id = p.supplier_id
JOIN branches b ON b.id = m.branch_id
GROUP BY m.branch_id, m.product_id, p.id, c.parent_id, s.lead_time_days, b.id
"""

# Дни, когда на конец дня остатка не хватало даже на одну единицу продажи (хлыст, штуку)
STOCKOUT_SQL = """
WITH daily AS (
    SELECT branch_id, product_id, moved_on, sum(quantity) AS delta
    FROM stock_movements
    GROUP BY 1, 2, 3
), balance AS (
    SELECT branch_id, product_id, moved_on,
           sum(delta) OVER w      AS balance,
           lead(moved_on) OVER w  AS next_move
    FROM daily
    WINDOW w AS (PARTITION BY branch_id, product_id ORDER BY moved_on)
)
SELECT date_trunc('week', d.day)::date AS week, b.branch_id, b.product_id, count(*) AS stockout_days
FROM balance b
JOIN products p ON p.id = b.product_id
JOIN branches br ON br.id = b.branch_id
CROSS JOIN LATERAL generate_series(b.moved_on, coalesce(b.next_move - 1, %(end)s::date), interval '1 day') AS d(day)
WHERE b.balance < CASE WHEN p.unit = 'm' THEN coalesce(p.stick_length_m, 1) ELSE 1 END
  AND NOT (br.is_seasonal AND (extract(month FROM d.day) IN (12, 1, 2)
                               OR (extract(month FROM d.day) = 3 AND extract(day FROM d.day) < 15)))
GROUP BY 1, 2, 3
"""


def _query(conn, sql, params=None):
    cursor = conn.execute(sql, params)
    return pd.DataFrame(cursor.fetchall(), columns=[d.name for d in cursor.description])


def _monday(dates):
    dates = pd.to_datetime(pd.Series(dates))
    return dates - pd.to_timedelta(dates.dt.weekday, unit='D')


def _branch_open(day, is_seasonal):
    """Сезонная база работает с 15 марта по 30 ноября."""
    winter = day.dt.month.isin([12, 1, 2]) | ((day.dt.month == 3) & (day.dt.day < 15))
    return ~(is_seasonal & winter)


# ===== Панель =====

def build_panel(conn=None):
    """Недельная панель продаж «неделя × база × позиция» с разметкой дефицита."""
    if conn is None:
        with connect() as conn:
            return build_panel(conn)

    calendar = _query(conn, 'SELECT date, is_working_day, holiday_name FROM calendar ORDER BY date')
    calendar['date'] = pd.to_datetime(calendar['date'])
    start, end = calendar['date'].min(), calendar['date'].max()

    series = _query(conn, SERIES_SQL)
    for column in ['first_move', 'introduced_on', 'discontinued_on', 'opened_on']:
        series[column] = pd.to_datetime(series[column])
    series['start'] = series[['first_move', 'introduced_on', 'opened_on']].max(axis=1).clip(lower=start)
    series['end'] = (series['discontinued_on'] - pd.Timedelta(days=1)).fillna(end).clip(upper=end)
    series = series[series['end'] >= series['start']].reset_index(drop=True)

    # Сетка: все недели каждого ряда
    first_week, last_week = _monday(series['start']), _monday(series['end'])
    n_weeks = ((last_week - first_week).dt.days // 7 + 1).to_numpy()
    panel = series.loc[np.repeat(series.index, n_weeks)].reset_index(drop=True)
    panel['week'] = np.repeat(first_week.to_numpy(), n_weeks) + pd.to_timedelta(_offsets(n_weeks) * 7, unit='D')

    panel['active_days'] = _active_days(panel, calendar, start, end)

    sales = _query(conn, WEEKLY_SALES_SQL, {'b2b': B2B_SEGMENTS})
    stockouts = _query(conn, STOCKOUT_SQL, {'end': end.date()})
    for frame in (sales, stockouts):
        frame['week'] = pd.to_datetime(frame['week'])
    panel = panel.merge(sales, on=['week'] + SERIES_KEY, how='left').merge(
        stockouts, on=['week'] + SERIES_KEY, how='left')

    counts = ['qty', 'qty_b2b', 'orders', 'b2b_orders', 'customers', 'max_line', 'stockout_days']
    panel[counts] = panel[counts].fillna(0)
    panel['qty_base'] = panel['qty'] - panel['qty_b2b']
    panel['weight_t'] = panel['qty'] * panel['kg_per_unit'] / 1000
    panel['censored'] = panel['stockout_days'] > 0

    # Недели, когда база закрыта: спроса нет, это не ноль, а пропуск
    closed = panel['active_days'] == 0
    targets = ['qty', 'qty_base', 'qty_b2b', 'orders', 'b2b_orders', 'customers', 'max_line', 'weight_t']
    panel.loc[closed, targets] = np.nan
    panel.loc[closed, 'censored'] = False

    return panel.drop(columns=['first_move', 'start', 'end']).sort_values(['week'] + SERIES_KEY, ignore_index=True)


def _offsets(n_weeks):
    """0, 1, ..., n-1 для каждого ряда подряд."""
    ends = np.cumsum(n_weeks)
    return np.arange(ends[-1]) - np.repeat(ends - n_weeks, n_weeks)


def _active_days(panel, calendar, start, end):
    """Число дней недели, когда ряд существовал и база работала."""
    days = calendar[['date']].copy()
    days['week'] = _monday(days['date'])
    result = np.zeros(len(panel), dtype=int)
    for is_seasonal in (False, True):
        open_days = days[_branch_open(days['date'], is_seasonal)].groupby('week').size()
        rows = (panel['is_seasonal'] == is_seasonal).to_numpy()
        result[rows] = panel.loc[rows, 'week'].map(open_days).fillna(0).to_numpy()

    # Неполные первая и последняя недели ряда (ввод позиции, открытие базы, границы периода)
    week = panel['week']
    starts = panel[['introduced_on', 'opened_on']].max(axis=1).clip(lower=start)
    ends = (panel['discontinued_on'] - pd.Timedelta(days=1)).fillna(end).clip(upper=end)
    from_start = (week + pd.Timedelta(days=6) - starts).dt.days + 1
    to_end = (ends - week).dt.days + 1
    return np.clip(np.minimum(result, np.minimum(from_start, to_end)), 0, 7)


# ===== Признаки =====

def add_features(panel, horizon=1, conn=None):
    """Признаки для прогноза на horizon недель вперёд. Возвращает строки, где база работала."""
    if conn is None:
        with connect() as conn:
            return add_features(panel, horizon, conn)
    h = horizon
    p = panel.set_index(['week'] + SERIES_KEY).sort_index()
    weeks = p.index.get_level_values('week')
    series_keys = p.index.droplevel('week')
    category_keys = pd.MultiIndex.from_arrays([p.index.get_level_values('branch_id'), p['category_id']])
    product_keys = p.index.get_level_values('product_id')

    def wide(column):
        # недели × ряды; вне ряда и в закрытые недели - NaN
        return p[column].astype(float).unstack(SERIES_KEY)

    def rolling(frame, window, how='mean'):
        return getattr(frame.rolling(window, min_periods=1), how)()

    def lookup(frame, keys):
        # значение широкой таблицы для каждой строки панели: её неделя × её ключ
        rows, columns = frame.index.get_indexer(weeks), frame.columns.get_indexer(keys)
        values = np.full(len(p), np.nan)
        found = (rows >= 0) & (columns >= 0)
        values[found] = frame.to_numpy(dtype=float)[rows[found], columns[found]]
        return values

    features = {}

    # --- История ряда (по состоянию на origin = week - h) ---
    qty = wide('qty').shift(h)
    for k in range(EXTRA_LAGS + 1):
        features[f'qty_lag{h + k}'] = qty.shift(k)
    if h <= 52:
        features['qty_lag52'] = wide('qty').shift(52)
    for window in ROLLING_WINDOWS:
        features[f'qty_mean{window}'] = rolling(qty, window)
    features['qty_std13'] = rolling(qty, 13, 'std')
    features['qty_ewm'] = qty.ewm(alpha=0.3, ignore_na=True).mean()
    for window in (13, 26):
        features[f'nonzero_share{window}'] = rolling(qty.gt(0).astype(float).where(qty.notna()), window)
    features['weeks_since_sale'] = _weeks_since(qty.gt(0))

    base = wide('qty_base').shift(h)
    features[f'base_lag{h}'] = base
    for window in (4, 13):
        features[f'base_mean{window}'] = rolling(base, window)

    b2b = wide('qty_b2b').shift(h)
    b2b_orders = wide('b2b_orders').shift(h)
    for window in (13, 26):
        features[f'b2b_mean{window}'] = rolling(b2b, window)
        features[f'b2b_orders_sum{window}'] = rolling(b2b_orders, window, 'sum')
    features['b2b_line_mean26'] = rolling(b2b, 26, 'sum') / rolling(b2b_orders, 26, 'sum').replace(0, np.nan)

    orders = wide('orders').shift(h)
    features['orders_mean4'] = rolling(orders, 4)
    features['orders_mean13'] = rolling(orders, 13)
    features['customers_mean13'] = rolling(wide('customers').shift(h), 13)
    features['max_line13'] = rolling(wide('max_line').shift(h), 13, 'max')

    stockout_days = wide('stockout_days').shift(h)
    features[f'stockout_days_lag{h}'] = stockout_days
    features['stockout_days_sum4'] = rolling(stockout_days, 4, 'sum')
    features['censored_share13'] = rolling(wide('censored').shift(h), 13)

    result = p.copy()
    for name, frame in features.items():
        result[name] = lookup(frame, series_keys)

    # --- Иерархия: категория на базе и позиция по всей сети ---
    weight = p['weight_t']
    by_category = weight.groupby(['week', 'branch_id', p['category_id']]).sum(min_count=1).unstack(
        ['branch_id', 'category_id']).shift(h)
    by_product = weight.groupby(['week', 'product_id']).sum(min_count=1).unstack('product_id').shift(h)
    result['category_weight_lag'] = lookup(by_category, category_keys)
    result['category_weight_mean4'] = lookup(rolling(by_category, 4), category_keys)
    result['category_weight_mean13'] = lookup(rolling(by_category, 13), category_keys)
    result['network_weight_lag'] = lookup(by_product, product_keys)
    result['network_weight_mean4'] = lookup(rolling(by_product, 4), product_keys)
    result['network_weight_mean13'] = lookup(rolling(by_product, 13), product_keys)
    series_weight13 = lookup(rolling(wide('weight_t').shift(h), 13, 'sum'), series_keys)
    category_weight13 = lookup(rolling(by_category, 13, 'sum'), category_keys)
    result['category_share13'] = series_weight13 / np.where(category_weight13 > 0, category_weight13, np.nan)

    # --- Цены и рынок (по состоянию на origin) ---
    all_weeks = weeks.unique().sort_values()
    for name, frame in _price_features(conn, all_weeks, h, p).items():
        result[name] = lookup(frame, product_keys)
    for frame in (_market_features(conn, all_weeks, h), _calendar_features(conn)):
        for name in frame.columns:
            result[name] = frame[name].reindex(weeks).to_numpy()

    # --- Статические признаки ---
    result = result.reset_index()
    result['origin_week'] = result['week'] - pd.Timedelta(weeks=h)
    result['horizon'] = h
    result['product_age_weeks'] = (result['week'] - result['introduced_on']).dt.days / 7
    attributes = pd.json_normalize(result['attributes'])
    for name in ATTRIBUTE_FEATURES:
        result[name] = pd.to_numeric(attributes[name], errors='coerce') if name in attributes else np.nan
    for name in ['branch_format', 'unit']:
        result[name] = result[name].astype('category')

    result = result[result['active_days'] > 0]
    return result.drop(columns=['attributes', 'introduced_on', 'discontinued_on', 'opened_on']).reset_index(drop=True)


def feature_columns(frame):
    """Колонки результата add_features(), которые можно подавать в модель."""
    excluded = set(KEY_COLUMNS + TARGET_COLUMNS + DIAGNOSTIC_COLUMNS)
    return [column for column in frame.columns if column not in excluded]


def _weeks_since(mask):
    """Недель с последней недели, где mask истинен (NaN - не было ни разу)."""
    position = pd.DataFrame(np.arange(len(mask))[:, None].repeat(mask.shape[1], axis=1),
                            index=mask.index, columns=mask.columns)
    last = position.where(mask.fillna(False).astype(bool)).ffill()
    return position - last


def _price_features(conn, weeks, h, p):
    """Широкие таблицы недели × позиции с ценовыми признаками на origin."""
    prices = _query(conn, 'SELECT product_id, valid_from, retail_price::float8 AS price FROM price_history')
    prices['valid_from'] = pd.to_datetime(prices['valid_from'])
    days = pd.date_range(weeks.min(), weeks.max() + pd.Timedelta(days=6))
    daily = prices.pivot(index='valid_from', columns='product_id', values='price').reindex(days).ffill()
    # Цена на конец недели
    weekly = daily.loc[weeks + pd.Timedelta(days=6)].set_axis(weeks)
    origin = weekly.shift(h)

    kg = p.groupby('product_id')['kg_per_unit'].first()
    category = p.groupby('product_id')['category_id'].first()
    per_kg = origin / kg.reindex(origin.columns).to_numpy()
    category_mean = per_kg.T.groupby(category.reindex(per_kg.columns).to_numpy()).transform('mean').T

    return {
        'price': origin,
        'price_rel13': origin / origin.rolling(13, min_periods=1).mean(),
        'price_change4': origin / weekly.shift(h + 4) - 1,
        'price_rel_category': per_kg / category_mean,
    }


def _market_features(conn, weeks, h):
    index = _query(conn, 'SELECT date, value::float8 AS value FROM metal_price_index')
    index['week'] = _monday(index['date'])
    weekly = index.groupby('week')['value'].mean().reindex(weeks)
    origin = weekly.shift(h)
    return pd.DataFrame({
        'metal_index': origin,
        'metal_index_change4': origin / weekly.shift(h + 4) - 1,
        'metal_index_rel13': origin / origin.rolling(13, min_periods=1).mean(),
    })


def _calendar_features(conn):
    calendar = _query(conn, 'SELECT date, is_working_day, holiday_name FROM calendar')
    calendar['week'] = _monday(calendar['date'])
    weekly = calendar.groupby('week').agg(working_days=('is_working_day', 'sum'),
                                          holidays=('holiday_name', 'count'))
    week_of_year = weekly.index.isocalendar().week.astype(float)
    weekly['week_sin'] = np.sin(2 * np.pi * week_of_year / WEEKS_PER_YEAR)
    weekly['week_cos'] = np.cos(2 * np.pi * week_of_year / WEEKS_PER_YEAR)
    weekly['month'] = (weekly.index + pd.Timedelta(days=3)).month
    return weekly
