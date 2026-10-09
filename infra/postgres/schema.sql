-- Создание роли и базы данных проекта.
-- Запускается от суперпользователя, имя роли, базы и пароль передаются переменными psql:
--   psql -U postgres -h localhost -d postgres \
--        -v app_user=metal_market -v app_db=metal_market -v app_password=... \
--        -f infra/postgres/schema.sql

\set ON_ERROR_STOP on

-- Роль приложения: создаётся, если её ещё нет, пароль обновляется в любом случае
SELECT format('CREATE ROLE %I LOGIN', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec

ALTER ROLE :"app_user" WITH LOGIN PASSWORD :'app_password';

-- База данных, владельцем которой является роль приложения
SELECT format('CREATE DATABASE %I OWNER %I ENCODING ''UTF8'' TEMPLATE template0', :'app_db', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db') \gexec

-- Подключаться к базе может только владелец и суперпользователи
REVOKE ALL ON DATABASE :"app_db" FROM PUBLIC;
GRANT ALL ON DATABASE :"app_db" TO :"app_user";
