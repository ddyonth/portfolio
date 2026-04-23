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

# Создание массива с случайными числами
n = 1000
randomlist = [random.randint(-10000, 10000) for _ in range(n)]

# Вывод гномьей сортировки
time_spent, steps, comparisons = gnome_sort(randomlist)
time_spent_sec = "{:.6f}".format(time_spent)

print("Время, затраченное на выполнение сортировки, составляет: ", time_spent_sec, " секунд")
print("Количество выполненных перестановок: ", steps)
print("Количество выполненных сравнений: ", comparisons)