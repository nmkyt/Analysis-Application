import pandas as pd
import mysql.connector as sql
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder

try:
    # Установка параметров подключения к базе данных
    connection = sql.connect(
        host="localhost",
        user="user",
        password="",
        database="analysissystem"
    )

    # Если подключение успешно, выведется сообщение "Подключено к базе данных"
    if connection.is_connected():
        connection_state = "Подключено к базе данных"
    else:
        connection_state = "Подключено к базе данных"
except sql.connection.Error as e:
    connection_state = ("Ошибка при подключении к базе данных:", str(e))


def dataSelection(x):
    # SQL запрос для выборки данных из таблицы
    sql_query = "SELECT * FROM sales_data;"

    # Чтение данных из MySQL и сохранение их в DataFrame
    df = pd.read_sql(sql_query, connection)

    # Инициализация OneHotEncoder
    encoder = OneHotEncoder()

    # Определение столбцов, к которым будет применяться OneHotEncoder
    categorical_columns = [0]

    # Определение трансформации для применения OneHotEncoder
    column_transformer = ColumnTransformer(
        [('one_hot_encoder', encoder, categorical_columns)],
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
    categorical_columns = [0]
    column_transformer = ColumnTransformer(
        [('one_hot_encoder', encoder, categorical_columns)],
        remainder='passthrough'
    )
    transformed_data = column_transformer.fit_transform(prediction_df)
    prediction_df = pd.DataFrame(transformed_data)
    prediction_df = prediction_df.drop(prediction_df.columns[[x]], axis=1)
    return attributes, target, prediction_df
