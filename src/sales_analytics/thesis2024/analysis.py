from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor


def analysis(attributes, target, df):
    # Разделение данных на обучающий и тестовый наборы
    attributes_train, attributes_test, target_train, target_test = train_test_split(attributes, target,
                                                                                    test_size=0.2,
                                                                                    random_state=42)

    # Инициализация и обучение модели случайного леса
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(attributes_train, target_train)

    # Оценка точности на тестовом наборе, который модель не видела при обучении
    mae = mean_absolute_error(target_test, model.predict(attributes_test))

    # Предсказание значений целевой переменной
    target_prediction = model.predict(df)
    return target_prediction, mae
