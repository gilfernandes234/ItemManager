import pygame
import sys
import math
import os
from PyQt6.QtWidgets import QApplication, QFileDialog
from PyQt6.QtCore import Qt
import json
import random


if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

data_path = os.path.join(base_path, "data")
if data_path not in sys.path:
    sys.path.append(data_path)

from particle import Particle
from particle_type import ParticleType
from particle_emitter import ParticleEmitter
from particle_system import ParticleSystem
from particle_affector import GravityAffector, AttractionAffector

pygame.init()

class ColorEditor:

    def __init__(self):
        self.colors = [
            [255, 255, 0, 255],
            [255, 128, 0, 200],
            [255, 0, 0, 100],
            [50, 50, 50, 0]
        ]
        self.stops = [0.0, 0.3, 0.6, 1.0]
        self.selected_color = 0
        self.selected_channel = 0

    def get_colors(self):
        return [tuple(c) for c in self.colors]
    
    def get_stops(self):
        return self.stops.copy()

    def adjust_channel(self, delta):
        self.colors[self.selected_color][self.selected_channel] += delta
        self.colors[self.selected_color][self.selected_channel] = max(0, min(255, 
            self.colors[self.selected_color][self.selected_channel]))

    def next_color(self):
        self.selected_color = (self.selected_color + 1) % len(self.colors)

    def prev_color(self):
        self.selected_color = (self.selected_color - 1) % len(self.colors)


class ParticleGenerator:
    def __init__(self, width=1400, height=900):
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Editor de Partículas")
        self.clock = pygame.time.Clock()
        self.running = True
        self.particle_system = None
        
        self.color_editor = ColorEditor()
        
        # Modos: "particle", "emitter", "colors", "affectors"
        self.edit_mode = "particle"
        
        # Textura
        self.texture = None
        self.texture_path = None
        self.texture_preview = None
        
        # Nomes para exportação
        self.particle_name = "custom_particle"
        self.effect_name = "custom_effect"
        

        self.particle_params = {

            'min_position_radius': 0.0,
            'max_position_radius': 800.0,
            'min_position_angle': 0.0,
            'max_position_angle': 360.0,
            
            # Velocity
            'min_velocity': 10.0,
            'max_velocity': 150.0,
            'min_velocity_angle': 30.0,
            'max_velocity_angle': 50.0,
            
            # Acceleration
            'min_acceleration': 0.0,
            'max_acceleration': 20.0,
            'min_acceleration_angle': 0.0,
            'max_acceleration_angle': 360.0,
            
            # Duration
            'min_duration': 0,
            'max_duration': 3.5,
            'ignore_physics_after': -1.0,
            
            # Size
            'start_size': 8,
            'final_size': 4,
            'random_size_multiplier': 1.0,
            
            # Visual
            'use_texture': False,
            'composition_mode': 1,  # 0=normal, 1=additive, 2=multiply
            'particle_shape': 0, 
        }
        
        # PARÂMETROS DO EMISSOR
        self.emitter_params = {
            'burst_rate': 25.0,
            'burst_count': 1,
            'duration': 10,
            'delay': 0.1,
        }
        

        self.affector_params = {

            'use_gravity': False,
            'gravity_angle': 180.0,
            'gravity_strength': 100.0,
            

            'use_attraction': False,
            'attraction_acceleration': 1000.0,
            'attraction_reduction': 0.0,
            'attraction_repelish': False,
        }
        
        # Fontes
        self.font = pygame.font.Font(None, 22)
        self.small_font = pygame.font.Font(None, 18)
        self.title_font = pygame.font.Font(None, 28)
        
        # Controles
        self.selected_param = 0
        self.param_lists = {
            'particle': list(self.particle_params.keys()),
            'emitter': list(self.emitter_params.keys()),
            'affectors': list(self.affector_params.keys()),
        }
        
        self.mouse_pos = (width // 2, height // 2)
        self.emitting = False
        
        self.particle_library = []
        self.selected_preset = 0
        self.library_dir = os.path.join(base_path, "presets")
        if not os.path.exists(self.library_dir):
            os.makedirs(self.library_dir)
        self.refresh_library()

    def refresh_library(self):

        self.particle_library = []
        if os.path.exists(self.library_dir):
            for file in os.listdir(self.library_dir):
                if file.endswith('.otps'):
                    self.particle_library.append(file)
        self.particle_library.sort()

    def parse_otps_file(self, filepath):

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            params = {}
            current_section = None

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Detectar seções
                if line in ['Particle', 'Effect', 'System', 'Emitter', 'GravityAffector', 'AttractionAffector']:
                    current_section = line
                    continue

                # Parse de parâmetros key: value
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    # Converter valores
                    if current_section == 'Particle':
                        if key == 'duration':
                            params['max_duration'] = float(value)
                        elif key == 'min-position-radius':
                            params['min_position_radius'] = float(value)
                        elif key == 'max-position-radius':
                            params['max_position_radius'] = float(value)
                        elif key == 'min-position-angle':
                            params['min_position_angle'] = float(value)
                        elif key == 'max-position-angle':
                            params['max_position_angle'] = float(value)
                        elif key == 'min-velocity':
                            params['min_velocity'] = float(value)
                        elif key == 'max-velocity':
                            params['max_velocity'] = float(value)
                        elif key == 'min-velocity-angle':
                            params['min_velocity_angle'] = float(value)
                        elif key == 'max-velocity-angle':
                            params['max_velocity_angle'] = float(value)
                        elif key == 'min-acceleration':
                            params['min_acceleration'] = float(value)
                        elif key == 'max-acceleration':
                            params['max_acceleration'] = float(value)
                        elif key == 'min-acceleration-angle':
                            params['min_acceleration_angle'] = float(value)
                        elif key == 'max-acceleration-angle':
                            params['max_acceleration_angle'] = float(value)
                        elif key == 'ignore-physics-after':
                            params['ignore_physics_after'] = float(value)
                        elif key == 'size':
                            sizes = value.split()
                            if len(sizes) >= 2:
                                params['start_size'] = int(sizes[0])
                                params['final_size'] = int(sizes[1])
                        elif key == 'composition-mode':
                            modes = {'normal': 0, 'addition': 1, 'multiply': 2}
                            params['composition_mode'] = modes.get(value, 0)
                        elif key == 'colors':
                            colors = value.split()
                            parsed_colors = []
                            for c in colors:
                                if c.startswith('#'):
                                    r = int(c[1:3], 16)
                                    g = int(c[3:5], 16)
                                    b = int(c[5:7], 16)
                                    a = int(c[7:9], 16) if len(c) > 7 else 255
                                    parsed_colors.append([r, g, b, a])
                            params['colors'] = parsed_colors
                        elif key == 'colors-stops':
                            stops = [float(s) for s in value.split()]
                            params['color_stops'] = stops

                    elif current_section == 'Emitter':
                        if key == 'burst-rate':
                            params['burst_rate'] = float(value)
                        elif key == 'burst-count':
                            params['burst_count'] = int(value)
                        elif key == 'duration':
                            params['emitter_duration'] = float(value)
                        elif key == 'delay':
                            params['delay'] = float(value)

                    elif current_section == 'GravityAffector':
                        params['use_gravity'] = True
                        if key == 'angle':
                            params['gravity_angle'] = float(value)
                        elif key == 'gravity':
                            params['gravity_strength'] = float(value)

                    elif current_section == 'AttractionAffector':
                        params['use_attraction'] = True
                        if key == 'acceleration':
                            params['attraction_acceleration'] = float(value)
                        elif key == 'reduction':
                            params['attraction_reduction'] = float(value)
                        elif key == 'repelish':
                            params['attraction_repelish'] = value.lower() == 'true'

            return params

        except Exception as e:
            print(f"✗ Erro ao carregar preset: {e}")
            return None

    def load_preset(self, filename):
        """Carrega um preset da biblioteca"""
        filepath = os.path.join(self.library_dir, filename)
        params = self.parse_otps_file(filepath)

        if not params:
            return False

        # Aplicar parâmetros de partícula
        for key in ['min_position_radius', 'max_position_radius', 'min_position_angle', 'max_position_angle',
                    'min_velocity', 'max_velocity', 'min_velocity_angle', 'max_velocity_angle',
                    'min_acceleration', 'max_acceleration', 'min_acceleration_angle', 'max_acceleration_angle',
                    'max_duration', 'ignore_physics_after', 'start_size', 'final_size', 'composition_mode']:
            if key in params:
                self.particle_params[key] = params[key]

        # Aplicar cores
        if 'colors' in params and len(params['colors']) > 0:
            self.color_editor.colors = params['colors'][:4]  # Máximo 4 cores
            # Preencher com cores padrão se necessário
            while len(self.color_editor.colors) < 4:
                self.color_editor.colors.append([255, 255, 255, 255])

        if 'color_stops' in params and len(params['color_stops']) > 0:
            self.color_editor.stops = params['color_stops'][:4]
            # Preencher stops
            while len(self.color_editor.stops) < 4:
                self.color_editor.stops.append(1.0)

        # Aplicar parâmetros de emissor
        for key in ['burst_rate', 'burst_count', 'delay']:
            if key in params:
                self.emitter_params[key] = params[key]

        if 'emitter_duration' in params:
            self.emitter_params['duration'] = params['emitter_duration']

        # Aplicar affectors
        if 'use_gravity' in params:
            self.affector_params['use_gravity'] = params['use_gravity']
            if 'gravity_angle' in params:
                self.affector_params['gravity_angle'] = params['gravity_angle']
            if 'gravity_strength' in params:
                self.affector_params['gravity_strength'] = params['gravity_strength']

        if 'use_attraction' in params:
            self.affector_params['use_attraction'] = params['use_attraction']
            if 'attraction_acceleration' in params:
                self.affector_params['attraction_acceleration'] = params['attraction_acceleration']
            if 'attraction_reduction' in params:
                self.affector_params['attraction_reduction'] = params['attraction_reduction']
            if 'attraction_repelish' in params:
                self.affector_params['attraction_repelish'] = params['attraction_repelish']

        print(f"✓ Preset carregado: {filename}")
        return True



    def randomize_all_parameters(self):

        self.particle_params = {
            # Position
            'min_position_radius': random.uniform(0, 50),
            'max_position_radius': random.uniform(50, 800),
            'min_position_angle': random.uniform(0, 180),
            'max_position_angle': random.uniform(180, 360),
            
            # Velocity
            'min_velocity': random.uniform(5, 50),
            'max_velocity': random.uniform(50, 200),
            'min_velocity_angle': random.uniform(0, 180),
            'max_velocity_angle': random.uniform(180, 360),
            
            # Acceleration
            'min_acceleration': random.uniform(0, 50),
            'max_acceleration': random.uniform(50, 200),
            'min_acceleration_angle': random.uniform(0, 180),
            'max_acceleration_angle': random.uniform(180, 360),
            
            # Duration
            'min_duration': random.uniform(0, 1),
            'max_duration': random.uniform(1, 5),
            'ignore_physics_after': random.choice([-1.0, random.uniform(0.5, 3)]),
            
            # Size
            'start_size': random.randint(16, 16),
            'final_size': random.randint(16, 16),
            'random_size_multiplier': random.uniform(0.5, 2.0),
            
            # Visual
            'use_texture': self.particle_params['use_texture'],  # Mantém textura
            'composition_mode': random.randint(0, 2),
            'particle_shape': random.randint(0, 1),
        }
        
        # Randomiza parâmetros do emissor
        self.emitter_params = {
            'burst_rate': random.uniform(1, 50),
            'burst_count': random.randint(1, 10),
            'duration': random.uniform(0, 10),
            'delay': random.uniform(0.05, 0.5),
        }
        
        # Randomiza affectors
        self.affector_params = {
            'use_gravity': random.choice([True, False]),
            'gravity_angle': random.uniform(0, 360),
            'gravity_strength': random.uniform(-200, 200),
            'use_attraction': random.choice([True, False]),
            'attraction_acceleration': random.uniform(100, 2000),
            'attraction_reduction': random.uniform(0, 50),
            'attraction_repelish': random.choice([True, False]),
        }
        
        # Randomiza cores
        self.color_editor.colors = [
            [random.randint(0, 255) for _ in range(4)] for _ in range(4)
        ]
        
        # Mantém stops ordenados
        stops = sorted([random.uniform(0, 1) for _ in range(3)])
        self.color_editor.stops = [0.0] + stops
        
        print("✓ Todos os parâmetros randomizados!")
            
        

    def get_current_params(self):

        if self.edit_mode == "particle":
            return self.particle_params
        elif self.edit_mode == "emitter":
            return self.emitter_params
        elif self.edit_mode == "affectors":
            return self.affector_params
        return {}

    def get_current_param_list(self):

        if self.edit_mode in self.param_lists:
            return self.param_lists[self.edit_mode]
        return []

    def load_texture(self):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Selecionar Textura PNG",
            "",
            "PNG files (*.png);;All files (*.*)"
        )
        
        if file_path:
            try:
                self.texture = pygame.image.load(file_path).convert_alpha()
                self.texture_path = os.path.basename(file_path)
                
                preview_size = (64, 64)
                self.texture_preview = pygame.transform.scale(self.texture, preview_size)
                
                self.particle_params['use_texture'] = True
                
                print(f"✓ Textura carregada: {self.texture_path}")
                return True
            except Exception as e:
                print(f"✗ Erro ao carregar textura: {e}")
                self.texture = None
                self.texture_path = None
                self.texture_preview = None
                return False
        return False

    def export_to_otclient(self):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        
        file_path, _ = QFileDialog.getSaveFileName(
            None,
            "Salvar Partículas OTClient",
            "",
            "OTClient Particle System (*.otps);;All files (*.*)"
        )
        
        
        
      
        if not file_path:
            return False

        # Se usuário cancelou ou não especificou diretório, usar presets
        if file_path and not os.path.dirname(file_path):
            file_path = os.path.join(self.library_dir, os.path.basename(file_path))

        # Garantir extensão .otps
        if not file_path.endswith('.otps'):
            file_path += '.otps'
        
        try:
     
            colors_hex = []
            for color in self.color_editor.colors:
                r, g, b, a = color
                hex_color = f"#{r:02x}{g:02x}{b:02x}{a:02x}"
                colors_hex.append(hex_color)
            
            colors_str = " ".join(colors_hex)
            stops_str = " ".join(str(s) for s in self.color_editor.stops)
   
            if self.particle_params['use_texture'] and self.texture_path:
                texture_name = os.path.splitext(self.texture_path)[0]
                texture_path = f"/particles/{texture_name}"
            else:
                texture_path = "/particles/particle"
            
            # Composition mode
            comp_modes = ["normal", "addition", "multiply"]
            comp_mode = comp_modes[self.particle_params['composition_mode']]
            
            # Gera conteúdo OTML
            content = f"""Particle
  name: {self.particle_name}

  duration: {self.particle_params['max_duration']:.2f}
  min-position-radius: {self.particle_params['min_position_radius']:.0f}
  max-position-radius: {self.particle_params['max_position_radius']:.0f}
  min-position-angle: {self.particle_params['min_position_angle']:.0f}
  max-position-angle: {self.particle_params['max_position_angle']:.0f}
  min-velocity: {self.particle_params['min_velocity']:.0f}
  max-velocity: {self.particle_params['max_velocity']:.0f}
  min-velocity-angle: {self.particle_params['min_velocity_angle']:.0f}
  max-velocity-angle: {self.particle_params['max_velocity_angle']:.0f}
  min-acceleration: {self.particle_params['min_acceleration']:.0f}
  max-acceleration: {self.particle_params['max_acceleration']:.0f}
  min-acceleration-angle: {self.particle_params['min_acceleration_angle']:.0f}
  max-acceleration-angle: {self.particle_params['max_acceleration_angle']:.0f}
  colors: {colors_str}
  colors-stops: {stops_str}
  size: {self.particle_params['start_size']} {self.particle_params['final_size']}
  texture: {texture_path}
  composition-mode: {comp_mode}
"""

            if self.particle_params['ignore_physics_after'] >= 0:
                content += f"  ignore-physics-after: {self.particle_params['ignore_physics_after']:.2f}\n"

            content += f"""
Effect
  name: {self.effect_name}
  description: Generated by Particle Editor

  System
    position: 0 0

    Emitter
      position: 0 0
      delay: {self.emitter_params['delay']:.2f}
      duration: {self.emitter_params['duration']:.2f}
      burst-rate: {self.emitter_params['burst_rate']:.0f}
      burst-count: {self.emitter_params['burst_count']}
      particle-type: {self.particle_name}
"""

            # Gravity Affector
            if self.affector_params['use_gravity']:
                content += f"""
    GravityAffector
      angle: {self.affector_params['gravity_angle']:.0f}
      gravity: {self.affector_params['gravity_strength']:.0f}
"""

            # Attraction Affector
            if self.affector_params['use_attraction']:
                repelish_str = "true" if self.affector_params['attraction_repelish'] else "false"
                content += f"""
    AttractionAffector
      position: 0 0
      acceleration: {self.affector_params['attraction_acceleration']:.0f}
      reduction: {self.affector_params['attraction_reduction']:.0f}
      repelish: {repelish_str}
"""

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✓ Arquivo exportado: {file_path}")
            return True
            
        except Exception as e:
            print(f"✗ Erro ao exportar: {e}")
            return False
            
            self.refresh_library()            

    def create_particle_type(self) -> ParticleType:

        ptype = ParticleType("custom")
        
        if self.particle_params['use_texture'] and self.texture:
            ptype.set_texture(self.texture)
        
        ptype.set_colors(self.color_editor.get_colors(), self.color_editor.get_stops())
        
        # Position
        ptype.set_position_radius(
            self.particle_params['min_position_radius'],
            self.particle_params['max_position_radius']
        )
        ptype.set_position_angle(
            self.particle_params['min_position_angle'],
            self.particle_params['max_position_angle']
        )
        
        # Velocity
        ptype.set_velocity(
            self.particle_params['min_velocity'],
            self.particle_params['max_velocity']
        )
        ptype.set_velocity_angle(
            self.particle_params['min_velocity_angle'],
            self.particle_params['max_velocity_angle']
        )
        
        # Acceleration
        ptype.set_acceleration(
            self.particle_params['min_acceleration'],
            self.particle_params['max_acceleration']
        )
        ptype.set_acceleration_angle(
            self.particle_params['min_acceleration_angle'],
            self.particle_params['max_acceleration_angle']
        )
        
        # Duration
        ptype.set_duration(
            self.particle_params['min_duration'],
            self.particle_params['max_duration']
        )
        ptype.ignore_physics_after = self.particle_params['ignore_physics_after']
        
        # Size
        ptype.start_size = (self.particle_params['start_size'], self.particle_params['start_size'])
        ptype.final_size = (self.particle_params['final_size'], self.particle_params['final_size'])
        ptype.random_size_multiplier = (
            self.particle_params['random_size_multiplier'],
            self.particle_params['random_size_multiplier']
        )

        ptype.shape = self.particle_params['particle_shape']       
        return ptype

    def create_particle_system(self):

        self.particle_system = ParticleSystem()
        
        emitter = ParticleEmitter()
        emitter.set_position(self.mouse_pos)
        emitter.set_burst_rate(self.emitter_params['burst_rate'])
        emitter.set_burst_count(self.emitter_params['burst_count'])
        emitter.set_duration(self.emitter_params['duration'])
        emitter.set_delay(self.emitter_params['delay'])
        
        ptype = self.create_particle_type()
        emitter.set_particle_type(ptype)
        
        self.particle_system.add_emitter(emitter)
        
        # Affectors
        if self.affector_params['use_gravity']:
            gravity = GravityAffector(
                angle=self.affector_params['gravity_angle'],
                gravity=self.affector_params['gravity_strength']
            )
            self.particle_system.add_affector(gravity)
        
        if self.affector_params['use_attraction']:
            attraction = AttractionAffector(
                position=self.mouse_pos,
                acceleration=self.affector_params['attraction_acceleration'],
                reduction=self.affector_params['attraction_reduction'],
                repelish=self.affector_params['attraction_repelish']
            )
            self.particle_system.add_affector(attraction)

    def handle_input(self):

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self.emitting = True
                    self.create_particle_system()
                    
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.emitting = False
                    
            elif event.type == pygame.MOUSEMOTION:
                self.mouse_pos = event.pos
                
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                    
                elif event.key == pygame.K_TAB:
                    # Cicla entre modos
                    modes = ["particle", "emitter", "affectors", "colors", "library"]
                    current_idx = modes.index(self.edit_mode)
                    self.edit_mode = modes[(current_idx + 1) % len(modes)]
                    self.selected_param = 0
                    
                elif event.key == pygame.K_SPACE:
                    self.create_particle_system()
                    
                elif event.key == pygame.K_c:
                    if self.particle_system:
                        self.particle_system = None
                
                elif event.key == pygame.K_t:
                    self.load_texture()
                
                elif event.key == pygame.K_s:
                    self.export_to_otclient()
                    
                elif event.key == pygame.K_f: 
                    self.randomize_all_parameters()
                    self.create_particle_system()  

                elif event.key == pygame.K_l:
                    # Atualizar biblioteca
                    self.refresh_library()                    
                
                # Navegação
                elif self.edit_mode in ["particle", "emitter", "affectors"]:
                    if event.key == pygame.K_UP:
                        param_list = self.get_current_param_list()
                        self.selected_param = (self.selected_param - 1) % len(param_list)
                    elif event.key == pygame.K_DOWN:
                        param_list = self.get_current_param_list()
                        self.selected_param = (self.selected_param + 1) % len(param_list)
                    elif event.key == pygame.K_LEFT:
                        self.adjust_parameter(-1)
                    elif event.key == pygame.K_RIGHT:
                        self.adjust_parameter(1)
                    elif event.key == pygame.K_LSHIFT or event.key == pygame.K_RSHIFT:
                        pass  # Modificador para ajuste fino
                
                # Modo cores
                elif self.edit_mode == "colors":
                    if event.key == pygame.K_UP:
                        self.color_editor.prev_color()
                    elif event.key == pygame.K_DOWN:
                        self.color_editor.next_color()
                    elif event.key == pygame.K_LEFT:
                        self.color_editor.adjust_channel(-5)
                    elif event.key == pygame.K_RIGHT:
                        self.color_editor.adjust_channel(5)
                    elif event.key == pygame.K_r:
                        self.color_editor.selected_channel = 0
                    elif event.key == pygame.K_g:
                        self.color_editor.selected_channel = 1
                    elif event.key == pygame.K_b:
                        self.color_editor.selected_channel = 2
                    elif event.key == pygame.K_a:
                        self.color_editor.selected_channel = 3
                        
                        
                elif self.edit_mode == "library":
                    if event.key == pygame.K_UP:
                        if len(self.particle_library) > 0:
                            self.selected_preset = (self.selected_preset - 1) % len(self.particle_library)
                    elif event.key == pygame.K_DOWN:
                        if len(self.particle_library) > 0:
                            self.selected_preset = (self.selected_preset + 1) % len(self.particle_library)
                    elif event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                        if len(self.particle_library) > 0:
                            self.load_preset(self.particle_library[self.selected_preset])
                            self.create_particle_system()
                    elif event.key == pygame.K_l:
                        self.refresh_library()                        
                            

    def adjust_parameter(self, direction):

        params = self.get_current_params()
        param_list = self.get_current_param_list()
        
        if not param_list:
            return
        
        param_name = param_list[self.selected_param]
        value = params[param_name]
        
        # Shift para ajuste fino
        keys = pygame.key.get_pressed()
        fine = 0.1 if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) else 1.0
        
        if isinstance(value, bool):
            params[param_name] = not value
        elif isinstance(value, int):
            if 'burst' in param_name:
                params[param_name] += direction * int(10 * fine)
                params[param_name] = max(1, min(1000, params[param_name]))  # Mínimo 1
            elif 'size' in param_name:
                params[param_name] += direction * max(1, int(2 * fine))
                params[param_name] = max(1, min(128, params[param_name]))  # Mínimo 1
        elif isinstance(value, float):
            if 'angle' in param_name:
                params[param_name] += direction * (10 * fine)
                params[param_name] = params[param_name] % 360  # Wrap around 0-360
            elif 'radius' in param_name:
                params[param_name] += direction * (5 * fine)
                params[param_name] = max(0.0, min(1000, params[param_name]))
            elif 'min_velocity' in param_name or 'max_velocity' in param_name:
                params[param_name] += direction * (10 * fine)
                # Velocity pode ser 0, mas tem limite máximo
                params[param_name] = max(0.0, min(1000, params[param_name]))
            elif 'min_acceleration' in param_name or 'max_acceleration' in param_name:
                params[param_name] += direction * (10 * fine)
                # Acceleration pode ser 0 ou negativa em alguns casos
                params[param_name] = max(0.0, min(1000, params[param_name]))
            elif 'duration' in param_name or 'delay' in param_name:
                params[param_name] += direction * (0.1 * fine)
                # Duration pode ser 0.0 ou maior, mas delay precisa de mínimo
                if 'delay' in param_name:
                    params[param_name] = max(0.0, min(10, params[param_name]))
                else:
                    params[param_name] = max(0.1, min(10, params[param_name]))  # Min 0.1 para duration
            elif 'multiplier' in param_name:
                params[param_name] += direction * (0.1 * fine)
                params[param_name] = max(0.1, min(5, params[param_name]))
            elif 'ignore' in param_name:
                params[param_name] += direction * (0.1 * fine)
                # -1 significa desabilitado, então pode ser negativo
                params[param_name] = max(-1.0, min(10, params[param_name]))
            elif 'rate' in param_name:
                params[param_name] += direction * (10 * fine)
                params[param_name] = max(1.0, min(2000, params[param_name]))  # Mínimo 1
            elif 'strength' in param_name or 'gravity' in param_name.lower():
                params[param_name] += direction * (10 * fine)
                # Gravity/strength podem ser negativos (para cima/repelir)
                params[param_name] = max(-1000, min(1000, params[param_name]))
            elif 'reduction' in param_name:
                params[param_name] += direction * (5 * fine)
                params[param_name] = max(0.0, min(100, params[param_name]))
            elif 'attraction' in param_name:
                params[param_name] += direction * (50 * fine)
                params[param_name] = max(0.0, min(5000, params[param_name]))
            else:
                # Caso genérico para floats não especificados
                params[param_name] += direction * (1 * fine)
                params[param_name] = max(0.0, params[param_name])
        elif param_name == 'composition_mode':
            params[param_name] = (params[param_name] + direction) % 3
        elif param_name == 'particle_shape':
            params[param_name] = (params[param_name] + direction) % 2  # Alterna 0/1


    def render_ui(self):

        panel_width = 400
        pygame.draw.rect(self.screen, (20, 20, 30), (0, 0, panel_width, self.height))
        
        y_offset = 10
        
        # Título
        title = self.title_font.render("Editor de Partículas", True, (255, 255, 100))
        self.screen.blit(title, (10, y_offset))
        y_offset += 40
        
        # Modo atual
        mode_names = {
            "particle": "PARTÍCULA",
            "emitter": "EMISSOR",
            "affectors": "AFFECTORS",
            "colors": "CORES",
            "library": "BIBLIOTECA"       
            
        }
        mode_color = (100, 255, 100)
        mode_text = self.font.render(f"Modo: {mode_names[self.edit_mode]}", True, mode_color)
        self.screen.blit(mode_text, (10, y_offset))
        y_offset += 30
        
        # Renderiza conforme modo
        if self.edit_mode == "colors":
            self.render_color_editor(y_offset, panel_width)
        elif self.edit_mode == "library":  
            self.render_library_ui(y_offset, panel_width)
        else:                              
            self.render_parameter_editor(y_offset, panel_width)

        
        # Instruções gerais
        instructions = [
            "TAB: Trocar modo",
            "↑↓: Navegar",
            "←→: Ajustar",
            "Shift: Ajuste fino",
            "T: Textura",
            "F: Randomizar TUDO", 
            "L: Atualizar biblioteca",            
            "S: Salvar OTPS",
            "ESPAÇO: Testar",
            "C: Limpar",
        ]
        
        y = self.height - len(instructions) * 18 - 10
        for inst in instructions:
            text = self.small_font.render(inst, True, (100, 100, 100))
            self.screen.blit(text, (10, y))
            y += 18
        
        # Contador de partículas
        if self.particle_system:
            count = self.particle_system.get_particle_count()
            count_text = self.font.render(f"Partículas: {count}", True, (100, 255, 100))
            self.screen.blit(count_text, (self.width - 180, self.height - 40))

    def render_parameter_editor(self, y_offset, panel_width):

        params = self.get_current_params()
        param_list = self.get_current_param_list()
        
        comp_modes = ["normal", "additive", "multiply"]
        
        for i, key in enumerate(param_list):
            value = params[key]
            color = (255, 255, 0) if i == self.selected_param else (180, 180, 180)
            
            # Formata valor
            if isinstance(value, bool):
                value_str = "ON" if value else "OFF"
            elif isinstance(value, float):
                value_str = f"{value:.2f}"
            elif isinstance(value, int):
                value_str = str(value)
            elif key == 'composition_mode':
                value_str = comp_modes[value]
            else:
                value_str = str(value)
            
            # Nome formatado
            display_name = key.replace('_', ' ').title()
            if len(display_name) > 25:
                display_name = display_name[:22] + "..."
            
            text = self.small_font.render(f"{display_name}: {value_str}", True, color)
            self.screen.blit(text, (10, y_offset))
            y_offset += 20

    def render_color_editor(self, y_offset, panel_width):

        colors_title = self.font.render("Editor de Cores:", True, (255, 255, 255))
        self.screen.blit(colors_title, (10, y_offset))
        y_offset += 25
        
        channels = ['R', 'G', 'B', 'A']
        for i, color in enumerate(self.color_editor.colors):
            if i == self.color_editor.selected_color:
                pygame.draw.rect(self.screen, (255, 255, 255), 
                               (5, y_offset - 2, panel_width - 10, 54), 2)
            
            color_name = self.small_font.render(f"Cor {i+1}:", True, (200, 200, 200))
            self.screen.blit(color_name, (10, y_offset))
            y_offset += 18
            
            preview_rect = pygame.Rect(10, y_offset, 80, 30)
            pygame.draw.rect(self.screen, tuple(color), preview_rect)
            pygame.draw.rect(self.screen, (100, 100, 100), preview_rect, 1)
            
            for j, (ch, val) in enumerate(zip(channels, color)):
                ch_color = (255, 255, 0) if (i == self.color_editor.selected_color and 
                                              j == self.color_editor.selected_channel) else (150, 150, 150)
                ch_text = self.small_font.render(f"{ch}:{val:3d}", True, ch_color)
                self.screen.blit(ch_text, (100 + j * 70, y_offset + 8))
            
            y_offset += 40
            
            
    def render_library_ui(self, y_offset, panel_width):

        lib_title = self.font.render("Biblioteca de Presets:", True, (255, 255, 255))
        self.screen.blit(lib_title, (10, y_offset))
        y_offset += 30

        if len(self.particle_library) == 0:
            empty_text = self.small_font.render("Nenhum preset encontrado", True, (150, 150, 150))
            self.screen.blit(empty_text, (10, y_offset))
            y_offset += 20
            help_text = self.small_font.render("Salve com 'S' para criar presets", True, (100, 100, 100))
            self.screen.blit(help_text, (10, y_offset))
        else:
            info_text = self.small_font.render(f"Total: {len(self.particle_library)} presets", True, (100, 200, 100))
            self.screen.blit(info_text, (10, y_offset))
            y_offset += 25

            # Lista de presets
            max_display = 25  # Máximo de itens visíveis
            start_idx = max(0, self.selected_preset - 12)
            end_idx = min(len(self.particle_library), start_idx + max_display)

            for i in range(start_idx, end_idx):
                filename = self.particle_library[i]
                # Remover extensão para exibição
                display_name = filename[:-5] if filename.endswith('.otps') else filename

                # Truncar nome se muito longo
                if len(display_name) > 35:
                    display_name = display_name[:32] + "..."

                # Cor e marcador
                if i == self.selected_preset:
                    color = (255, 255, 0)
                    marker = "► "
                    # Desenhar fundo de seleção
                    pygame.draw.rect(self.screen, (40, 40, 60), 
                                   (5, y_offset - 2, panel_width - 10, 18))
                else:
                    color = (180, 180, 180)
                    marker = "  "

                text = self.small_font.render(f"{marker}{display_name}", True, color)
                self.screen.blit(text, (10, y_offset))
                y_offset += 18

            # Instruções específicas da biblioteca
            y_offset = self.height - 310
            lib_instructions = [
                "",
                "BIBLIOTECA:",
                "↑↓: Navegar presets",
                "ENTER: Carregar preset",
                "L: Atualizar lista",
                "S: Salvar preset atual",
            ]

            for inst in lib_instructions:
                if inst:
                    text = self.small_font.render(inst, True, (150, 150, 200))
                    self.screen.blit(text, (10, y_offset))
                y_offset += 18            

    def run(self):

        while self.running:
            self.handle_input()
            
            # Fundo com degradê
            for y in range(self.height):
                color_val = int(5 + (y / self.height) * 15)
                pygame.draw.line(self.screen, (color_val, color_val, color_val + 5),
                               (400, y), (self.width, y))
            
            # Sistema de partículas
            if self.particle_system:
                self.particle_system.update()
                self.particle_system.render(self.screen)
            
            # UI
            self.render_ui()
            
            # Cursor
            pygame.draw.circle(self.screen, (255, 0, 0), self.mouse_pos, 5, 2)
            pygame.draw.circle(self.screen, (255, 255, 255), self.mouse_pos, 7, 1)
            
            pygame.display.flip()
            self.clock.tick(60)
        
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    generator = ParticleGenerator()
    generator.run()
