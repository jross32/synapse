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

def test_to_roman():
    assert to_roman(1) == 'I'
    assert to_roman(4) == 'IV'
    assert to_roman(9) == 'IX'
    assert to_roman(58) == 'LVIII'
    assert to_roman(1994) == 'MCMXCIV'
    assert to_roman(3999) == 'MMMCMXCIX'
    print('OK')

test_to_roman()