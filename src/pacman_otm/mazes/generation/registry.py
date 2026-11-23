"""Names used in recipes -> shape and topography implementations."""

from pacman_otm.mazes.generation.lattice import LatticeParams, generate_lattice
from pacman_otm.mazes.generation.shapes import SHAPES

# generator name -> (parameter dataclass, generate(region, params, rules, rng) -> grid)
GENERATORS = frozendict(
    {
        "lattice": (LatticeParams, generate_lattice),
    }
)

__all__ = ["GENERATORS", "SHAPES"]
