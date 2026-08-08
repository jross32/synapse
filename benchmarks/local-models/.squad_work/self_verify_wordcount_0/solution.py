def word_count(text):
    return {word.lower(): text.count(word) for word in text.split() if word.isalpha()}