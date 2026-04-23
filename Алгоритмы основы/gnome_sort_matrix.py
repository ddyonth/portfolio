import random
import time

def gnome_sort(arr):
    begin_time = time.time()
    index = 0
    n = len(arr)
    steps = 0
    comparisons = 0

    while index < n:
        comparisons += 1
        if index == 0:
            index += 1
        if arr[index] >= arr[index - 1]:
            index += 1
        else:
            arr[index], arr[index - 1] = arr[index - 1], arr[index]
            index -= 1
            steps += 1

    end_time = time.time()
    timer = end_time - begin_time
    return timer, steps, comparisons

def generate_matrix(rows, columns, min = -10000, max = 10000):
    matrix = [[random.randint(min, max) for _ in range(columns)] for _ in range(rows)]
    return matrix

def g_sort_matrix(matrix):
    total_steps = 0
    total_time = 0
    total_comparisons = 0

    for row in matrix:
        time_taken, steps, comparisons = gnome_sort(row)
        total_time += time_taken
        total_steps += steps
        total_comparisons += comparisons

    num_rows = len(matrix)
    num_columns = len(matrix[0])

    for col_idx in range(num_columns):
        current_column = []
        for row_idx in range(num_rows):
            current_column.append(matrix[row_idx][col_idx])

        time_taken, steps, comparisons = gnome_sort(current_column)
        total_time += time_taken
        total_steps += steps
        total_comparisons += comparisons

    return total_time, total_steps, total_comparisons

randommatrix = generate_matrix(75, 75)

time_spent, steps, comparisons = g_sort_matrix(randommatrix)

time_spent_sec = "{:.6f}".format(time_spent)

print("Время, затраченное на выполнение сортировки, составляет: ", time_spent_sec, " секунд")
print("Количество выполненных перестановок: ", steps)
print("Количество выполненных сравнений: ", comparisons)