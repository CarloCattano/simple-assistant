def add_two_numbers(a: int, b: int) -> int:
    return a + b

tool = {
    'name': 'add_two_numbers',
    'function': add_two_numbers,
    'triggers': ['add', 'sum', 'plus'],
    'description': 'Add two integers and return the sum.',
    'parameters': {
        'a': {'type': 'integer', 'description': 'First addend'},
        'b': {'type': 'integer', 'description': 'Second addend'},
    },
}
