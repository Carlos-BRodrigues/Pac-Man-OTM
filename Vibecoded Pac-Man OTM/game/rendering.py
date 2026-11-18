import math, pygame
from config import (
    TILE_SIZE,
    WINDOW_MARGIN,
    HUD_HEIGHT,
    BACKGROUND,
    WALL_COLOR,
    WALL_HIGHLIGHT,
    PELLET_COLOR,
    PACMAN_COLOR,
    TEXT_COLOR,
    MUTED_TEXT,
)


def window_size(maze):
    return (
        maze.width * TILE_SIZE + 2 * WINDOW_MARGIN,
        maze.height * TILE_SIZE + HUD_HEIGHT + 2 * WINDOW_MARGIN,
    )


def draw_maze(screen, maze, pellets, offset):
    ox, oy = offset
    screen.fill(BACKGROUND)
    walls = {
        (x, y) for y, row in enumerate(maze.grid) for x, v in enumerate(row) if v == 1
    }
    # Rounded tiles are joined by bridges across shared edges: visually one continuous wall.
    for x, y in walls:
        pygame.draw.rect(
            screen,
            WALL_COLOR,
            (ox + x * TILE_SIZE, oy + y * TILE_SIZE, TILE_SIZE, TILE_SIZE),
            border_radius=7,
        )
    for x, y in walls:
        px, py = ox + x * TILE_SIZE, oy + y * TILE_SIZE
        if (x + 1, y) in walls:
            pygame.draw.rect(
                screen, WALL_COLOR, (px + TILE_SIZE // 2, py, TILE_SIZE, TILE_SIZE)
            )
        if (x, y + 1) in walls:
            pygame.draw.rect(
                screen, WALL_COLOR, (px, py + TILE_SIZE // 2, TILE_SIZE, TILE_SIZE)
            )
    for x, y in walls:
        if (x, y - 1) not in walls:
            pygame.draw.line(
                screen,
                WALL_HIGHLIGHT,
                (ox + x * TILE_SIZE + 5, oy + y * TILE_SIZE + 2),
                (ox + (x + 1) * TILE_SIZE - 5, oy + y * TILE_SIZE + 2),
                2,
            )
    for x, y in pellets:
        pygame.draw.circle(
            screen,
            PELLET_COLOR,
            (ox + x * TILE_SIZE + TILE_SIZE // 2, oy + y * TILE_SIZE + TILE_SIZE // 2),
            max(2, TILE_SIZE // 9),
        )


def draw_pacman(screen, pos, direction, anim_time, offset):
    x, y = pos
    ox, oy = offset
    cx = int(ox + (x + 0.5) * TILE_SIZE)
    cy = int(oy + (y + 0.5) * TILE_SIZE)
    r = TILE_SIZE * 0.39
    pygame.draw.circle(screen, PACMAN_COLOR, (cx, cy), int(r))
    mouth = 0.06 + 0.42 * (0.5 + 0.5 * math.sin(anim_time * 11))
    angle = {"RIGHT": 0, "DOWN": math.pi / 2, "LEFT": math.pi, "UP": -math.pi / 2}.get(
        direction, 0
    )
    p1 = (
        cx + math.cos(angle - mouth) * r * 1.15,
        cy + math.sin(angle - mouth) * r * 1.15,
    )
    p2 = (
        cx + math.cos(angle + mouth) * r * 1.15,
        cy + math.sin(angle + mouth) * r * 1.15,
    )
    pygame.draw.polygon(screen, BACKGROUND, [(cx, cy), p1, p2])


def draw_hud(screen, font, small, sim, mode, controller):
    s = sim.state
    st = sim.statistics
    x = WINDOW_MARGIN
    y = WINDOW_MARGIN
    screen.blit(
        font.render(
            f"Score: {s.score}   Pellets: {st.pellets_collected}/{len(sim.initial_pellets)}",
            True,
            TEXT_COLOR,
        ),
        (x, y),
    )
    screen.blit(
        small.render(
            f"Game time: {st.game_time:.1f}s   Moves: {st.successful_moves}   Algorithm compute: {st.algorithm_compute_seconds*1000:.2f} ms",
            True,
            MUTED_TEXT,
        ),
        (x, y + 29),
    )
    screen.blit(
        small.render(
            f"{mode}: {controller}   M: switch mode   R: restart   Arrows/WASD: move",
            True,
            MUTED_TEXT,
        ),
        (x, y + 50),
    )
    if s.won:
        screen.blit(
            font.render("ALL PELLETS COLLECTED!", True, (255, 230, 80)), (x, y + 69)
        )
