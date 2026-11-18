import pygame
from config import TILE_SIZE, HUD_HEIGHT, WINDOW_MARGIN, MOVE_INTERVAL
from game.model import Maze
from game.simulation import Simulation
from game.rendering import window_size, draw_maze, draw_pacman, draw_hud
from algorithms.base import ManualController
from algorithms.bfs import NearestPelletBFS
from maps.custom_map import (
    ROWS,
    START,
    PELLETS,
    TUNNELS,
    RANDOM_GENERATION,
    RANDOM_WIDTH,
    RANDOM_HEIGHT,
    RANDOM_CORRIDOR_FRACTION,
    RANDOM_MIN_EDGES,
    RANDOM_MIN_AVERAGE_DEGREE,
    RANDOM_SEED,
    RANDOM_PELLET_FRACTION,
)
from maps.generation import generate_connected_maze
import random


class PacmanApp:
    def __init__(self):
        if RANDOM_GENERATION:
            self.maze = generate_connected_maze(
                RANDOM_WIDTH,
                RANDOM_HEIGHT,
                RANDOM_CORRIDOR_FRACTION,
                RANDOM_MIN_EDGES,
                RANDOM_MIN_AVERAGE_DEGREE,
                RANDOM_SEED,
            )
            positions = sorted(
                self.maze.corridor_positions(), key=lambda p: (p[1], p[0])
            )
            start = positions[0]
            candidates = positions[1:]
            count = (
                max(1, round(len(candidates) * RANDOM_PELLET_FRACTION))
                if candidates
                else 0
            )
            pellets = set(random.Random(RANDOM_SEED + 1).sample(candidates, count))
            self.sim = Simulation(self.maze, start, pellets, MOVE_INTERVAL)
        else:
            self.maze = Maze.from_rows(ROWS, TUNNELS)
            self.sim = Simulation(self.maze, START, PELLETS, MOVE_INTERVAL)
        self.manual = ManualController()
        self.algorithm = NearestPelletBFS()
        self.algorithm_mode = False
        self.direction = "RIGHT"
        self.anim_time = 0
        self.running = True
        self.screen = pygame.display.set_mode(window_size(self.maze))
        self.font = pygame.font.SysFont("arial", 22, bold=True)
        self.small = pygame.font.SysFont("arial", 15)
        self.offset = (WINDOW_MARGIN, WINDOW_MARGIN + HUD_HEIGHT)

    def handle_events(self, events):
        keys = {
            pygame.K_UP: "UP",
            pygame.K_w: "UP",
            pygame.K_DOWN: "DOWN",
            pygame.K_s: "DOWN",
            pygame.K_LEFT: "LEFT",
            pygame.K_a: "LEFT",
            pygame.K_RIGHT: "RIGHT",
            pygame.K_d: "RIGHT",
        }
        for e in events:
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.running = False
                elif e.key == pygame.K_r:
                    self.sim.reset()
                    self.direction = "RIGHT"
                elif e.key == pygame.K_m:
                    self.algorithm_mode = not self.algorithm_mode
                elif e.key in keys and not self.algorithm_mode:
                    self.manual.set_action(keys[e.key])

    def update(self, dt):
        self.anim_time += dt
        controller = self.algorithm if self.algorithm_mode else self.manual
        self.sim.advance(dt, controller.choose_action, is_algorithm=self.algorithm_mode)
        if self.sim.last_action in ("UP", "DOWN", "LEFT", "RIGHT"):
            self.direction = self.sim.last_action

    def draw(self):
        draw_maze(self.screen, self.maze, self.sim.state.pellets, self.offset)
        draw_pacman(
            self.screen,
            self.sim.interpolated_position(),
            self.direction,
            self.anim_time,
            self.offset,
        )
        draw_hud(
            self.screen,
            self.font,
            self.small,
            self.sim,
            "ALGORITHM" if self.algorithm_mode else "MANUAL",
            self.algorithm.name if self.algorithm_mode else "Keyboard",
        )
        pygame.display.flip()
