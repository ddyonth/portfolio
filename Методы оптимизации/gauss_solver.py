# гаусс для системы. возвращает список значений переменных
def gauss_elimination(matrix, results):
    n = len(matrix)

    # прямой ход. упрощение системы уравнений до треугольного вида чтобы ниже главной диагонали были нули
    for i in range(n):
        # главный элемент в столбце
        max_row = i
        for k in range(i + 1, n):
            if abs(matrix[k][i]) > abs(matrix[max_row][i]):
                max_row = k

        # поменять строки местами
        matrix[i], matrix[max_row] = matrix[max_row], matrix[i]
        results[i], results[max_row] = results[max_row], results[i]

        # нормализация строки так чтобы ведущий элемент стал = 1
        divisor = matrix[i][i]
        if divisor == 0:
            return None  # если / на ноль — нет решения
        matrix[i] = [m / divisor for m in matrix[i]]
        results[i] /= divisor

        # исключение переменной из следующих строк
        for k in range(i + 1, n):
            factor = matrix[k][i]
            matrix[k] = [m2 - factor * m1 for m1, m2 in zip(matrix[i], matrix[k])]
            results[k] -= factor * results[i]

    # обратный ход. определение значений переменных начиная с последней и двигаясь вверх
    solution = [0] * n
    for i in range(n - 1, -1, -1):
        solution[i] = results[i] - sum(matrix[i][j] * solution[j] for j in range(i + 1, n))

    return solution

# целевая функция
def objective(x1, x2, x3, x4, x5):
    return -1 * x1 + 3 * x2 - 8 * x3 + 6 * x4 - 2 * x5

# поиск всех решений
def find_all_solutions():
    variables = ['x1', 'x2', 'x3', 'x4', 'x5']
    feasible_solutions = []
    infeasible_solutions = []
    max_value = None
    optimal_solution = None

    # перебор всех возможных комбинацй 2 переменных = 0
    for i in range(len(variables)):
        for j in range(i + 1, len(variables)):
            # копии ограничений для текущей комбинации
            matrix = [
                [6, 4, 1, 8, 8],
                [-7, 4, -1, 0, 7],
                [9, 6, 7, 3, 1]
            ]
            results = [27, 3, 26]

            # задаем 2 переменные = 0
            matrix = [row[:i] + row[i + 1:j] + row[j + 1:] for row in matrix]
            variables_copy = [var for idx, var in enumerate(variables) if idx != i and idx != j]

            # решаем систему для оставшихся переменных
            solution = gauss_elimination(matrix, results)
            if solution:
                # добавляем 0 для фиксированных переменных
                full_solution = [0] * 5
                idx = 0
                for k in range(5):
                    if k != i and k != j:
                        full_solution[k] = solution[idx]
                        idx += 1

                # проверка допустимости решения
                if all(value >= 0 for value in full_solution):
                    # значение целевой функции
                    L_value = objective(*full_solution)
                    # допустимая точка
                    feasible_solutions.append((full_solution, L_value))

                    # максимальное значение целевой функции
                    if max_value is None or L_value > max_value:
                        max_value = L_value
                        optimal_solution = full_solution
                else:
                    # недопустимая
                    infeasible_solutions.append(full_solution)

    return feasible_solutions, infeasible_solutions, optimal_solution, max_value

# вызов функции поиск решений
feasible_solutions, infeasible_solutions, optimal_solution, max_value = find_all_solutions()

# вывод допустимых
if feasible_solutions:
    print("Допустимые точки:")
    for idx, (solution, L_value) in enumerate(feasible_solutions):
        solution_str = ", ".join(f"{val:.4f}" for val in solution)
        print(f"A{idx + 1} ({solution_str})")

# вывед недопустимызх
if infeasible_solutions:
    print("\nНедопустимые точки:")
    for idx, solution in enumerate(infeasible_solutions):
        solution_str = ", ".join(f"{val:.4f}" for val in solution)
        print(f"B{idx + 1} ({solution_str})")

# оптимальное решение
if optimal_solution:
    print("\nОптимальное решение:")
    solution_str = ", ".join(f"{val:.4f}" for val in optimal_solution)
    print(f"Оптимальная точка: ({solution_str})")
    print(f"Максимальное значение целевой функции L = {max_value:.4f}")
else:
    print("Допустимых решений не найдено.")