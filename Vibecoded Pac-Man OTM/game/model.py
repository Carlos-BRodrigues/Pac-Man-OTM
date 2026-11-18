from dataclasses import dataclass
from enum import IntEnum


class Tile(IntEnum):
    VOID = 0
    WALL = 1
    CORRIDOR = 2


DIRECTIONS = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}


@dataclass(frozen=True)
class Maze:
    grid: tuple
    tunnels: tuple = ()

    @classmethod
    def from_rows(cls, rows, tunnels=()):
        raw = [list(map(int, row)) for row in rows]
        if not raw or not max(map(len, raw)):
            raise ValueError("Maze cannot be empty")
        w = max(map(len, raw))
        for row in raw:
            if any(v not in (0, 1, 2) for v in row):
                raise ValueError("Tile values: 0, 1, 2 only")
            row.extend([0] * (w - len(row)))
        obj = cls(tuple(tuple(row) for row in raw), tuple(tuple(p) for p in tunnels))
        obj.validate()
        return obj

    @property
    def width(self):
        return len(self.grid[0])

    @property
    def height(self):
        return len(self.grid)

    def in_bounds(self, p):
        x, y = p
        return 0 <= x < self.width and 0 <= y < self.height

    def is_corridor(self, p):
        return self.in_bounds(p) and self.grid[p[1]][p[0]] == 2

    def tunnel_lookup(self):
        d = {}
        for a, b in self.tunnels:
            d[a] = b
            d[b] = a
        return d

    def tunnel_exit_action(self, p):
        q = self.tunnel_lookup().get(p)
        if q is None:
            return None
        x, y = p
        qx, qy = q
        if y == qy and x == 0 and qx == self.width - 1:
            return "LEFT"
        if y == qy and x == self.width - 1 and qx == 0:
            return "RIGHT"
        if x == qx and y == 0 and qy == self.height - 1:
            return "UP"
        if x == qx and y == self.height - 1 and qy == 0:
            return "DOWN"
        return None

    def action_between(self, p, q):
        dx, dy = q[0] - p[0], q[1] - p[1]
        direct = {(0, -1): "UP", (0, 1): "DOWN", (-1, 0): "LEFT", (1, 0): "RIGHT"}.get(
            (dx, dy)
        )
        if direct is not None:
            return direct
        if self.tunnel_lookup().get(p) == q:
            return self.tunnel_exit_action(p)
        raise ValueError(f"No single movement action connects {p} to {q}")

    def neighbors(self, p):
        if not self.is_corridor(p):
            return ()
        x, y = p
        out = [
            (x + dx, y + dy)
            for dx, dy in DIRECTIONS.values()
            if self.is_corridor((x + dx, y + dy))
        ]
        q = self.tunnel_lookup().get(p)
        if q is not None and q not in out:
            out.append(q)
        return tuple(out)

    def corridor_positions(self):
        return tuple(
            (x, y)
            for y, row in enumerate(self.grid)
            for x, v in enumerate(row)
            if v == 2
        )

    def edges(self):
        return {
            tuple(sorted((p, q)))
            for p in self.corridor_positions()
            for q in self.neighbors(p)
        }

    def average_degree(self):
        n = len(self.corridor_positions())
        return 2 * len(self.edges()) / n if n else 0.0

    def connected(self):
        nodes = set(self.corridor_positions())
        if not nodes:
            return False
        seen = {next(iter(nodes))}
        stack = list(seen)
        while stack:
            for q in self.neighbors(stack.pop()):
                if q not in seen:
                    seen.add(q)
                    stack.append(q)
        return seen == nodes

    def validate(self):
        lookup = {}
        for a, b in self.tunnels:
            if not self.is_corridor(a) or not self.is_corridor(b):
                raise ValueError("Tunnel endpoints must be corridors")
            ax, ay = a
            bx, by = b
            lr = ay == by and {ax, bx} == {0, self.width - 1}
            tb = ax == bx and {ay, by} == {0, self.height - 1}
            if not (lr or tb):
                raise ValueError(
                    "Tunnel endpoints must be opposite edges, same row/column"
                )
            if a in lookup or b in lookup:
                raise ValueError("Tunnel endpoints must belong to only one pair")
            lookup[a] = b
            lookup[b] = a
        return self
