import random
import time

def bubble_sort(arr):
    begin_time = time.time() 
    n = len(arr)
    steps = 0
    comparisons = 0

    for i in range(n - 1):
        for j in range(n - i - 1):
            comparisons += 1
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                steps += 1

    end_time = time.time()
    timer = end_time - begin_time
    return timer, steps, comparisons
 
n = 5000
randomlist = [random.randint(-10000, 10000) for _ in range(n)]

time_spent, steps, comparisons = bubble_sort(randomlist)

time_spent_sec = "{:.6f}".format(time_spent)

print("Время, затраченное на выполнение сортировки, составляет: ", time_spent_sec, " секунд")
print("Количество выполненных перестановок: ", steps)
print("Количество выполненных сравнений: ", comparisons)