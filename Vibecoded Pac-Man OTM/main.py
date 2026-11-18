import pygame
from config import FPS
from game.app import PacmanApp


def main():
    pygame.init()
    pygame.display.set_caption("Pac-Man OTM")
    app = PacmanApp()
    clock = pygame.time.Clock()
    while app.running:
        dt = min(clock.tick(FPS) / 1000.0, 0.05)
        app.handle_events(pygame.event.get())
        app.update(dt)
        app.draw()
    pygame.quit()


if __name__ == "__main__":
    main()
