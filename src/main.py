import pandas as pd
import matplotlib.pyplot as plt
import analysis
import data_preprocessing as data
from config import settings
import customtkinter
from tkinter import messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Глобальные переменные для хранения номера отчёта и количества месяцев
selected_report = None
selected_months = None

# Меню выбора категории (создаётся один раз при первом выборе отчёта по категориям)
category_selection_menu = None


# Функция для обновления выбранного отчета
def update_selected_report(option):
    global selected_report
    selected_report = option


# Функция для обновления выбранного количества месяцев
def update_selected_months(option):
    global selected_months
    selected_months = int(option)


# Функция обработки выбора отчета
def handle_report_selection():
    global selected_report, selected_months
    if selected_report is None:
        messagebox.showwarning("Отчёт не выбран", "Выберите тип отчёта")
        return
    if selected_months is None:
        messagebox.showwarning("Период не выбран", "Выберите количество месяцев")
        return

    try:
        if selected_report == 'Отчёт о выручке':
            generate_revenue_report(selected_months)
        elif selected_report == 'Отчёт о продажах':
            generate_sales_report(selected_months)
        elif selected_report == 'Отчёт по категориям':
            handle_category_selection()
    except Exception as e:
        show_report_error(e)


# Функция вывода сообщения об ошибке при формировании отчёта
def show_report_error(error):
    messagebox.showerror("Ошибка", "Не удалось сформировать отчёт:\n" + str(error))


def generate_revenue_report(months):

    # Генерация данных для прогноза
    attributes, target, df = data.dataSelection(12)
    x, mae = analysis.analysis(attributes, target, df)

    # Создаем новое окно для отчета
    report_window = customtkinter.CTkToplevel(root)
    report_window.title("Отчет о выручке")
    report_window.geometry("800x600")
    months_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    # Обрезаем список месяцев до нужного количества
    months_labels = months_labels[:months]
    forecast_sales = {
        'Month': months_labels,
        'Revenue': x[:months]
    }

    # Создание DataFrame из прогноза продаж
    df_forecast = pd.DataFrame(forecast_sales)

    # Создание графика прогноза продаж
    fig, ax = plt.subplots(figsize=(6, 3.3))
    ax.plot(df_forecast['Month'], df_forecast['Revenue'], marker='o', linestyle='-')
    ax.set_title('Прогноз выручки на следующие ' + str(months) + ' месяцев')
    ax.set_xlabel('Месяц')
    ax.set_ylabel('Выручка')
    ax.tick_params(axis='x', rotation=45)
    ax.grid(True)

    # Отображение графика в новом окне
    canvas = FigureCanvasTkAgg(fig, master=report_window)
    canvas.draw()
    canvas.get_tk_widget().pack()

    # Сохранение графика в файл
    fig.savefig(settings.data_dir / 'forecast_revenue_report.png')

    # Создание отчета в текстовый файл
    with open(settings.data_dir / 'forecast_revenue_report.txt', 'w', encoding='utf-8') as file:
        file.write("Отчет с прогнозом выручки за следующие " + str(months) + " месяцев:\n")
        file.write(df_forecast.to_string(index=False))

    # Вывод сообщения об успешном сохранении отчета в новом окне
    info_textbox = customtkinter.CTkTextbox(report_window, height=600, width=500)
    info_textbox.pack()
    info_textbox.insert("end", "Отчет с прогнозом выручки сохранен в файл forecast_revenue_report.txt\n")
    info_textbox.insert("end", "Средняя абсолютная ошибка MAE: " + str(mae) + "\n")
    info_textbox.insert("end", "Отчет с прогнозом выручки за следующие " + str(months) + " месяцев:\n")
    info_textbox.insert("end", df_forecast.to_string(index=False))


def generate_sales_report(months):
    # Генерация данных для прогноза
    attributes, target, df = data.dataSelection(20)
    x, mae = analysis.analysis(attributes, target, df)

    # Создаем новое окно для отчета
    report_window = customtkinter.CTkToplevel(root)
    report_window.title("Отчет о продажах")
    report_window.geometry("800x600")
    months_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    # Обрезаем список месяцев до нужного количества
    months_labels = months_labels[:months]
    forecast_sales = {
        'Month': months_labels,
        'Sales': x[:months]
    }

    # Создание DataFrame из прогноза продаж
    df_forecast = pd.DataFrame(forecast_sales)

    # Создание графика прогноза продаж
    fig, ax = plt.subplots(figsize=(6, 3.3))
    ax.plot(df_forecast['Month'], df_forecast['Sales'], marker='o', linestyle='-')
    ax.set_title('Прогноз продаж на следующие ' + str(months) + ' месяцев')
    ax.set_xlabel('Месяц')
    ax.set_ylabel('Продажи')
    ax.tick_params(axis='x', rotation=45)
    ax.grid(True)

    # Отображение графика в новом окне
    canvas = FigureCanvasTkAgg(fig, master=report_window)
    canvas.draw()
    canvas.get_tk_widget().pack()

    # Сохранение графика в файл
    fig.savefig(settings.data_dir / 'forecast_sales_report.png')

    # Создание отчета в текстовый файл
    with open(settings.data_dir / 'forecast_sales_report.txt', 'w', encoding='utf-8') as file:
        file.write("Отчет с прогнозом продаж на следующие " + str(months) + " месяцев:\n")
        file.write(df_forecast.to_string(index=False))

    # Вывод сообщения об успешном сохранении отчета в новом окне
    info_textbox = customtkinter.CTkTextbox(report_window, height=600, width=500)
    info_textbox.pack()
    info_textbox.insert("end", "Отчет с прогнозом продаж сохранен в файл forecast_sales_report.txt\n")
    info_textbox.insert("end", "Средняя абсолютная ошибка MAE: " + str(mae) + "\n")
    info_textbox.insert("end", "Отчет с прогнозом продаж на следующие " + str(months) + " месяцев:\n")
    info_textbox.insert("end", df_forecast.to_string(index=False))


def handle_category_selection():
    global category_selection_menu

    # Меню категорий уже показано - повторно не создаём
    if category_selection_menu is not None:
        return

    # Текст бокс

    category_textbox = customtkinter.CTkTextbox(root, height=70, width=400)
    category_textbox.pack(pady=20)
    category_textbox.insert("end", "Выберите нужную категорию:")

    # Выбор категории

    category_selection_menu = customtkinter.CTkOptionMenu(root, values=["Трубы", "Металлические конструкции", "Метизы", "Нержавеющая сталь", "Металлические сетки"], command=handle_category_report)
    category_selection_menu.pack(pady=10)
    category_selection_menu.set("Категории")


# Функция обработки выбора категории
def handle_category_report(option):
    try:
        generate_category_report(option)
    except Exception as e:
        show_report_error(e)


def generate_category_report(option):

    global selected_months
    months = selected_months

    if option == "Трубы":

        # Генерация данных для прогноза
        attributes, target, df = data.dataSelection(15)
        x, mae = analysis.analysis(attributes, target, df)

        # Создаем новое окно для отчета
        report_window = customtkinter.CTkToplevel(root)
        report_window.title("Отчет о продажах труб")
        report_window.geometry("800x600")
        months_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        # Обрезаем список месяцев до нужного количества
        months_labels = months_labels[:months]
        forecast_sales = {
            'Month': months_labels,
            'Pipes': x[:months]
        }

        # Создание DataFrame из прогноза продаж
        df_forecast = pd.DataFrame(forecast_sales)

        # Создание графика прогноза продаж
        fig, ax = plt.subplots(figsize=(6, 3.3))
        ax.plot(df_forecast['Month'], df_forecast['Pipes'], marker='o', linestyle='-')
        ax.set_title('Прогноз продаж труб на следующие ' + str(months) + ' месяцев')
        ax.set_xlabel('Месяц')
        ax.set_ylabel('Продажи')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True)

        # Отображение графика в новом окне
        canvas = FigureCanvasTkAgg(fig, master=report_window)
        canvas.draw()
        canvas.get_tk_widget().pack()

        # Сохранение графика в файл
        fig.savefig(settings.data_dir / 'forecast_pipes_sales_report.png')

        # Создание отчета в текстовый файл
        with open(settings.data_dir / 'forecast_pipes_sales_report.txt', 'w', encoding='utf-8') as file:
            file.write("Отчет с прогнозом продаж труб на следующие " + str(months) + " месяцев:\n")
            file.write(df_forecast.to_string(index=False))

        # Вывод сообщения об успешном сохранении отчета в новом окне
        info_textbox = customtkinter.CTkTextbox(report_window, height=600, width=500)
        info_textbox.pack()
        info_textbox.insert("end", "Отчет с прогнозом продаж труб сохранен в файл forecast_pipes_sales_report.txt\n")
        info_textbox.insert("end", "Средняя абсолютная ошибка MAE: " + str(mae) + "\n")
        info_textbox.insert("end", "Отчет с прогнозом продаж труб на следующие " + str(months) + " месяцев:\n")
        info_textbox.insert("end", df_forecast.to_string(index=False))

    if option == "Металлические конструкции":

        # Генерация данных для прогноза
        attributes, target, df = data.dataSelection(16)
        x, mae = analysis.analysis(attributes, target, df)

        # Создаем новое окно для отчета
        report_window = customtkinter.CTkToplevel(root)
        report_window.title("Отчет о продажах металлический конструкций")
        report_window.geometry("800x600")
        months_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        # Обрезаем список месяцев до нужного количества
        months_labels = months_labels[:months]
        forecast_sales = {
            'Month': months_labels,
            'Constructions': x[:months]
        }

        # Создание DataFrame из прогноза продаж
        df_forecast = pd.DataFrame(forecast_sales)

        # Создание графика прогноза продаж
        fig, ax = plt.subplots(figsize=(6, 3.3))
        ax.plot(df_forecast['Month'], df_forecast['Constructions'], marker='o', linestyle='-')
        ax.set_title('Прогноз продаж метал. конструкций на следующие ' + str(months) + ' месяцев')
        ax.set_xlabel('Месяц')
        ax.set_ylabel('Продажи')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True)

        # Отображение графика в новом окне
        canvas = FigureCanvasTkAgg(fig, master=report_window)
        canvas.draw()
        canvas.get_tk_widget().pack()

        # Сохранение графика в файл
        fig.savefig(settings.data_dir / 'forecast_constructions_sales_report.png')

        # Создание отчета в текстовый файл
        with open(settings.data_dir / 'forecast_constructions_sales_report.txt', 'w', encoding='utf-8') as file:
            file.write("Отчет с прогнозом продаж метал. конструкций на следующие " + str(months) + " месяцев:\n")
            file.write(df_forecast.to_string(index=False))

        # Вывод сообщения об успешном сохранении отчета в новом окне
        info_textbox = customtkinter.CTkTextbox(report_window, height=600, width=500)
        info_textbox.pack()
        info_textbox.insert("end", "Отчет с прогнозом продаж метал. конструкций сохранен в файл forecast_constructions_sales_report.txt\n")
        info_textbox.insert("end", "Средняя абсолютная ошибка MAE: " + str(mae) + "\n")
        info_textbox.insert("end", "Отчет с прогнозом продаж метал. конструкций на следующие " + str(months) + " месяцев:\n")
        info_textbox.insert("end", df_forecast.to_string(index=False))

    if option == "Метизы":

        # Генерация данных для прогноза
        attributes, target, df = data.dataSelection(17)
        x, mae = analysis.analysis(attributes, target, df)

        # Создаем новое окно для отчета
        report_window = customtkinter.CTkToplevel(root)
        report_window.title("Отчет о продажах метизов")
        report_window.geometry("800x600")
        months_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        # Обрезаем список месяцев до нужного количества
        months_labels = months_labels[:months]
        forecast_sales = {
            'Month': months_labels,
            'Hardware': x[:months]
        }

        # Создание DataFrame из прогноза продаж
        df_forecast = pd.DataFrame(forecast_sales)

        # Создание графика прогноза продаж
        fig, ax = plt.subplots(figsize=(6, 3.3))
        ax.plot(df_forecast['Month'], df_forecast['Hardware'], marker='o', linestyle='-')
        ax.set_title('Прогноз продаж метизов на следующие ' + str(months) + ' месяцев')
        ax.set_xlabel('Месяц')
        ax.set_ylabel('Метизы')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True)

        # Отображение графика в новом окне
        canvas = FigureCanvasTkAgg(fig, master=report_window)
        canvas.draw()
        canvas.get_tk_widget().pack()

        # Сохранение графика в файл
        fig.savefig(settings.data_dir / 'forecast_hardware_sales_report.png')

        # Создание отчета в текстовый файл
        with open(settings.data_dir / 'forecast_hardware_sales_report.txt', 'w', encoding='utf-8') as file:
            file.write("Отчет с прогнозом продаж метизов на следующие " + str(months) + " месяцев:\n")
            file.write(df_forecast.to_string(index=False))

        # Вывод сообщения об успешном сохранении отчета в новом окне
        info_textbox = customtkinter.CTkTextbox(report_window, height=600, width=500)
        info_textbox.pack()
        info_textbox.insert("end", "Отчет с прогнозом продаж метизов сохранен в файл forecast_hardware_sales_report.txt\n")
        info_textbox.insert("end", "Средняя абсолютная ошибка MAE: " + str(mae) + "\n")
        info_textbox.insert("end", "Отчет с прогнозом продаж метизов на следующие " + str(months) + " месяцев:\n")
        info_textbox.insert("end", df_forecast.to_string(index=False))

    if option == "Нержавеющая сталь":

        # Генерация данных для прогноза
        attributes, target, df = data.dataSelection(18)
        x, mae = analysis.analysis(attributes, target, df)

        # Создаем новое окно для отчета
        report_window = customtkinter.CTkToplevel(root)
        report_window.title("Отчет о продажах нержавеющей стали")
        report_window.geometry("800x600")
        months_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        # Обрезаем список месяцев до нужного количества
        months_labels = months_labels[:months]
        forecast_sales = {
            'Month': months_labels,
            'Stainless': x[:months]
        }

        # Создание DataFrame из прогноза продаж
        df_forecast = pd.DataFrame(forecast_sales)

        # Создание графика прогноза продаж
        fig, ax = plt.subplots(figsize=(6, 3.3))
        ax.plot(df_forecast['Month'], df_forecast['Stainless'], marker='o', linestyle='-')
        ax.set_title('Прогноз продаж нержавеющей стали на следующие ' + str(months) + ' месяцев')
        ax.set_xlabel('Месяц')
        ax.set_ylabel('Нержавеющая сталь')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True)

        # Отображение графика в новом окне
        canvas = FigureCanvasTkAgg(fig, master=report_window)
        canvas.draw()
        canvas.get_tk_widget().pack()

        # Сохранение графика в файл
        fig.savefig(settings.data_dir / 'forecast_stainless_sales_report.png')

        # Создание отчета в текстовый файл
        with open(settings.data_dir / 'forecast_stainless_sales_report.txt', 'w', encoding='utf-8') as file:
            file.write("Отчет с прогнозом продаж нержавеющей стали на следующие " + str(months) + " месяцев:\n")
            file.write(df_forecast.to_string(index=False))

        # Вывод сообщения об успешном сохранении отчета в новом окне
        info_textbox = customtkinter.CTkTextbox(report_window, height=600, width=500)
        info_textbox.pack()
        info_textbox.insert("end", "Отчет с прогнозом продаж нержавеющей стали сохранен в файл forecast_stainless_sales_report.txt\n")
        info_textbox.insert("end", "Средняя абсолютная ошибка MAE: " + str(mae) + "\n")
        info_textbox.insert("end", "Отчет с прогнозом продаж нержавеющей стали на следующие " + str(months) + " месяцев:\n")
        info_textbox.insert("end", df_forecast.to_string(index=False))

    if option == "Металлические сетки":

        # Генерация данных для прогноза
        attributes, target, df = data.dataSelection(19)
        x, mae = analysis.analysis(attributes, target, df)

        # Создаем новое окно для отчета
        report_window = customtkinter.CTkToplevel(root)
        report_window.title("Отчет о продажах металлических сеток")
        report_window.geometry("800x600")
        months_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        # Обрезаем список месяцев до нужного количества
        months_labels = months_labels[:months]
        forecast_sales = {
            'Month': months_labels,
            'Grid': x[:months]
        }

        # Создание DataFrame из прогноза продаж
        df_forecast = pd.DataFrame(forecast_sales)

        # Создание графика прогноза продаж
        fig, ax = plt.subplots(figsize=(6, 3.3))
        ax.plot(df_forecast['Month'], df_forecast['Grid'], marker='o', linestyle='-')
        ax.set_title('Прогноз продаж металлических сеток на следующие ' + str(months) + ' месяцев')
        ax.set_xlabel('Месяц')
        ax.set_ylabel('Металлические сетки')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True)

        # Отображение графика в новом окне
        canvas = FigureCanvasTkAgg(fig, master=report_window)
        canvas.draw()
        canvas.get_tk_widget().pack()

        # Сохранение графика в файл
        fig.savefig(settings.data_dir / 'forecast_grid_sales_report.png')

        # Создание отчета в текстовый файл
        with open(settings.data_dir / 'forecast_grid_sales_report.txt', 'w', encoding='utf-8') as file:
            file.write("Отчет с прогнозом продаж металлических сеток на следующие " + str(months) + " месяцев:\n")
            file.write(df_forecast.to_string(index=False))

        # Вывод сообщения об успешном сохранении отчета в новом окне
        info_textbox = customtkinter.CTkTextbox(report_window, height=600, width=500)
        info_textbox.pack()
        info_textbox.insert("end", "Отчет с прогнозом продаж металлических сеток сохранен в файл forecast_grid_sales_report.txt\n")
        info_textbox.insert("end", "Средняя абсолютная ошибка MAE: " + str(mae) + "\n")
        info_textbox.insert("end", "Отчет с прогнозом продаж металлических сеток на следующие " + str(months) + " месяцев:\n")
        info_textbox.insert("end", df_forecast.to_string(index=False))


customtkinter.set_appearance_mode('dark')
customtkinter.set_default_color_theme('dark-blue')

# Окно приложения
root = customtkinter.CTk()
root.title("Приложение для анализа и прогнозирования продаж")

# Размер окна
root.geometry("1200x800")

# Лейбл
label = customtkinter.CTkLabel(root, text='Приложение для анализа и прогнозирования продаж организации')
label.pack(pady=20)

# Текстбокс
info_textbox = customtkinter.CTkTextbox(root, height=50, width=400)
info_textbox.pack(pady=20)
info_textbox.insert("end", data.connection_state)
info_textbox.insert("end", "\nВыберите необходимый отчёт:")

# Поля для выбора отчётов
report_selection_menu = customtkinter.CTkOptionMenu(root, values=["Отчёт о выручке", "Отчёт о продажах", "Отчёт по категориям"], command=update_selected_report)
report_selection_menu.pack(pady=10)
report_selection_menu.set("Тип отчёта")

months_selection_menu = customtkinter.CTkOptionMenu(root, values=["3", "6", "12"], command=update_selected_months)
months_selection_menu.pack(pady=10)
months_selection_menu.set("Количество месяцев")

# Кнопка подтверждения отчёта
report_selection_button = customtkinter.CTkButton(root, text="Сгенерировать отчет", command=handle_report_selection)
report_selection_button.pack(pady=10)

root.mainloop()
