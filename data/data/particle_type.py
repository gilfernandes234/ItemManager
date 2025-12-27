
import random
import math
from typing import List, Tuple, Optional
import pygame

class ParticleType:
    def __init__(self, name: str = "default"):
        self.name = name

 
        self.colors: List[Tuple[int, int, int, int]] = [(255, 255, 255, 128)]
        self.colors_stops: List[float] = [0.0]
        self.texture: Optional[pygame.Surface] = None


        self.start_size = (32, 32)
        self.final_size = (32, 32)
        self.random_size_multiplier = (1.0, 1.0)
        self.shape = 0
     
        self.min_position_radius = 0.0
        self.max_position_radius = 3.0
        self.min_position_angle = 0.0
        self.max_position_angle = 360.0


        self.min_velocity = 32.0
        self.max_velocity = 64.0
        self.min_velocity_angle = 0.0
        self.max_velocity_angle = 360.0


        self.min_acceleration = 32.0
        self.max_acceleration = 64.0
        self.min_acceleration_angle = 0.0
        self.max_acceleration_angle = 360.0

     
        self.min_duration = 0.0
        self.max_duration = 10.0
        self.ignore_physics_after = -1.0

    @staticmethod
    def random_range(min_val: float, max_val: float) -> float:
        return random.uniform(min_val, max_val)

    def get_name(self) -> str:
        return self.name

    def set_colors(self, colors: List[Tuple[int, int, int, int]], stops: List[float]):
        self.colors = colors
        self.colors_stops = stops

    def set_texture(self, texture: pygame.Surface):
        self.texture = texture

    def set_size(self, start: Tuple[int, int], final: Tuple[int, int]):
        self.start_size = start
        self.final_size = final

    def set_position_radius(self, min_r: float, max_r: float):
        self.min_position_radius = min_r
        self.max_position_radius = max_r

    def set_position_angle(self, min_a: float, max_a: float):
        self.min_position_angle = math.radians(min_a)
        self.max_position_angle = math.radians(max_a)

    def set_velocity(self, min_v: float, max_v: float):
        self.min_velocity = min_v
        self.max_velocity = max_v

    def set_velocity_angle(self, min_a: float, max_a: float):
        self.min_velocity_angle = math.radians(min_a)
        self.max_velocity_angle = math.radians(max_a)

    def set_acceleration(self, min_a: float, max_a: float):
        self.min_acceleration = min_a
        self.max_acceleration = max_a

    def set_acceleration_angle(self, min_a: float, max_a: float):
        self.min_acceleration_angle = math.radians(min_a)
        self.max_acceleration_angle = math.radians(max_a)

    def set_duration(self, min_d: float, max_d: float):
        self.min_duration = min_d
        self.max_duration = max_d
