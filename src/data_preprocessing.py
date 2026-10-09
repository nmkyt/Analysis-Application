import pandas as pd
import mysql.connector as sql
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from config import settings

connection = None

try:
    # Установка параметров подключения к базе данных (значения берутся из .env)
    connection = sql.connect(
        host=settings.db.host,
        port=settings.db.port,
        user=settings.db.user,
        password=settings.db.password.get_secret_value(),
        database=settings.db.name
    )

    if connection.is_connected():
        connection_state = "Подключено к базе данных"
    else:
        connection_state = "Не удалось подключиться к базе данных"
except sql.Error as e:
    connection_state = "Ошибка при подключении к базе данных: " + str(e)


def dataSelection(x):
    # Без подключения к базе данных загрузить данные невозможно
    if connection is None or not connection.is_connected():
        raise ConnectionError(connection_state)

    # SQL запрос для выборки данных из таблицы
    sql_query = "SELECT * FROM sales_data;"

    # Чтение данных из MySQL и сохранение их в DataFrame
    df = pd.read_sql(sql_query, connection)

    # Определение столбцов, к которым будет применяться OneHotEncoder
    categorical_columns = [0]

    # Определение трансформации для применения OneHotEncoder.
    # Категории, которых нет в обучающих данных, кодируются нулями
    column_transformer = ColumnTransformer(
        [('one_hot_encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical_columns)],
        remainder='passthrough'
    )

    # Применение трансформации к данным и преобразование их в DataFrame
    transformed_data = column_transformer.fit_transform(df)
    transformed_df = pd.DataFrame(transformed_data)

    # Разделение данных на признаки и целевую переменную
    target = transformed_df.iloc[:, [x]]
    attributes = transformed_df.drop(transformed_df.columns[[x]], axis=1)
    target = target.values.ravel()

    # Загрузка таблицы для прогнозов
    sql_query = "SELECT * FROM sales_prediction;"
    prediction_df = pd.read_sql(sql_query, connection)

    # Используется та же трансформация, что и для обучающих данных,
    # чтобы столбцы признаков совпадали по составу и порядку
    transformed_data = column_transformer.transform(prediction_df)
    prediction_df = pd.DataFrame(transformed_data)
    prediction_df = prediction_df.drop(prediction_df.columns[[x]], axis=1)
    return attributes, target, prediction_df
