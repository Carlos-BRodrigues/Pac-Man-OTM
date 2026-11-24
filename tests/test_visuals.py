import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from pacman_otm.controllers.registry import create_controller_registry
from pacman_otm.mazes.layout import parse_layout
from pacman_otm.mazes.registry import resolve_maze
from pacman_otm.simulation.actions import Action
from pacman_otm.simulation.engine import SimulationEngine
from pacman_otm.simulation.frame import SimulationFrame
from pacman_otm.simulation.replay import ReplayPlayer
from pacman_otm.simulation.runner import run_simulation
from pacman_otm.visualization.animation import (
    CAUGHT_REASON,
    INITIAL_POSE,
    PlayerPose,
    poses_for_states,
    step_poses,
)
from pacman_otm.visualization.live import LivePygameVisualizer
from pacman_otm.visualization.maze_art import dilate, open_pixel_mask, wall_outline_mask
from pacman_otm.visualization.pygame_renderer import PygameRenderer
from pacman_otm.visualization.replay import ReplayPygameVisualizer
from pacman_otm.visualization.sprites import (
    DEATH_FRAMES,
    Mouth,
    SpriteSet,
    death_masks,
    player_mask,
)
from pacman_otm.visualization.theme import DEFAULT_THEME as THEME

BLOCK_LAYOUT = (
    "#######\n"
    "#P....#\n"
    "#.###.#\n"
    "#.###.#\n"
    "#.....#\n"
    "#######\n"
)


@pytest.fixture(autouse=True)
def pygame_session():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _run(maze_name: str, controller: str = "nearest-pellet"):
    maze = resolve_maze(maze_name)
    return run_simulation(
        engine=SimulationEngine(maze),
        controller=create_controller_registry().create(controller, maze, 1),
        max_steps=300,
    )


# Maze art

@pytest.mark.parametrize("maze_name", ["small", "classic"])
def test_outlines_keep_the_recess(maze_name: str) -> None:
    maze = resolve_maze(maze_name)
    outline = wall_outline_mask(maze, THEME)
    near_open = dilate(open_pixel_mask(maze, THEME), THEME.wall_recess)

    assert outline.any()
    assert not (outline & near_open).any()


def test_no_outline_along_the_grid_edge() -> None:
    outline = wall_outline_mask(parse_layout(BLOCK_LAYOUT, "block"), THEME)

    assert not outline[0].any() and not outline[-1].any()
    assert not outline[:, 0].any() and not outline[:, -1].any()


def test_wall_block_outline_has_rounded_corners() -> None:
    outline = wall_outline_mask(parse_layout(BLOCK_LAYOUT, "block"), THEME)

    # The inner 3x2-tile block lies in tiles rows 2-3, cols 2-4.
    tile = THEME.tile
    block = outline[2 * tile:4 * tile, 2 * tile:5 * tile]
    rows, cols = np.nonzero(block)
    top, bottom, left, right = rows.min(), rows.max(), cols.min(), cols.max()

    assert block[top, (left + right) // 2] and block[bottom, (left + right) // 2]
    for corner in ((top, left), (top, right), (bottom, left), (bottom, right)):
        assert not block[corner]


def test_maze_art_is_deterministic() -> None:
    maze = resolve_maze("classic")
    assert np.array_equal(wall_outline_mask(maze, THEME), wall_outline_mask(maze, THEME))


# Sprites

def test_sprite_set_sizes() -> None:
    sprites = SpriteSet(THEME, scale=2)
    size = THEME.sprite * 2

    assert len(sprites.movement) == 9
    assert len(sprites.death) == DEATH_FRAMES == len(death_masks(THEME.sprite))
    for surface in [*sprites.movement.values(), *sprites.death]:
        assert surface.get_size() == (size, size)


def test_directional_sprites_are_rotations() -> None:
    size = THEME.sprite
    closed = {player_mask(Mouth.CLOSED, facing, size).tobytes() for facing in Action}
    assert len(closed) == 1

    for mouth in (Mouth.HALF, Mouth.WIDE):
        right = player_mask(mouth, Action.RIGHT, size)
        assert np.array_equal(player_mask(mouth, Action.LEFT, size), np.fliplr(right))
        assert np.array_equal(player_mask(mouth, Action.UP, size), np.rot90(right, 1))
        assert np.array_equal(player_mask(mouth, Action.DOWN, size), np.rot90(right, -1))
        assert not np.array_equal(right, player_mask(Mouth.CLOSED, Action.RIGHT, size))


# Animation

def test_chomp_loop_order_and_facing() -> None:
    poses = step_poses(INITIAL_POSE, (5, 5), (4, 5), subframes=4)

    assert [pose.mouth for pose in poses] == [Mouth.HALF, Mouth.WIDE, Mouth.HALF, Mouth.CLOSED]
    assert all(pose.facing == Action.UP for pose in poses)


def test_stopped_player_can_freeze_on_any_shape() -> None:
    # Walk tile by tile; the shape at each tile centre must vary, so stopping
    # against a wall does not always show the closed shape.
    pose = INITIAL_POSE
    shapes_at_tile_centres = set()

    for col in range(10, 2, -1):
        pose = step_poses(pose, (1, col), (1, col - 1))[-1]
        shapes_at_tile_centres.add(pose.mouth)
        assert step_poses(pose, (1, col - 1), (1, col - 1))[-1] == pose

    assert shapes_at_tile_centres == {Mouth.CLOSED, Mouth.HALF, Mouth.WIDE}


def test_blocked_player_freezes_and_keeps_facing() -> None:
    moving = step_poses(INITIAL_POSE, (5, 5), (5, 6))[1]
    frozen = step_poses(moving, (5, 6), (5, 6))

    assert frozen == [moving] * len(frozen)
    assert moving == PlayerPose(facing=Action.RIGHT, chomp_step=2)
    assert moving.mouth == Mouth.WIDE


def test_poses_for_states_matches_stepwise_feeding() -> None:
    result = _run("small", "random-walk")
    poses = poses_for_states(result.states)

    pose = INITIAL_POSE
    for index in range(1, len(result.states)):
        pose = step_poses(
            pose,
            result.states[index - 1].pacman_position,
            result.states[index].pacman_position,
        )[-1]
        assert poses[index] == pose


# Renderer and visualizers (headless smoke tests)

def test_live_visualizer_draws_steps_and_death() -> None:
    result = _run("small")
    renderer = PygameRenderer(result.maze, scale=2)
    live = LivePygameVisualizer(renderer, fps=1000)

    replay = ReplayPlayer(result)
    for index in range(replay.total_frames):
        assert live(replay.get_frame(index))

    caught = result.final_state.copy()
    caught.terminated = True
    caught.termination_reason = CAUGHT_REASON
    assert live(SimulationFrame(state=caught))


def test_replay_visualizer_draws_in_between_frames() -> None:
    result = _run("classic")
    renderer = PygameRenderer(result.maze, scale=1)
    visualizer = ReplayPygameVisualizer(renderer, ReplayPlayer(result), fps=10)

    visualizer.playing = True
    for elapsed in (0.0, 30.0, 60.0, 99.0):
        visualizer.elapsed_ms = elapsed
        visualizer._draw()

    visualizer.elapsed_ms = 0.0
    visualizer._update_playback(250)
    assert visualizer.replay.current_index == 2


def test_auto_scale_fits_the_screen() -> None:
    renderer = PygameRenderer(resolve_maze("classic"))
    assert renderer.scale >= 1
    assert renderer.width == max(renderer.MIN_WINDOW_WIDTH, 28 * THEME.tile * renderer.scale)


def test_default_window_size_is_predictable(monkeypatch) -> None:
    """
    Mazes of similar size get windows of the same height (or width, for wide
    mazes), not ones that jump with the whole-number drawing scale.
    """
    monkeypatch.setattr(pygame.display, "get_desktop_sizes", lambda: [(1536, 864)])
    limit = round(864 * PygameRenderer.SCREEN_FRACTION)

    def window(height: int, width: int) -> tuple[int, int]:
        layout = "\n".join(["#" * width] + ["#" + "." * (width - 2) + "#"] * (height - 2) + ["#" * width])
        layout = layout.replace(".", "P", 1)
        renderer = PygameRenderer(parse_layout(layout, name="box"))
        size = renderer.window.get_size()
        # Frames drawn at a whole scale reach the window, scaled down.
        renderer.draw(SimulationFrame(state=SimulationEngine(renderer.maze).get_state(0)))
        assert len(np.unique(pygame.surfarray.array2d(renderer.window))) > 2
        renderer.close()
        return size

    tall = [window(52, 40), window(61, 40), window(101, 101)]
    assert all(abs(height - limit) <= 1 for _, height in tall)

    wide_width, wide_height = window(25, 80)
    assert abs(wide_width - round(1536 * PygameRenderer.SCREEN_FRACTION)) <= 1 and wide_height < limit

    # Small mazes stop at the largest scale; an explicit scale is pixel-exact.
    assert window(7, 7)[0] == 7 * THEME.tile * PygameRenderer.MAX_SCALE
    renderer = PygameRenderer(resolve_maze("small"), scale=2)
    assert renderer.screen is renderer.window and renderer.window.get_width() == max(200, 7 * THEME.tile * 2)
    renderer.close()
