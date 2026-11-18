import random as r

# Tile codes: 0=void, 1=wall, 2=corridor. Rows top-to-bottom.
ROWS = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 2, 2, 2, 1, 2, 2, 2, 2, 2, 1],
    [1, 2, 1, 2, 1, 2, 1, 1, 1, 2, 1],
    [1, 2, 1, 2, 2, 2, 2, 2, 1, 2, 1],
    [1, 2, 1, 1, 1, 2, 1, 2, 1, 2, 1],
    [1, 2, 2, 2, 2, 2, 1, 2, 2, 2, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
]
START = (1, 1)
PELLETS = {
    (2, 1),
    (3, 1),
    (5, 1),
    (6, 1),
    (7, 1),
    (8, 1),
    (9, 1),
    (1, 2),
    (3, 2),
    (5, 2),
    (9, 2),
    (1, 3),
    (3, 3),
    (4, 3),
    (5, 3),
    (6, 3),
    (7, 3),
    (9, 3),
    (1, 4),
    (5, 4),
    (7, 4),
    (9, 4),
    (1, 5),
    (2, 5),
    (3, 5),
    (4, 5),
    (5, 5),
    (7, 5),
    (8, 5),
    (9, 5),
}
TUNNELS = []

# Optional random-map mode. Set to True to use the connected graph generator.
"""RANDOM_GENERATION = False
RANDOM_WIDTH = 20
RANDOM_HEIGHT = 15
RANDOM_CORRIDOR_FRACTION = 0.55
RANDOM_MIN_EDGES = 180
RANDOM_MIN_AVERAGE_DEGREE = 1.8
RANDOM_SEED = 42
RANDOM_PELLET_FRACTION = 0.25"""

RANDOM_GENERATION = True
RANDOM_WIDTH = 30
RANDOM_HEIGHT = 15
RANDOM_CORRIDOR_FRACTION = 0.55
RANDOM_MIN_EDGES = 180
RANDOM_MIN_AVERAGE_DEGREE = 1.5
RANDOM_SEED = r.randint(0, 255)
RANDOM_PELLET_FRACTION = 0.25
