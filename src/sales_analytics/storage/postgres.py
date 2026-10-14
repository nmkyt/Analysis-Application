"""Подключение к базе данных учётной системы, создание роли и базы на сервере."""
import psycopg
from psycopg import sql

from ..config import settings
from ..exceptions import StorageError


def connect(**kwargs):
    """Подключение к базе с параметрами из .env.

    Аргументы host, port, user, password, dbname заменяют значения из .env,
    остальные передаются в psycopg.connect.
    """
    params = {
        'host': settings.db.host,
        'port': settings.db.port,
        'user': settings.db.user,
        'password': settings.db.password.get_secret_value(),
        'dbname': settings.db.name,
        **kwargs,
    }
    try:
        return psycopg.connect(**params)
    except psycopg.OperationalError as e:
        raise StorageError(
            f'Не удалось подключиться к {params["dbname"]} на {params["host"]}:{params["port"]} '
            f'как {params["user"]}: {e}'
        ) from e


def create_database(superuser='postgres', password=None):
    """Создаёт роль и базу из .env от имени суперпользователя; роль становится владельцем базы.

    Если роль и база уже есть, обновляется только пароль роли. password - пароль суперпользователя;
    если не задан, psycopg берёт его из PGPASSWORD или pgpass.
    """
    role, database = settings.db.user, settings.db.name
    role_password = settings.db.password.get_secret_value()
    if not role_password:
        raise StorageError('В .env не задан DB_PASSWORD')

    credentials = {'user': superuser, 'dbname': 'postgres'}
    if password is not None:
        credentials['password'] = password
    # CREATE DATABASE нельзя выполнить внутри транзакции
    with connect(**credentials, autocommit=True) as conn:
        try:
            if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname = %s', [role]).fetchone():
                conn.execute(sql.SQL('CREATE ROLE {} LOGIN').format(sql.Identifier(role)))
            conn.execute(sql.SQL('ALTER ROLE {} WITH LOGIN PASSWORD {}').format(
                sql.Identifier(role), sql.Literal(role_password)))

            if not conn.execute('SELECT 1 FROM pg_database WHERE datname = %s', [database]).fetchone():
                conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(
                    sql.Identifier(database), sql.Identifier(role)))

            # Подключаться к базе может только владелец и суперпользователи
            conn.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(database)))
            conn.execute(sql.SQL('GRANT ALL ON DATABASE {} TO {}').format(
                sql.Identifier(database), sql.Identifier(role)))
        except psycopg.Error as e:
            raise StorageError(f'Не удалось создать роль {role} и базу {database}: {e}') from e
