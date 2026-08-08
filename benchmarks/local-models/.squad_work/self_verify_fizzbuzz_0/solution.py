def fizzbuzz(n):
    return [str(i) if i % 3 != 0 and i % 5 != 0 else 'Fizz' if i % 3 == 0 else 'Buzz' if i % 5 == 0 else 'FizzBuzz' for i in range(1, n+1)]