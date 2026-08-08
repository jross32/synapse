import re

def word_count(text):
    # Split text into words using regex to handle punctuation
    words = re.findall(r'\b\w+\b', text.lower())
    # Count occurrences of each word
    return {word: words.count(word) for word in set(words)}

# Test the function with various inputs
def test_word_count():
    assert word_count("Hello, world!") == {'hello': 1, 'world': 1}
    assert word_count("This is a test. This test is only a test.") == {
        'this': 2,
        'is': 2,
        'a': 2,
        'test': 3
    }
    assert word_count("") == {}
    assert word_count("   Leading and trailing spaces   ") == {'leading': 1, 'and': 1, 'trailing': 1}
    assert word_count("Punctuation! Should be ignored.") == {
        'punctuation': 1,
        'should': 1,
        'be': 1,
        'ignored': 1
    }
    print('OK')

# Run the tests
test_word_count()