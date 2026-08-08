import re

def word_count(text):
    words = re.findall(r'\b\w+\b', text.lower())
    return {word: words.count(word) for word in set(words)}