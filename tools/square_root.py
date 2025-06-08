def square_root(a: float) -> float:
    return float(a) ** 0.5

tool = {
    'function': square_root,
    'triggers': ['square root', 'sqrt', 'root'],
}
