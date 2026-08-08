def to_roman(n):
    val = [
        1000, 900, 500, 400,
        100, 90, 50, 40,
        10, 9, 5, 4,
        1
    ]
    syms = [
        "M", "CM", "D", "CD",
        "C", "XC", "L", "XL",
        "X", "IX", "V", "IV",
        "I"
    ]
    roman_numeral = ''
    i = 0
    while n > 0:
        for _ in range(n // val[i]):
            roman_numeral += syms[i]
            n -= val[i]
        i += 1
    return roman_numeral

# Example usage
print(to_roman(42))  # Output: XLII