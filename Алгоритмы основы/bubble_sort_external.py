import random
import time

def generate_random(filename, n):
    with open(filename, 'w') as f:
        for _ in range(n):
            f.write(str(random.randint(-10000, 10000)) + "\n")

def read_f(filename):
    with open(filename, 'r') as f:
        return [int(line.strip()) for line in f.readlines()]

def write_f(filename, a):
    with open(filename, 'w') as f:
        for item in a:
            f.write(str(item) + "\n")

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
    return arr, timer, steps, comparisons 

generate_random("file1.txt", 2500)
generate_random("file2.txt", 2500)

f1 = read_f("file1.txt")
f2 = read_f("file2.txt")

union = list(set(f1).union(set(f2)))
intersection = list(set(f1).intersection(set(f2)))
difference = list(set(f1).difference(set(f2)))
symm_difference = list(set(f1).symmetric_difference(set(f2)))

sorted_union, u_time_spent, u_steps, u_comparisons = bubble_sort(union)
sorted_intersection, i_time_spent, i_steps, i_comparisons = bubble_sort(intersection)
sorted_difference, d_time_spent, d_steps, d_comparisons = bubble_sort(difference)
sorted_s_difference, s_time_spent, s_steps, s_comparisons = bubble_sort(symm_difference)

write_f("sorted_union.txt", sorted_union)
write_f("sorted_intersection.txt", sorted_intersection)
write_f("sorted_difference.txt", sorted_difference)
write_f("sorted_s_difference.txt", sorted_s_difference)