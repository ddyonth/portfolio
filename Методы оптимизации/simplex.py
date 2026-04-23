import numpy as np
from fractions import Fraction

def to_fractions(data):
    # преобразует данные в дроби с наименьшими знаменателями
    return np.array([[Fraction(x).limit_denominator() for x in row] for row in data])


def initialize_tableau():
    # создает начальную таблицу для симплекс-метода
    data = [
        [6, 4, 1, 8, 8, 27],
        [-7, 4, -1, 0, 7, 3],
        [9, 6, 7, 3, 1, 26],
        [1, -3, 8, -6, 2, 0],  # целевая функция l
        [-8, -14, -7, -11, -16, -56]  # целевая функция l1
    ]
    index = ['y1', 'y2', 'y3', 'l', 'l1']
    columns = ['x1', 'x2', 'x3', 'x4', 'x5', '=']
    return index, columns, to_fractions(data)


def print_table(index, columns, tableau):
    # выводит текущую таблицу симплекс-метода в читаемом виде
    header = "\t".join([""] + columns)
    print(header)
    for idx, row in zip(index, tableau):
        print("\t".join([idx] + [str(x) for x in row]))


def perform_pivot(index, columns, tableau, razr_row, razr_col):
    # выполняет операцию разрешающего элемента для симплекс-метода
    razr_value = tableau[razr_row, razr_col]
    
    # нормализуем разрешающую строку, делим ее на разрешающий элемент
    tableau[razr_row] = tableau[razr_row] / razr_value

    # обновляем остальные строки таблицы с учетом новой разрешающей строки
    for i in range(len(tableau)):
        if i != razr_row:  # не изменяем разрешающую строку
            factor = tableau[i, razr_col]
            tableau[i] -= factor * tableau[razr_row]

    return index, columns, tableau


def apply_simplex():
    # основной процесс решения задачи с помощью симплекс-метода
    index, columns, tableau = initialize_tableau()
    print("исходная таблица:")
    print_table(index, columns, tableau)

    iteration = 0
    previous_pivots = set()  # защита от зацикливания

    # начинаем работать сначала с l1, а потом с l
    while True:
        # проверяем строку l1 на наличие отрицательных значений
        if any(x < 0 for x in tableau[-1, :-1]):
            print(f"шаг {iteration} для l1:")
            print_table(index, columns, tableau)

            # находим разрешающий столбец для l1 (столбец с минимальным значением)
            razr_col = np.argmin(tableau[-1, :-1])
            print(f"выбран разрешающий столбец для l1: {columns[razr_col]}")

            # находим разрешающую строку
            ratios = []
            for i in range(len(tableau) - 2):  # исключаем строки l и l1
                if tableau[i, razr_col] > 0:
                    ratios.append((tableau[i, -1] / tableau[i, razr_col], i))
                else:
                    ratios.append((float('inf'), i))

            if all(r[0] == float('inf') for r in ratios):  # если все отношения бесконечны
                raise Exception("задача неограничена.")

            # выбираем разрешающую строку с минимальным отношением
            razr_row = min(ratios, key=lambda x: x[0])[1]
            print(f"выбрана разрешающая строка для l1: {index[razr_row]}")

            # проверка на зацикливание
            if (razr_row, razr_col) in previous_pivots:
                print(f"такая позиция уже использовалась: ({index[razr_row]}, {columns[razr_col]})")
                raise Exception("симплекс-метод зациклился. проверьте постановку задачи.")
            previous_pivots.add((razr_row, razr_col))

            # выполняем операцию разрешающего элемента
            index, columns, tableau = perform_pivot(index, columns, tableau, razr_row, razr_col)

            # обновляем базисную переменную (название строки)
            if index[razr_row] not in ['l', 'l1']:
                index[razr_row] = columns[razr_col]

            iteration += 1
        else:
            # если с l1 все завершено, начинаем работу с l
            print(f"шаг {iteration} для l:")
            print_table(index, columns, tableau)

            # находим разрешающий столбец для l (столбец с минимальным значением)
            razr_col = np.argmin(tableau[-2, :-1])
            print(f"выбран разрешающий столбец для l: {columns[razr_col]}")

            # находим разрешающую строку
            ratios = []
            for i in range(len(tableau) - 2):  # исключаем строки l и l1
                if tableau[i, razr_col] > 0:
                    ratios.append((tableau[i, -1] / tableau[i, razr_col], i))
                else:
                    ratios.append((float('inf'), i))

            if all(r[0] == float('inf') for r in ratios):  # если все отношения бесконечны
                raise Exception("задача неограничена.")

            # выбираем разрешающую строку с минимальным отношением
            razr_row = min(ratios, key=lambda x: x[0])[1]
            print(f"выбрана разрешающая строка для l: {index[razr_row]}")

            # проверка на зацикливание
            if (razr_row, razr_col) in previous_pivots:
                print(f"такая позиция уже использовалась: ({index[razr_row]}, {columns[razr_col]})")
                raise Exception("симплекс-метод зациклился. проверьте постановку задачи.")
            previous_pivots.add((razr_row, razr_col))

            # выполняем операцию разрешающего элемента для l
            index, columns, tableau = perform_pivot(index, columns, tableau, razr_row, razr_col)

            # обновляем базисную переменную (название строки)
            if index[razr_row] not in ['l', 'l1']:
                index[razr_row] = columns[razr_col]

            iteration += 1

        # проверяем завершение работы для обеих целевых функций
        if all(x >= 0 for x in tableau[-1, :-1]) and all(x >= 0 for x in tableau[-2, :-1]):
            print("финальная таблица:")
            print_table(index, columns, tableau)
            break

    # находим оптимальное решение
    optimal_values = {}
    for i, row_name in enumerate(index[:-2]):  # исключаем строки l и l1
        if row_name not in ['l', 'l1']:
            column_index = columns.index(row_name)
            optimal_values[columns[column_index]] = tableau[i, -1]
    
    # выводим оптимальные координаты
    print("оптимальная точка:")
    for var, value in optimal_values.items():
        print(f"{var} = {float(value):.2f}")

    # вычисляем значение целевой функции
    optimal_value = tableau[-2, -1]
    print(f"значение функции l в оптимальной точке: {float(optimal_value):.2f}")

# вызов функции для выполнения симплекс-метода
apply_simplex()