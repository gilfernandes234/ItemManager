
import math
from typing import List, Tuple, Optional
import pygame

class Particle:
    def __init__(
        self,
        position: Tuple[float, float],
        start_size: Tuple[int, int],
        final_size: Tuple[int, int],
        velocity: Tuple[float, float],
        acceleration: Tuple[float, float],
        duration: float,
        ignore_physics_after: float,
        colors: List[Tuple[int, int, int, int]],
        colors_stops: List[float],
        texture: Optional[pygame.Surface] = None,
        shape: int = 0
    ):
        self.position = list(position)
        self.velocity = list(velocity)
        self.acceleration = list(acceleration)
        self.start_size = start_size
        self.final_size = final_size
        self.size = list(start_size)
        self.duration = duration
        self.ignore_physics_after = ignore_physics_after
        self.colors = colors.copy()
        self.colors_stops = colors_stops.copy()
        self.texture = texture
        self.elapsed_time = 0.0
        self.finished = False
        self.color = colors[0] if colors else (255, 255, 255, 255)
        self.shape = shape       

    def update(self, elapsed_time: float):
        if self.duration >= 0 and self.elapsed_time >= self.duration:
            self.finished = True
            return

        self.update_color()
        self.update_size()
        self.update_position(elapsed_time)
        self.elapsed_time += elapsed_time

    def update_position(self, elapsed_time: float):
        if self.ignore_physics_after < 0 or self.elapsed_time < self.ignore_physics_after:

            delta_x = self.velocity[0] * elapsed_time
            delta_y = -self.velocity[1] * elapsed_time  
            self.position[0] += delta_x
            self.position[1] += delta_y

            self.velocity[0] += self.acceleration[0] * elapsed_time
            self.velocity[1] += self.acceleration[1] * elapsed_time

    def update_size(self):
        if self.duration <= 0:
            return

        factor = self.elapsed_time / self.duration
        self.size[0] = self.start_size[0] + (self.final_size[0] - self.start_size[0]) * factor
        self.size[1] = self.start_size[1] + (self.final_size[1] - self.start_size[1]) * factor

    def update_color(self):
        if self.duration <= 0 or len(self.colors) == 0:
            return

        current_life = self.elapsed_time / self.duration

        if len(self.colors_stops) > 1 and current_life < self.colors_stops[1]:
            range_val = self.colors_stops[1] - self.colors_stops[0]
            if range_val > 0:
                factor = (current_life - self.colors_stops[0]) / range_val
                c1 = self.colors[0]
                c2 = self.colors[1]
                self.color = tuple(int(c1[i] * (1.0 - factor) + c2[i] * factor) for i in range(4))
        elif len(self.colors) > 1:
            self.colors.pop(0)
            self.colors_stops.pop(0)
        elif self.colors:
            self.color = self.colors[0]

    def render(self, surface: pygame.Surface):
        if self.finished:
            return
        
        x = int(self.position[0])
        y = int(self.position[1])
        
        if self.texture:
            scaled = pygame.transform.scale(self.texture, (int(self.size[0]), int(self.size[1])))
            scaled.set_alpha(self.color[3])
            surface.blit(scaled, (x - int(self.size[0] / 2), y - int(self.size[1] / 2)))
        else:
            if self.shape == 0:  
                radius = int(max(self.size[0], self.size[1]) / 2)
                if radius > 0:
                    circle_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
                    pygame.draw.circle(circle_surface, self.color, (radius, radius), radius)
                    surface.blit(circle_surface, (x - radius, y - radius))
            else:  
                rect_surface = pygame.Surface((int(self.size[0]), int(self.size[1])), pygame.SRCALPHA)
                rect_surface.fill(self.color)
                surface.blit(rect_surface, (x - int(self.size[0] / 2), y - int(self.size[1] / 2)))


    def get_position(self) -> Tuple[float, float]:
        return tuple(self.position)

    def get_velocity(self) -> Tuple[float, float]:
        return tuple(self.velocity)

    def set_position(self, position: Tuple[float, float]):
        self.position = list(position)

    def set_velocity(self, velocity: Tuple[float, float]):
        self.velocity = list(velocity)

    def has_finished(self) -> bool:
        return self.finished
