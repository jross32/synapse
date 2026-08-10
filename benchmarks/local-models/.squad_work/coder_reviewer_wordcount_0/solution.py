def word_count(text):
    import string

    # Remove punctuation from each word and convert to lowercase
    words = [word.strip(string.punctuation).lower() for word in text.split()]

    # Count the occurrences of each word
    word_dict = {}
    for word in words:
        if word:
            word_dict[word] = word_dict.get(word, 0) + 1

    return word_dict