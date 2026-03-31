# Test file for review
def add_numbers(a, b):
    return a + b

def divide_numbers(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

def unused_function():
    x = 1
    y = 2
    return x + y

if __name__ == "__main__":
    result = add_numbers(5, 10)
    print(f"Result: {result}")
    
    # This will cause an error
    try:
        divide_result = divide_numbers(5, 0)
        print(f"Divide Result: {divide_result}")
    except ValueError as e:
        print(f"Error: {e}")