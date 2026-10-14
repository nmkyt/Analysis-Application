"""Прогноз спроса: обучение моделей, прогноз и графики.

    python -m sales_analytics.forecasting train [--horizon 1 2 3 4] [--data DIR] [--save-data]
    python -m sales_analytics.forecasting predict [--horizon 1 2 3 4] [--data DIR]
    python -m sales_analytics.forecasting report [--dir docs/images]

Данные читаются из базы, а с --data - из датасета в CSV (например, --data data).
Результаты сохраняются в output/ (OUTPUT_DIR). Те же действия доступны через REST API: python -m sales_analytics.api
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

from ..exceptions import SalesAnalyticsError
from ..storage import load_demand_data, load_demand_data_csv
from .model import HORIZONS, METHODS, forecast, save, save_forecast, train
from .preprocessing import build_panel
from .report import build_report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    for name, help_text in [('train', 'обучить и сохранить модели'), ('predict', 'прогноз сохранёнными моделями')]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument('--horizon', type=int, nargs='+', default=list(HORIZONS),
                             help='горизонты прогноза в неделях (по умолчанию: %(default)s)')
        command.add_argument('--data', type=Path, help='папка датасета в CSV вместо базы')
    commands.choices['train'].add_argument('--save-data', action='store_true',
                                           help='сохранить выборки для обучения в output/training')
    report = commands.add_parser('report', help='графики по сохранённым моделям и последнему прогнозу')
    report.add_argument('--dir', type=Path, help='папка для графиков (по умолчанию: docs/images)')
    args = parser.parse_args()

    try:
        if args.command == 'report':
            for path in build_report(args.dir):
                print(f'Сохранено: {path}')
            return
        print(f'Загрузка данных из {args.data or "базы"}')
        data = load_demand_data_csv(args.data) if args.data else load_demand_data()
        if args.command == 'train':
            _train(data, args.horizon, args.save_data)
        else:
            _predict(data, args.horizon)
    except (SalesAnalyticsError, ValueError) as e:
        sys.exit(str(e))


def _train(data, horizons, save_data):
    panel = build_panel(data)
    for horizon in horizons:
        print(f'\nГоризонт {horizon} нед.: обучение')
        result = train(panel, horizon, save_data=save_data)
        path = save(result)
        test = result.periods['test']
        print(f'Тест {test[0]} - {test[1]}, итераций: {result.model.n_iter_}')
        print(_format(result.metrics.rename(index={METHODS['naive']: f'как {horizon} нед. назад'})))
        print('\nWAPE по единицам измерения')
        print(_format(result.wape_by_unit))
        print(f'Сохранено: {path}')


def _predict(data, horizons):
    result = forecast(data, horizons)
    path = save_forecast(result)

    print(f'Последняя известная неделя: {result["origin_week"].iloc[0].date()}')
    total = result.groupby(['horizon', 'week'])['forecast_kg'].sum().div(1000).rename('тонн').reset_index()
    print(total.to_string(index=False, float_format=lambda value: f'{value:.1f}'))
    print(f'Сохранено: {path} ({len(result)} строк)')


def _format(frame: pd.DataFrame):
    return frame.to_string(float_format=lambda value: f'{value:.3f}')


if __name__ == '__main__':
    main()
