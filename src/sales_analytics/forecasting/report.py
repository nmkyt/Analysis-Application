"""Графики качества и прогноза (PNG) по сохранённым моделям и последнему прогнозу.

    metrics_by_horizon.png - WAPE модели и ориентиров на тесте по горизонтам
    network_forecast.png   - продажи сети по неделям: факт, прогноз на тесте и прогноз на будущее
    series_examples.png    - факт и прогноз на тесте для четырёх крупнейших рядов
"""
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter, MultipleLocator, PercentFormatter  # noqa: E402

from ..config import BASE_DIR, settings  # noqa: E402
from ..exceptions import ModelError  # noqa: E402
from .model import METHODS, evaluation_path, latest_forecast, saved_models  # noqa: E402

# Цвета рядов проверены на различимость при нарушениях цветового зрения,
# у оранжевого и жёлтого низкий контраст с фоном, поэтому у линий есть подписи
SURFACE, INK, INK_SECONDARY, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
COLORS = {'model': '#2a78d6', 'naive': '#eb6834', 'seasonal': '#1baf7a', 'mean4': '#eda100'}
FACT_COLOR = INK_SECONDARY

plt.rcParams.update({
    'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE, 'savefig.facecolor': SURFACE,
    'font.family': 'sans-serif', 'font.sans-serif': ['Segoe UI', 'DejaVu Sans'], 'font.size': 10,
    'text.color': INK, 'axes.labelcolor': INK_SECONDARY, 'axes.titlecolor': INK,
    'axes.titlesize': 12, 'axes.titleweight': 'bold', 'axes.titlelocation': 'left',
    'axes.edgecolor': AXIS, 'axes.spines.top': False, 'axes.spines.right': False,
    'axes.grid': True, 'axes.grid.axis': 'y', 'grid.color': GRID, 'grid.linewidth': 0.8,
    'xtick.color': MUTED, 'ytick.color': MUTED, 'xtick.labelcolor': INK_SECONDARY,
    'ytick.labelcolor': INK_SECONDARY, 'lines.linewidth': 2, 'lines.solid_capstyle': 'round',
})


def build_report(directory=None):
    """Строит графики в directory (по умолчанию docs/images), возвращает пути к файлам."""
    directory = directory or BASE_DIR / 'docs' / 'images'
    directory.mkdir(parents=True, exist_ok=True)
    metrics = {horizon: metadata['metrics'] for horizon, metadata in saved_models().items()}
    if not metrics:
        raise ModelError(f'В {settings.models_dir} нет моделей: python -m sales_analytics.forecasting train')
    test = pd.read_csv(_existing(evaluation_path(min(metrics))), parse_dates=['week'])
    future, _ = latest_forecast()

    paths = [directory / 'metrics_by_horizon.png', directory / 'network_forecast.png',
             directory / 'series_examples.png']
    for path, draw in zip(paths, [lambda: _plot_metrics(metrics), lambda: _plot_network(test, future),
                                  lambda: _plot_series(test, future)]):
        figure = draw()
        figure.savefig(path, dpi=150, bbox_inches='tight')
        plt.close(figure)
    return paths


def _plot_metrics(metrics):
    figure, ax = plt.subplots(figsize=(8, 4.2))
    horizons = sorted(metrics)
    for method, label in METHODS.items():
        values = [metrics[h][label]['wape'] for h in horizons]
        ax.plot(horizons, values, color=COLORS[method], marker='o', markersize=6,
                markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.annotate(label, (horizons[-1], values[-1]), xytext=(10, 0), textcoords='offset points',
                    va='center', color=INK_SECONDARY)
    ax.set_xticks(horizons, [f'{h} нед.' for h in horizons])
    ax.set_xlim(horizons[0] - 0.2, horizons[-1] + 0.2)
    ax.yaxis.set_major_locator(MultipleLocator(0.05))
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    ax.set_xlabel('горизонт прогноза')
    ax.set_title('WAPE на тесте по горизонтам: чем ниже, тем лучше')
    return figure


def _plot_network(test, future):
    figure, ax = plt.subplots(figsize=(9, 4.2))
    weekly = (test.assign(fact_t=test['fact'] * test['kg_per_unit'] / 1000,
                          model_t=test['model'] * test['kg_per_unit'] / 1000)
              .groupby('week')[['fact_t', 'model_t']].sum())
    ax.plot(weekly.index, weekly['fact_t'], color=FACT_COLOR, label='факт')
    ax.plot(weekly.index, weekly['model_t'], color=COLORS['model'], label='прогноз на неделю вперёд (тест)')

    if future is not None:
        ahead = future.groupby('week')['forecast_kg'].sum() / 1000
        origin = pd.Timestamp(future['origin_week'].iloc[0])
        line = pd.concat([pd.Series({origin: weekly['model_t'].get(origin, ahead.iloc[0])}), ahead])
        ax.plot(line.index, line.values, color=COLORS['model'], linestyle=(0, (3, 2)), marker='o',
                markersize=5, markevery=list(range(1, len(line))), label=f'прогноз на {len(ahead)} нед. вперёд')
        ax.axvline(origin + pd.Timedelta(days=3), color=AXIS, linewidth=1)

    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:,.0f}'.replace(',', ' ')))
    ax.set_ylabel('тонн в неделю')
    ax.legend(frameon=False, loc='lower left', labelcolor=INK_SECONDARY)
    ax.set_title('Продажи сети: факт и прогноз')
    figure.autofmt_xdate()
    return figure


def _plot_series(test, future):
    weight = test.assign(kg=test['fact'] * test['kg_per_unit']).groupby(['branch_id', 'product_id'])['kg'].sum()
    top = weight.nlargest(4).index
    names = None
    if future is not None:
        names = future.drop_duplicates(['branch_id', 'product_id']).set_index(['branch_id', 'product_id'])

    figure, axes = plt.subplots(2, 2, figsize=(10, 6), sharex=True)
    for ax, key in zip(axes.flat, top):
        series = test[(test['branch_id'] == key[0]) & (test['product_id'] == key[1])].sort_values('week')
        ax.plot(series['week'], series['fact'], color=FACT_COLOR, label='факт')
        ax.plot(series['week'], series['model'], color=COLORS['model'], label='прогноз')
        unit = series['unit'].iloc[0]
        if names is not None and key in names.index:
            row = names.loc[key]
            title = f'{row["branch_code"]} · {row["name"]}'
        else:
            title = f'база {key[0]} · позиция {key[1]}'
        ax.set_title(title if len(title) <= 45 else title[:44] + '…', fontsize=10)
        ax.set_ylim(bottom=0)
        ax.set_ylabel(unit)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    figure.legend(handles, labels, frameon=False, loc='upper right', ncols=2, labelcolor=INK_SECONDARY)
    figure.suptitle('Четыре крупнейших ряда на тесте: прогноз на неделю вперёд', x=0.01, ha='left',
                    fontsize=12, fontweight='bold', color=INK)
    figure.autofmt_xdate()
    figure.tight_layout()
    return figure


def _existing(path):
    if not path.exists():
        raise ModelError(f'Нет файла {path}: python -m sales_analytics.forecasting train')
    return path
