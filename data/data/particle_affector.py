
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from particle import Particle

class ParticleAffector:
    def __init__(self):
        self.duration = -1.0
        self.delay = 0.0
        self.elapsed_time = 0.0
        self.finished = False
        self.active = False

    def update(self, elapsed_time: float):
        if self.duration >= 0 and self.elapsed_time >= self.duration + self.delay:
            self.finished = True
            return

        if not self.active and self.elapsed_time > self.delay:
            self.active = True

        self.elapsed_time += elapsed_time

    def update_particle(self, particle: 'Particle', elapsed_time: float):
        pass

    def has_finished(self) -> bool:
        return self.finished


class GravityAffector(ParticleAffector):
    def __init__(self, angle: float = 270.0, gravity: float = 9.8):
        super().__init__()
        self.angle = math.radians(angle)
        self.gravity = gravity

    def update_particle(self, particle: 'Particle', elapsed_time: float):
        if not self.active:
            return

        velocity = list(particle.get_velocity())
        velocity[0] += self.gravity * elapsed_time * math.cos(self.angle)
        velocity[1] += self.gravity * elapsed_time * math.sin(self.angle)
        particle.set_velocity(tuple(velocity))


class AttractionAffector(ParticleAffector):
    def __init__(self, position: tuple = (0, 0), acceleration: float = 32.0, 
                 reduction: float = 0.0, repelish: bool = False):
        super().__init__()
        self.position = position
        self.acceleration = acceleration
        self.reduction = reduction
        self.repelish = repelish

    def update_particle(self, particle: 'Particle', elapsed_time: float):
        if not self.active:
            return

        p_position = particle.get_position()
        dx = self.position[0] - p_position[0]
        dy = p_position[1] - self.position[1]

        length = math.sqrt(dx * dx + dy * dy)
        if length == 0:
            return

        direction = -1.0 if self.repelish else 1.0

        p_velocity = list(particle.get_velocity())
        p_velocity[0] += (dx / length * self.acceleration * elapsed_time) * direction
        p_velocity[1] += (dy / length * self.acceleration * elapsed_time) * direction

        # Redução de velocidade
        p_velocity[0] -= p_velocity[0] * self.reduction / 100.0 * elapsed_time
        p_velocity[1] -= p_velocity[1] * self.reduction / 100.0 * elapsed_time

        particle.set_velocity(tuple(p_velocity))
