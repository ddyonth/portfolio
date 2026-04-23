import time

def search(words, target):
    begin_time = time.time()
    count = 0
    cycle = 0

    left = 0
    right = len(words) - 1

    while left <= right:
        cycle += 1
        mid = (left + right) // 2

        if words[mid] == target:
            count += 1

            # совпадения слева
            i = mid - 1
            while i >= 0 and words[i] == target:
                cycle += 1
                count += 1
                i -= 1

            # совпадения справа
            i = mid + 1
            while i < len(words) and words[i] == target:
                cycle += 1
                count += 1
                i += 1

            break

        elif target > words[mid]:
            left = mid + 1
        else:
            right = mid - 1

    end_time = time.time()
    timer = end_time - begin_time

    return count, timer, cycle