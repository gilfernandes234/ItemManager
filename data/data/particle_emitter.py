
import math
import random
from typing import TYPE_CHECKING
from particle_type import ParticleType
from particle import Particle

if TYPE_CHECKING:
    from particle_system import ParticleSystem

class ParticleEmitter:
    def __init__(self):
        self.position = (0, 0)
        self.duration = -1.0
        self.delay = 0.0
        self.elapsed_time = 0.0
        self.burst_rate = 1.0
        self.current_burst = 0
        self.burst_count = 32
        self.finished = False
        self.active = False
        self.particle_type: ParticleType = None

    def set_particle_type(self, particle_type: ParticleType):
        self.particle_type = particle_type

    def set_position(self, position: tuple):
        self.position = position

    def set_duration(self, duration: float):
        self.duration = duration

    def set_delay(self, delay: float):
        self.delay = delay

    def set_burst_rate(self, rate: float):
        self.burst_rate = rate

    def set_burst_count(self, count: int):
        self.burst_count = count

    def update(self, elapsed_time: float, particle_system: 'ParticleSystem'):
        self.elapsed_time += elapsed_time

        if self.duration > 0 and self.elapsed_time >= self.duration + self.delay:
            self.finished = True
            return

        if not self.active and self.elapsed_time > self.delay:
            self.active = True

        if not self.active:
            return

        next_burst = int(math.floor((self.elapsed_time - self.delay) * self.burst_rate) + 1)
        ptype = self.particle_type

        for b in range(self.current_burst, next_burst):
    
            p_radius = random.uniform(ptype.min_position_radius, ptype.max_position_radius)
            p_angle = random.uniform(ptype.min_position_angle, ptype.max_position_angle)
            p_position = (
                self.position[0] + p_radius * math.cos(p_angle),
                self.position[1] + p_radius * math.sin(p_angle)
            )

            for p in range(self.burst_count):
                p_duration = random.uniform(ptype.min_duration, ptype.max_duration)

           
                p_velocity_abs = random.uniform(ptype.min_velocity, ptype.max_velocity)
                p_velocity_angle = random.uniform(ptype.min_velocity_angle, ptype.max_velocity_angle)
                p_velocity = (
                    p_velocity_abs * math.cos(p_velocity_angle),
                    p_velocity_abs * math.sin(p_velocity_angle)
                )

               
                p_accel_abs = random.uniform(ptype.min_acceleration, ptype.max_acceleration)
                p_accel_angle = random.uniform(ptype.min_acceleration_angle, ptype.max_acceleration_angle)
                p_acceleration = (
                    p_accel_abs * math.cos(p_accel_angle),
                    p_accel_abs * math.sin(p_accel_angle)
                )

           
                multiplier = random.uniform(ptype.random_size_multiplier[0], ptype.random_size_multiplier[1])
                start_size = (int(ptype.start_size[0] * multiplier), int(ptype.start_size[1] * multiplier))
                final_size = (int(ptype.final_size[0] * multiplier), int(ptype.final_size[1] * multiplier))

                particle = Particle(
                    p_position,
                    start_size,
                    final_size,
                    p_velocity,
                    p_acceleration,
                    p_duration,
                    ptype.ignore_physics_after,
                    ptype.colors,
                    ptype.colors_stops,
                    ptype.texture,
                    ptype.shape                    
                )

                particle_system.add_particle(particle)

        self.current_burst = next_burst

    def has_finished(self) -> bool:
        return self.finished
