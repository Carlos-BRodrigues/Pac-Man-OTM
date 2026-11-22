import pygame

from pacman_otm.simulation.actions import Action
from pacman_otm.visualization.animation import CHOMP_LOOP, DEATH_FPS, SUBFRAMES
from pacman_otm.visualization.sprites import DEATH_FRAMES, SpriteSet
from pacman_otm.visualization.theme import DEFAULT_THEME, Theme

PREVIEW_DIRECTIONS = (Action.RIGHT, Action.LEFT, Action.UP, Action.DOWN)


def run_sprite_preview(
    scale: int = 6,
    step_fps: int = 10,
    theme: Theme = DEFAULT_THEME,
) -> None:
    """
    A window looping the chomp in every direction (at the live chomp speed)
    and the death sequence. Esc or closing the window quits.
    """

    pygame.init()

    sprites = SpriteSet(theme, scale)
    cell = (theme.sprite + 4) * scale
    font = pygame.font.Font(None, 4 * scale + 8)
    label_height = 6 * scale

    width = cell * len(PREVIEW_DIRECTIONS) + cell * 2
    height = label_height + cell
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Pac-Man OTM | sprites")

    clock = pygame.time.Clock()
    elapsed_ms = 0.0
    running = True

    while running:
        elapsed_ms += clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        chomp_step = int(elapsed_ms * step_fps * SUBFRAMES / 1000)
        mouth = CHOMP_LOOP[chomp_step % len(CHOMP_LOOP)]

        # Death loops with a pause on the last frame.
        death_step = int(elapsed_ms * DEATH_FPS / 1000) % (DEATH_FRAMES + 4)
        death_index = min(death_step, DEATH_FRAMES - 1)

        screen.fill(theme.background)

        for column, facing in enumerate(PREVIEW_DIRECTIONS):
            screen.blit(
                sprites.player(mouth, facing), (column * cell + 2 * scale, label_height)
            )
            label = font.render(facing.name.lower(), True, theme.text)
            screen.blit(label, (column * cell + 2 * scale, scale))

        death_x = len(PREVIEW_DIRECTIONS) * cell + cell // 2
        screen.blit(sprites.death[death_index], (death_x, label_height))
        label = font.render(f"death {death_index + 1}/{DEATH_FRAMES}", True, theme.text)
        screen.blit(label, (death_x, scale))

        pygame.display.flip()

    pygame.quit()
