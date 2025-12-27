
import time
import math
from typing import List
from particle import Particle
from particle_emitter import ParticleEmitter
from particle_affector import ParticleAffector
import pygame

class ParticleSystem:
    def __init__(self):
        self.particles: List[Particle] = []
        self.emitters: List[ParticleEmitter] = []
        self.affectors: List[ParticleAffector] = []
        self.finished = False
        self.last_update_time = time.time()

    def add_emitter(self, emitter: ParticleEmitter):
        self.emitters.append(emitter)

    def add_affector(self, affector: ParticleAffector):
        self.affectors.append(affector)

    def add_particle(self, particle: Particle):
        self.particles.append(particle)

    def update(self):
        delay = 0.0166  

        current_time = time.time()
        elapsed_time = current_time - self.last_update_time

        if elapsed_time < delay:
            return

        if not self.particles and not self.emitters:
            self.finished = True
            return

        self.last_update_time = current_time - (elapsed_time % delay)

        iterations = int(math.floor(elapsed_time / delay))

        for i in range(iterations):
  
            for emitter in self.emitters[:]:
                if emitter.has_finished():
                    self.emitters.remove(emitter)
                else:
                    emitter.update(delay, self)

      
            for affector in self.affectors[:]:
                if affector.has_finished():
                    self.affectors.remove(affector)
                else:
                    affector.update(delay)

       
            for particle in self.particles[:]:
                if particle.has_finished():
                    self.particles.remove(particle)
                else:
                    for affector in self.affectors:
                        affector.update_particle(particle, delay)
                    particle.update(delay)

    def render(self, surface: pygame.Surface):
        for particle in self.particles:
            particle.render(surface)

    def has_finished(self) -> bool:
        return self.finished

    def get_particle_count(self) -> int:
        return len(self.particles)
