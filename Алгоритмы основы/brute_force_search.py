import time

# очищение текста, понижение регистра
def text(fname):
    with open(fname, 'r') as file:
        text = file.read()
    words = text.split()
    norm_words = []

    for i in words:
        if i.isalpha():
            i = i.lower()
            norm_words.append(i)

    return norm_words


def search(words, target):
    begin_time = time.time()
    count = 0
    cycle = 0

    for i in words:
        if i == target:
            count += 1
        cycle += 1

    end_time = time.time()
    timer = end_time - begin_time

    return count, timer, cycle


class worddata:
    def __init__(self, word, count, time_spent, cycle):
        self.word = word
        self.count = count
        self.time_spent = time_spent
        self.cycle = cycle


fname = '/Users/darius/VS code/ kapitanskaya-dochka.txt'
words = text(fname)
target = set(words)  # Все уникальные слова в тексте

word_data_list = []

begin_time = time.time()

for i in list(target):
    counts, time_spent, cycle = search(words, i)
    time_spent_sec = "{:.6f}".format(time_spent)
    word_data = worddata(i, counts, time_spent_sec, cycle)
    word_data_list.append(word_data)

end_time = time.time()

avg_time = end_time - begin_time
avg_time_sec = "{:.6f}".format(avg_time)

print("Average time: ", avg_time_sec)

sorted_word_data = sorted(word_data_list, key=lambda x: x.count, reverse=True)

print("{:<15} {:<10} {:<15} {:<15}".format("Word", "Count", "Time Spent", "Cycles"))
print("=" * 40)

for word_data in sorted_word_data:
    print("{:<15} {:<10} {:<15} {:<15}".format(
        word_data.word,
        word_data.count,
        word_data.time_spent,
        word_data.cycle
    ))