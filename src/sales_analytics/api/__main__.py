"""Запуск REST API: python -m sales_analytics.api [--host 127.0.0.1] [--port 8000]

Документация с возможностью вызвать любой запрос - http://127.0.0.1:8000/docs
"""
import argparse

import uvicorn

from ..config import settings


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', default=settings.api_host, help='адрес (по умолчанию: %(default)s, API_HOST)')
    parser.add_argument('--port', type=int, default=settings.api_port, help='порт (по умолчанию: %(default)s, API_PORT)')
    args = parser.parse_args()
    uvicorn.run('sales_analytics.api:app', host=args.host, port=args.port)


if __name__ == '__main__':
    main()
