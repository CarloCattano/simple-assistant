def square_root(a: float) -> float:
    print(f"Calculating the square root of {a}")
    return float(a) ** 0.5

tool = {
    'name': 'square_root',
    'function': square_root,
    'triggers': ['square root', 'sqrt', 'root'],
    'description': 'Compute the square root of a number.',
    'parameters': {
        'a': {'type': 'number', 'description': 'The number to compute the square root of'},
    },
}
