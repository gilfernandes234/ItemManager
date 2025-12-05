from PIL import Image, ImageEnhance, ImageTk
import customtkinter as ctk
from tkinter import filedialog, messagebox, Canvas, NW
from collections import OrderedDict
import numpy as np
import subprocess
import os
import sys
import threading
import struct


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

METADATA_FLAGS = {
    0x00: ('Ground', '<H'), 0x01: ('GroundBorder', ''), 0x02: ('OnBottom', ''),
    0x03: ('OnTop', ''), 0x04: ('Container', ''), 0x05: ('Stackable', ''),
    0x06: ('ForceUse', ''), 0x07: ('MultiUse', ''), 0x08: ('Writable', '<H'),
    0x09: ('WritableOnce', '<H'), 0x0A: ('FluidContainer', ''), 0x0B: ('IsFluid', ''),
    0x0C: ('Unpassable', ''), 0x0D: ('Unmoveable', ''), 0x0E: ('BlockMissile', ''),
    0x0F: ('BlockPathfind', ''), 0x10: ('NoMoveAnimation', ''), 0x11: ('Pickupable', ''),
    0x12: ('Hangable', ''), 0x13: ('HookVertical', ''), 0x14: ('HookHorizontal', ''),
    0x15: ('Rotatable', ''), 0x16: ('HasLight', '<HH'), 0x17: ('DontHide', ''),
    0x18: ('Translucent', ''), 0x19: ('HasOffset', '<hh'), 0x1A: ('HasElevation', '<H'),
    0x1B: ('LyingObject', ''), 0x1C: ('AnimateAlways', ''), 0x1D: ('ShowOnMinimap', '<H'),
    0x1E: ('LensHelp', '<H'), 0x1F: ('FullGround', ''), 0x20: ('IgnoreLook', ''),
    0x21: ('IsCloth', '<H'), 0x22: ('MarketItem', None), 0x23: ('DefaultAction', '<H'),
    0x24: ('Wrappable', ''), 0x25: ('Unwrappable', ''), 0x26: ('TopEffect', ''),
    0x27: ('Usable', '')
}
REVERSE_METADATA_FLAGS = {info[0]: flag for flag, info in METADATA_FLAGS.items()}
LAST_FLAG = 0xFF

# ---------------------------
# Conversores de cor (índice 0–215 e legado 16-bit)
# ---------------------------
def ob_index_to_rgb(idx):
    idx = max(0, min(215, int(idx)))
    r = (idx % 6) * 51
    g = ((idx // 6) % 6) * 51
    b = ((idx // 36) % 6) * 51
    return r, g, b

def rgb16_to_ob_index(val):
    r = (val & 0x1F) << 3
    g = ((val >> 5) & 0x1F) << 3
    b = ((val >> 10) & 0x1F) << 3
    ri = round(r / 51)
    gi = round(g / 51)
    bi = round(b / 51)
    return max(0, min(215, ri + gi * 6 + bi * 36))

# ---------------------------
# Classe de manipulação do .dat (sem alterações significativas)
# ---------------------------
class DatEditor:
    def __init__(self, dat_path):
        self.dat_path = dat_path
        self.signature = 0
        self.counts = {'items': 0, 'outfits': 0, 'effects': 0, 'missiles': 0}
        self.things = {'items': {}, 'outfits_effects_missiles_raw': b''}

    def load(self):
        with open(self.dat_path, 'rb') as f:
            self.signature = struct.unpack('<I', f.read(4))[0]
            item_count, outfit_count, effect_count, missile_count = struct.unpack('<HHHH', f.read(8))
            self.counts = {'items': item_count, 'outfits': outfit_count, 'effects': effect_count, 'missiles': missile_count}
            for item_id in range(100, self.counts['items'] + 1):
                self.things['items'][item_id] = self._parse_thing(f)
            start_of_others = f.tell()
            f.seek(0, 2)
            end_of_file = f.tell()
            f.seek(start_of_others)
            self.things['outfits_effects_missiles_raw'] = f.read(end_of_file - start_of_others)

    def _parse_thing(self, f):
        props = OrderedDict()
        while True:
            byte = f.read(1)
            if not byte or byte[0] == LAST_FLAG:
                break
            flag = byte[0]
            if flag in METADATA_FLAGS:
                name, fmt = METADATA_FLAGS[flag]
                props[name] = True
                if fmt is None and name == 'MarketItem':
                    market_header = f.read(8)
                    name_len = struct.unpack('<H', market_header[6:8])[0]
                    market_body = f.read(name_len + 4)
                    props[name + '_data'] = market_header + market_body
                elif fmt:
                    size = struct.calcsize(fmt)
                    data = f.read(size)
                    props[name + '_data'] = struct.unpack(fmt, data)
        texture_block_start = f.tell()
        width, height = struct.unpack('<BB', f.read(2))
        texture_header_size = 2
        if width > 1 or height > 1:
            f.read(1)
            texture_header_size += 1
        layers, patternX, patternY, patternZ, frames = struct.unpack('<BBBBB', f.read(5))
        texture_header_size += 5
        total_sprites = width * height * patternX * patternY * patternZ * layers * frames
        anim_detail_size = 0
        if frames > 1:
            anim_detail_size = 1 + 4 + 1 + (frames * 8)
        texture_data_size = total_sprites * 4
        f.seek(texture_block_start)
        total_texture_block_size = texture_header_size + anim_detail_size + texture_data_size
        texture_bytes = f.read(total_texture_block_size)
        return {"props": props, "texture_bytes": texture_bytes}
        
        


    def apply_changes(self, item_ids, attributes_to_set, attributes_to_unset):
        for item_id in item_ids:
            if item_id not in self.things['items']:
                continue
            item_props = self.things['items'][item_id]['props']
            for attr in attributes_to_set:
                if attr in REVERSE_METADATA_FLAGS:
                    item_props[attr] = True
                    flag_val = REVERSE_METADATA_FLAGS[attr]
                    _name, fmt = METADATA_FLAGS[flag_val]
                    if fmt:
                        data_key = attr + '_data'
                        if data_key not in item_props:
                            num_bytes = struct.calcsize(fmt)
                            num_values = len(struct.unpack(fmt, b'\x00' * num_bytes))
                            item_props[data_key] = tuple([0] * num_values)
            for attr in attributes_to_unset:
                if attr in REVERSE_METADATA_FLAGS and attr in item_props:
                    del item_props[attr]
                    if attr + '_data' in item_props:
                        del item_props[attr + '_data']

    def save(self, output_path):
        with open(output_path, 'wb') as f:
            f.write(struct.pack('<I', self.signature))
            f.write(struct.pack('<HHHH', self.counts['items'], self.counts['outfits'], self.counts['effects'], self.counts['missiles']))
            for item_id in range(100, self.counts['items'] + 1):
                item = self.things['items'][item_id]
                self._write_thing_properties(f, item['props'])
                f.write(item['texture_bytes'])
            f.write(self.things['outfits_effects_missiles_raw'])

    def _write_thing_properties(self, f, props):
        for flag, (name, fmt) in METADATA_FLAGS.items():
            if name in props and props[name]:
                f.write(struct.pack('<B', flag))
                data_key = name + '_data'
                if data_key in props:
                    data = props[data_key]
                    if fmt:
                        f.write(struct.pack(fmt, *data))
                    else:
                        # market raw
                        f.write(data)
        f.write(struct.pack('<B', LAST_FLAG))

    # util: extrai lista de sprite IDs a partir do texture_bytes (levando em conta header)
    @staticmethod
    def extract_sprite_ids_from_texture_bytes(texture_bytes):
        if not texture_bytes or len(texture_bytes) < 2:
            return []
        try:
            offset = 0
            width, height = struct.unpack_from('<BB', texture_bytes, offset)
            offset += 2
            if width > 1 or height > 1:
                offset += 1  # skip byte
            layers, px, py, pz, frames = struct.unpack_from('<BBBBB', texture_bytes, offset)
            offset += 5
            total_sprites = width * height * px * py * pz * layers * frames
            # skip anim block if present
            anim_offset = 0
            if frames > 1:
                # approximate: 1 + 4 + 1 + (frames * 8)
                anim_offset = 1 + 4 + 1 + (frames * 8)
            offset += anim_offset
            sprite_ids = []
            for i in range(total_sprites):
                if offset + 4 <= len(texture_bytes):
                    spr_id = struct.unpack_from('<I', texture_bytes, offset)[0]
                    sprite_ids.append(spr_id)
                    offset += 4
                else:
                    break
            return sprite_ids
        except Exception:
            return []

# ---------------------------
# SPR Reader (best-effort para 10.98)
# ---------------------------
class SprReader:
    """
    Leitor 'best-effort' para Tibia.spr 10.98:
    - Lê header (signature, count, offsets)
    - Para cada sprite tenta:
      1) interpretar como bloco não-comprimido (width,height + raw RGBA 32-bit)
      2) se falhar, tenta decoder RLE com pares (transparent u16, colored u16) e cores 3 bytes (RGB)
    Retorna PIL.Image ou None se não conseguiu.
    """
    def __init__(self, spr_path):
        self.spr_path = spr_path
        self.signature = 0
        self.sprite_count = 0
        self.offsets = []
        self._f = None

    def load(self):
        self._f = open(self.spr_path, 'rb')
        f = self._f
        f.seek(0)
        header = f.read(8)
        if len(header) < 8:
            raise ValueError("Arquivo SPR inválido ou truncado.")
        self.signature, self.sprite_count = struct.unpack('<II', header)
        # offsets table (sprite_count entries)
        self.offsets = []
        for _ in range(self.sprite_count):
            data = f.read(4)
            if len(data) < 4:
                self.offsets.append(0)
            else:
                self.offsets.append(struct.unpack('<I', data)[0])

    def close(self):
        if self._f:
            self._f.close()
            self._f = None

    def get_sprite(self, sprite_id):
        """
        Tenta decodificar a sprite testando múltiplas variantes de cabeçalho e formato de cor.
        Ideal para SPRs customizados (OTClient/Mehah) onde o formato exato varia.
        """
        if not self._f or sprite_id <= 0 or sprite_id > self.sprite_count:
            return None
        
        offset = self.offsets[sprite_id - 1]
        if offset == 0:
            return None
            
        # 1. Calcular tamanho do bloco
        next_offset = 0
        for i in range(sprite_id, self.sprite_count):
            if self.offsets[i] != 0:
                next_offset = self.offsets[i]
                break
        
        self._f.seek(0, 2)
        file_size = self._f.tell()
        size = (next_offset - offset) if (next_offset > offset) else (file_size - offset)
        
        if size <= 4: # Muito pequeno
            return None

        self._f.seek(offset)
        raw_data = self._f.read(size)

        # --- Tentativas de Decodificação ---
        # Tenta diferentes "pulos" iniciais (skips) para achar o cabeçalho W/H correto
        # Skip 0: Formato Padrão (W, H, RLE)
        # Skip 2: Formato Extended/OTC (Size, W, H, RLE)
        # Skip 3: Formato Legado/Modificado (ColorKey, Size, W, H...)
        
        # Lista de tentativas: (bytes_to_skip, bytes_per_pixel)
        # Ordem: Tenta RGBA (OTC) primeiro, depois RGB (Standard)
        attempts = [
            (0, 4), # RGBA Direto
            (2, 4), # RGBA com Header de Tamanho (2 bytes)
            (0, 3), # RGB Direto
            (2, 3), # RGB com Header de Tamanho
            (3, 3), # RGB com ColorKey + Tamanho (Raro)
            (1, 3)  # RGB com apenas ColorKey (Legacy 7.x-8.x)
        ]

        for skip, bpp in attempts:
            img = self._decode_variant(raw_data, skip, bpp)
            if img:
                return img
        
        return None

    def _decode_variant(self, data, skip_bytes, bpp):
        """
        Helper que tenta decodificar com parametros específicos.
        Retorna Image ou None se falhar.
        """
        try:
            if len(data) < skip_bytes + 4: return None
            
            p = skip_bytes
            
            # Ler dimensões
            w, h = struct.unpack_from('<HH', data, p)
            p += 4
            
            # Validação Rápida de Sanidade
            # Sprites do Tibia geralmente são 32x32 ou múltiplos pequenos (64x64).
            # Se vier algo gigante (ex: 24500x1200), o offset/skip está errado.
            if w == 0 or h == 0 or w > 128 or h > 128:
                return None

            total_pixels = w * h
            # Limite de segurança para alocação
            if total_pixels > 16384: # 128x128
                return None

            img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            pixels = img.load()
            
            x = 0
            y = 0
            drawn = 0
            
            while p < len(data) and drawn < total_pixels:
                # Header do Chunk RLE: Transparente (2) + Colorido (2)
                if p + 4 > len(data): break
                
                transparent, colored = struct.unpack_from('<HH', data, p)
                p += 4
                
                # Avança pixels transparentes
                drawn += transparent
                for _ in range(transparent):
                    x += 1
                    if x >= w:
                        x = 0
                        y += 1

                # Valida se há bytes suficientes para os pixels coloridos
                if p + (colored * bpp) > len(data):
                    return None # Chunk corrompido ou formato errado
                
                # Lê pixels coloridos
                for _ in range(colored):
                    if y >= h: break
                    
                    r = data[p]
                    g = data[p+1]
                    b = data[p+2]
                    a = data[p+3] if bpp == 4 else 255 # Alpha 255 se for RGB
                    
                    pixels[x, y] = (r, g, b, a)
                    p += bpp
                    
                    x += 1
                    drawn += 1
                    if x >= w:
                        x = 0
                        y += 1
            
            # Critério de sucesso: Desenhamos algo coerente?
            # Se "drawn" for muito maior que total_pixels, algo deu errado no loop (mas temos checks)
            # Se a imagem foi gerada sem exceções, assumimos sucesso.
            return img

        except Exception:
            return None



# Base path do script ou EXE
if getattr(sys, 'frozen', False):
    base_path = os.path.dirname(sys.executable)
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

WAIFU_EXE = os.path.join(base_path, "waifu2x-caffe", "waifu2x-caffe-cui.exe")




class ImageUpscaleApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Item Manager")
        self.geometry("900x1000")
        self.after(1, self.state, 'zoomed')
        
    
        

        icon_path = os.path.join(base_path, "ItemManagerIco.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
            
        # ---------------------------------------
        # 1️⃣ Criar TABVIEW PRINCIPAL
        # ---------------------------------------
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.pack(fill="both", expand=True, padx=10, pady=10)

        # Criar abas
        self.tab_manager = self.tab_view.add("Sprite Editor")
        self.tab_sprdat = self.tab_view.add("Spr/Dat Editor")

        # Construir interface da aba Sprite Manager
        self.build_sprite_manager_ui(self.tab_manager)
        
         # Construir interface da aba Spr/Dat Editor
        self.build_dat_editor_ui(self.tab_sprdat)


    # ===========================================================
    # FUNÇÃO QUE MONTA TODA A ABA "SPRITE MANAGER"
    # ===========================================================
   
    def build_sprite_manager_ui(self, parent):

        # Frame principal do Sprite Manager
        self.frame = ctk.CTkFrame(parent, corner_radius=10)
        self.frame.pack(padx=10, pady=0, fill="x")

        # Pasta
        ctk.CTkLabel(self.frame, text="Path:").pack(pady=0)
        self.path_entry = ctk.CTkEntry(self.frame, placeholder_text="Choose a folder...")
        self.path_entry.pack(padx=10, pady=0, fill="x")
        ctk.CTkButton(self.frame, text="Search Folder", command=self.select_folder).pack(pady=5)

        # Ajustes avançados
        self.create_advanced_adjustments(self.frame)

        # Controles Denoise / Upscale
        self.create_denoise_upscale_controls(self.frame)

        ctk.CTkButton(
            parent,
            text="Apply",
            height=25,
            font=("Arial", 16),
            fg_color="#ff9326",
            hover_color="#ffa64c",
            command=self.convert_images_thread
        ).pack(pady=5)

        # Frames para log e imagens
        self.create_display_frames(parent)

        self.status = ctk.CTkLabel(parent, text="Finish!", text_color="lightgreen")
        self.status.pack(pady=5)

    # ------------------- GUI Helpers -------------------
    def create_advanced_adjustments(self, parent):
        adv_frame = ctk.CTkFrame(parent, corner_radius=10)
        adv_frame.pack(padx=10, pady=2, fill="x")
        ctk.CTkLabel(adv_frame, text="Advanced").pack(pady=5)

        # Brilho, Contraste, Cor
        self.brightness_slider = ctk.CTkSlider(adv_frame, from_=0, to=2, number_of_steps=20)
        self.brightness_slider.set(1.0)
        ctk.CTkLabel(adv_frame, text="Bright").pack()
        self.brightness_slider.pack(padx=10, pady=2, fill="x")

        self.contrast_slider = ctk.CTkSlider(adv_frame, from_=0, to=2, number_of_steps=20)
        self.contrast_slider.set(1.0)
        ctk.CTkLabel(adv_frame, text="Contrast").pack()
        self.contrast_slider.pack(padx=10, pady=2, fill="x")

        self.color_slider = ctk.CTkSlider(adv_frame, from_=0, to=2, number_of_steps=20)
        self.color_slider.set(1.0)
        ctk.CTkLabel(adv_frame, text="Saturation").pack()
        self.color_slider.pack(padx=10, pady=2, fill="x")

        # Rotação
        self.rotate_slider = ctk.CTkSlider(adv_frame, from_=0, to=360, number_of_steps=36)
        self.rotate_slider.set(0)
        ctk.CTkLabel(adv_frame, text="Rotation:").pack()
        self.rotate_slider.pack(padx=10, pady=2, fill="x")

        # Ajustes RGB
        self.red_slider = ctk.CTkSlider(adv_frame, from_=0, to=2, number_of_steps=20)
        self.red_slider.set(1.0)
        ctk.CTkLabel(adv_frame, text="Red").pack()
        self.red_slider.pack(padx=10, pady=2, fill="x")

        self.green_slider = ctk.CTkSlider(adv_frame, from_=0, to=2, number_of_steps=20)
        self.green_slider.set(1.0)
        ctk.CTkLabel(adv_frame, text="Green").pack()
        self.green_slider.pack(padx=10, pady=2, fill="x")

        self.blue_slider = ctk.CTkSlider(adv_frame, from_=0, to=2, number_of_steps=20)
        self.blue_slider.set(1.0)
        ctk.CTkLabel(adv_frame, text="Blue").pack()
        self.blue_slider.pack(padx=10, pady=2, fill="x")

        # Flips
        self.flip_horizontal = ctk.CTkSwitch(adv_frame, text="Mirror Horizontal")
        self.flip_horizontal.pack(padx=10, pady=2)
        self.flip_vertical = ctk.CTkSwitch(adv_frame, text="Mirror Vertical")
        self.flip_vertical.pack(padx=10, pady=2)

    def create_denoise_upscale_controls(self, parent):
        controls_frame = ctk.CTkFrame(parent, corner_radius=10)
        controls_frame.pack(padx=10, pady=5, fill="x")

        # Denoise
        denoise_frame = ctk.CTkFrame(controls_frame)
        denoise_frame.pack(side="left", padx=10, pady=5)
        ctk.CTkLabel(denoise_frame, text="Denoise").pack(side="left")
        self.use_denoise = ctk.CTkSwitch(denoise_frame, text="", width=30)
        self.use_denoise.pack(side="left", padx=5)
        self.denoise_level = ctk.CTkComboBox(denoise_frame, values=["0", "1", "2", "3"], width=50)
        self.denoise_level.set("1")
        self.denoise_level.pack(side="left", padx=5)

        # Upscale
        upscale_frame = ctk.CTkFrame(controls_frame)
        upscale_frame.pack(side="left", padx=10, pady=5)
        ctk.CTkLabel(upscale_frame, text="Upscale").pack(side="left")
        self.use_upscale = ctk.CTkSwitch(upscale_frame, text="", width=30)
        self.use_upscale.pack(side="left", padx=5)
        self.upscale_factor = ctk.CTkComboBox(upscale_frame, values=["2", "4", "8"], width=50)
        self.upscale_factor.set("2")
        self.upscale_factor.pack(side="left", padx=5)

        # Resize
        resize_frame = ctk.CTkFrame(controls_frame)
        resize_frame.pack(side="left", padx=10, pady=5)
        ctk.CTkLabel(resize_frame, text="Resize").pack(side="left")
        self.use_resize = ctk.CTkSwitch(resize_frame, text="", width=30)
        self.use_resize.pack(side="left", padx=5)
        self.resize_output = ctk.CTkComboBox(resize_frame, values=["32", "64", "128", "240", "256", "512"], width=60)
        self.resize_output.set("32")
        self.resize_output.pack(side="left", padx=5)

        # Custom Resize
        custom_resize_frame = ctk.CTkFrame(controls_frame)
        custom_resize_frame.pack(side="left", padx=10, pady=5)

        ctk.CTkLabel(custom_resize_frame, text="Custom Size").pack(side="left")

        self.use_custom_resize = ctk.CTkSwitch(custom_resize_frame, text="", width=30)
        self.use_custom_resize.pack(side="left", padx=5)

        self.custom_width = ctk.CTkEntry(custom_resize_frame, placeholder_text="W", width=55)
        self.custom_width.pack(side="left", padx=2)

        self.custom_height = ctk.CTkEntry(custom_resize_frame, placeholder_text="H", width=55)
        self.custom_height.pack(side="left", padx=2)

    def create_display_frames(self, parent):
        main_display_frame = ctk.CTkFrame(parent, corner_radius=2)
        main_display_frame.pack(padx=10, pady=0, fill="both", expand=True)
        main_display_frame.grid_columnconfigure(0, weight=1)
        main_display_frame.grid_columnconfigure(1, weight=1)
        main_display_frame.grid_columnconfigure(2, weight=1)

        # Log
        log_frame = ctk.CTkFrame(main_display_frame, corner_radius=2)
        log_frame.grid(row=0, column=0, padx=5, pady=0, sticky="nsew")
        ctk.CTkLabel(log_frame, text="Log:").pack()
        self.log_box = ctk.CTkTextbox(log_frame, height=10)
        self.log_box.pack(padx=5, pady=5, fill="both", expand=True)

        # Input
        input_frame = ctk.CTkFrame(main_display_frame, corner_radius=2)
        input_frame.grid(row=0, column=1, padx=5, pady=0, sticky="nsew")
        ctk.CTkLabel(input_frame, text="Main Folder:").pack()
        self.input_scroll = ctk.CTkScrollableFrame(input_frame, height=0)
        self.input_scroll.pack(padx=5, pady=5, fill="both", expand=True)

        # Output
        output_frame = ctk.CTkFrame(main_display_frame, corner_radius=2)
        output_frame.grid(row=0, column=2, padx=5, pady=0, sticky="nsew")
        ctk.CTkLabel(output_frame, text="Output:").pack()
        self.output_scroll = ctk.CTkScrollableFrame(output_frame, height=0)
        self.output_scroll.pack(padx=5, pady=5, fill="both", expand=True)

    # ------------------- Funcionalidades -------------------
    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)
            self.show_images(folder)

    def show_images(self, folder):
        # Limpa os widgets antigos
        for widget in self.input_scroll.winfo_children():
            widget.destroy()
        for widget in self.output_scroll.winfo_children():
            widget.destroy()

        self.input_photos = []
        self.output_photos = []

        # Mostrar INPUTS
        for file in os.listdir(folder):
            if file.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                path = os.path.join(folder, file)
                img = Image.open(path)

                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(100, 100))
                self.input_photos.append(ctk_img)

                label = ctk.CTkLabel(self.input_scroll, image=ctk_img, text="")
                label.pack(pady=5)

        # Mostrar OUTPUTS
        out_folder = os.path.join(folder, "output_processed")
        if os.path.isdir(out_folder):
            for file in os.listdir(out_folder):
                if file.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                    path = os.path.join(out_folder, file)
                    img = Image.open(path)

                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(50, 50))
                    self.output_photos.append(ctk_img)

                    label = ctk.CTkLabel(self.output_scroll, image=ctk_img, text="")
                    label.pack(pady=5)

    def log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    # ------------------- Ajustes Pillow -------------------
    def process_pillow_image(self, img):
        img = ImageEnhance.Brightness(img).enhance(self.brightness_slider.get())
        img = ImageEnhance.Contrast(img).enhance(self.contrast_slider.get())
        img = ImageEnhance.Color(img).enhance(self.color_slider.get())

        img_np = np.array(img).astype(np.float32)

        # Ajustes RGB
        img_np[..., 0] = np.clip(img_np[..., 0] * self.red_slider.get(), 0, 255)
        img_np[..., 1] = np.clip(img_np[..., 1] * self.green_slider.get(), 0, 255)
        img_np[..., 2] = np.clip(img_np[..., 2] * self.blue_slider.get(), 0, 255)

        img = Image.fromarray(img_np.astype(np.uint8))

        angle = self.rotate_slider.get()
        if angle != 0:
            img = img.rotate(angle, expand=True)
        if self.flip_horizontal.get():
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        if self.flip_vertical.get():
            img = img.transpose(Image.FLIP_TOP_BOTTOM)

        return img

    def convert_images_thread(self):
        threading.Thread(target=self.convert_images, daemon=True).start()

    def convert_images(self):
        folder = self.path_entry.get().strip()
        if not os.path.isdir(folder):
            messagebox.showerror("Error", "Select a valid folder!")
            return

        denoise_enabled = self.use_denoise.get()
        upscale_enabled = self.use_upscale.get()
        resize_enabled = self.use_resize.get()
        denoise_level = self.denoise_level.get()
        upscale_factor = self.upscale_factor.get()
        resize_final = int(self.resize_output.get())

        custom_resize_enabled = self.use_custom_resize.get()
        custom_w = self.custom_width.get()
        custom_h = self.custom_height.get()

        if custom_resize_enabled:
            try:
                custom_w = int(custom_w)
                custom_h = int(custom_h)
            except:
                messagebox.showerror("Error", "Invalid Custom Resize values! Use only numbers.")
                return

        if not denoise_enabled and not upscale_enabled and not resize_enabled:
            messagebox.showerror("Error", "Select at least one option!")
            return
        if (denoise_enabled or upscale_enabled) and not os.path.isfile(WAIFU_EXE):
            messagebox.showerror("Erro", f"File not found:\n{WAIFU_EXE}")
            return

        out_folder = os.path.join(folder, "output_processed")
        os.makedirs(out_folder, exist_ok=True)
        count = 0

        files_to_process = [f for f in os.listdir(folder) if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))]

        for file in files_to_process:
            input_path = os.path.join(folder, file)
            temp_output = os.path.join(out_folder, "temp_" + file)
            final_output = os.path.join(out_folder, file)
            src = input_path

            self.log(f"Processing: {file}")

            if denoise_enabled:
                cmd = [WAIFU_EXE, "-i", src, "-o", temp_output, "-s", "1", "-m", "noise", "-n", denoise_level, "-p", "cpu"]
                subprocess.run(cmd)
                src = temp_output

            if upscale_enabled:
                cmd = [WAIFU_EXE, "-i", src, "-o", temp_output, "-s", upscale_factor, "-m", "noise_scale", "-n", denoise_level, "-p", "cpu"]
                subprocess.run(cmd)
                src = temp_output

            img = Image.open(src)

            if custom_resize_enabled:
                img = img.resize((custom_w, custom_h), Image.NEAREST)
            elif resize_enabled:
                img = img.resize((resize_final, resize_final), Image.NEAREST)

            img = self.process_pillow_image(img)
            img.save(final_output)

            if os.path.exists(temp_output):
                os.remove(temp_output)

            count += 1

        self.show_images(folder)
        self.status.configure(text=f"Completed! {count} processed images.")
        messagebox.showinfo("Ready", f"{count} Images were successfully generated!")
      


    # ===========================================================
    # FUNÇÃO QUE MONTA TODA A ABA "DAT/EDITOR"
    # ===========================================================      
        
       
    def build_dat_editor_ui(self, parent):
        """Constrói a interface completa do editor DAT/SPR na aba correspondente."""



        self.editor = None
        self.spr = None
        self.current_ids = []
        self.checkboxes = {}
        self.minimap_color_index = None
        self.tk_images_cache = {}  # para evitar GC de PhotoImage

  
        # LISTA LATERAL DE IDS (scroll)
        self.ids_list_frame = ctk.CTkScrollableFrame(parent, label_text="List", border_width=1, border_color="gray30")        
        self.ids_list_frame.pack(side="left", padx=10, pady=10, fill="y")

        self.id_buttons = {}
        self.ids_per_page = 250
        self.current_page = 0

        # Top Frame
        self.top_frame = ctk.CTkFrame(parent)
        self.top_frame.pack(padx=10, pady=10, fill="x")
        
        
        self.bottom_frame = ctk.CTkFrame(parent, border_width=1, border_color="gray30")
        self.bottom_frame.pack(padx=10, pady=10, fill="x")

        # Frame para operações de ID (Inserir/Apagar)
        id_operations_frame = ctk.CTkFrame(self.bottom_frame)
        id_operations_frame.pack(side="left", padx=10, pady=10)

        ctk.CTkLabel(id_operations_frame, text="Manage IDs:").pack(side="left", padx=(0, 5))

        self.id_operation_entry = ctk.CTkEntry(
            id_operations_frame,
            placeholder_text="ID (ex: 100-105)",
            width=120
        )
        self.id_operation_entry.pack(side="left", padx=5)

        self.insert_id_button = ctk.CTkButton(
            id_operations_frame,
            text="Insert ID",
            command=self.insert_ids,
            width=90,
            fg_color="#99ff99",
            hover_color="#bfffbf"
        )
        self.insert_id_button.pack(side="left", padx=5)

        self.delete_id_button = ctk.CTkButton(
            id_operations_frame,
            text="Delete ID",
            command=self.delete_ids,
            width=90,
            fg_color="#ff9673",
            hover_color="#ffcfbf"
        )
        self.delete_id_button.pack(side="left", padx=5)        
                
        
        self.load_dat_button = ctk.CTkButton(
            self.top_frame, 
            text="Load dat/spr (10.98)", 
            command=self.load_dat_file
        )
        self.load_dat_button.pack(side="left", padx=5)
        
        self.file_label = ctk.CTkLabel(
            self.top_frame, 
            text="Nenhum arquivo carregado.", 
            text_color="gray"
        )
        self.file_label.pack(side="left", padx=10, expand=True, fill="x")

        # ID Frame
        self.id_frame = ctk.CTkFrame(parent, border_width=1, border_color="gray30")        
        self.id_frame.pack(padx=10, pady=(0,10), fill="x")
        
        ctk.CTkLabel(self.id_frame, text="ID: (Ex: 100, 105-110):").pack(side="left", padx=5)
        
        self.id_entry = ctk.CTkEntry(
            self.id_frame, 
            placeholder_text="Insira os IDs dos itens aqui"
        )    
        self.id_entry.pack(side="left", padx=10,pady=10, expand=True, fill="x")
        self.id_entry.bind("<Return>", lambda event: self.load_ids_from_entry())
        
        self.load_ids_button = ctk.CTkButton(
            self.id_frame, 
            text="Search ID", 
            command=self.load_ids_from_entry, 
            width=100
        )
        self.load_ids_button.pack(side="left", padx=5)

        # Atributos (Flags)
        self.attributes_frame = ctk.CTkScrollableFrame(parent, label_text="Flags", border_width=1, border_color="gray30")
        self.attributes_frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        attr_names = sorted(REVERSE_METADATA_FLAGS.keys())
        num_attrs = len(attr_names)
        items_per_col = (num_attrs + 2) // 3
        
        for i, attr_name in enumerate(attr_names):
            row = i % items_per_col
            col = i // items_per_col
            cb = ctk.CTkCheckBox(self.attributes_frame, text=attr_name)
            cb.grid(row=row, column=col, padx=10, pady=5, sticky="w")
            self.checkboxes[attr_name] = cb

        # Frame para atributos numéricos
        self.numeric_attrs_frame = ctk.CTkFrame(parent, border_width=1, border_color="gray30")
        self.numeric_attrs_frame.pack(padx=10, pady=5, fill="x")

        self.numeric_entries = {}
        self.numeric_previews = {}

        attrs_config = [
            ("Minimap (0-215):", "ShowOnMinimap", True, "color"),
            ("Elevation:", "HasElevation", False, None),
            ("Ground Speed:", "Ground", False, None),
            ("Offset X:", "HasOffset_X", False, None),
            ("Offset Y:", "HasOffset_Y", False, None),
            ("Light Level:", "HasLight_Level", False, None),
            ("Light Color:", "HasLight_Color", True, "color")
        ]

        row = 0
        for label_text, attr_name, has_preview, preview_type in attrs_config:
            ctk.CTkLabel(
                self.numeric_attrs_frame, 
                text=label_text, 
                width=120, 
                anchor="w"
            ).grid(row=row, column=0, padx=5, pady=3, sticky="w")
            
            entry = ctk.CTkEntry(self.numeric_attrs_frame, width=80)
            entry.grid(row=row, column=1, padx=5, pady=3)
            self.numeric_entries[attr_name] = entry
            
            if has_preview and preview_type == "color":
                preview = ctk.CTkLabel(
                    self.numeric_attrs_frame, 
                    text="   ", 
                    width=40, 
                    fg_color="black"
                )
                preview.grid(row=row, column=2, padx=5, pady=3)
                self.numeric_previews[attr_name] = preview
                entry.bind(
                    "<KeyRelease>", 
                    lambda e, attr=attr_name: self.update_color_preview(attr)
                )
            
            row += 1

        # Spr preview area (direita)
        self.preview_frame = ctk.CTkFrame(parent, border_width=1, border_color="gray30")
        self.preview_frame.pack(side="right", padx=10, pady=10, fill="both", expand=False)
        
        ctk.CTkLabel(self.preview_frame, text="Preview").pack(pady=(6,0))
        
        self.canvas = Canvas(self.preview_frame, width=150, height=135, bg="#303030")
        self.canvas.pack(padx=6, pady=6)
        
        self.prev_controls = ctk.CTkFrame(self.preview_frame)
        self.prev_controls.pack(padx=6, pady=6, fill="x")
        
        self.prev_index_label = ctk.CTkLabel(self.prev_controls, text="Sprite 0 / 0")
        self.prev_index_label.pack(side="left", padx=4)
        
        self.prev_prev_btn = ctk.CTkButton(
            self.prev_controls, 
            text="<", 
            width=30, 
            command=lambda: self.change_preview_index(-1)
        )
        self.prev_prev_btn.pack(side="left", padx=4)
        
        self.prev_next_btn = ctk.CTkButton(
            self.prev_controls, 
            text=">", 
            width=30, 
            command=lambda: self.change_preview_index(1)
        )
        self.prev_next_btn.pack(side="left", padx=4)
        
        self.preview_info = ctk.CTkLabel(
            self.preview_frame, 
            text="Nenhuma sprite carregada.", 
            wraplength=250, 
            justify="left"
        )
        self.preview_info.pack(padx=6, pady=(0,6))

        # Bottom
# Bottom Frame
        self.bottom_frame = ctk.CTkFrame(parent, border_width=1, border_color="gray30")
        self.bottom_frame.pack(padx=10, pady=10, fill="x")

        # Adicione pady=10 (vertical) e padx=10 (horizontal) para desgrudar da borda
        self.apply_button = ctk.CTkButton(
            self.bottom_frame, 
            text="Save item flags", 
            command=self.apply_changes
        )
        self.apply_button.pack(side="left", padx=10, pady=10) # <--- Mude aqui

        self.save_button = ctk.CTkButton(
            self.bottom_frame, 
            text="Compile as...", 
            command=self.save_dat_file
        )
        self.save_button.pack(side="left", padx=10, pady=10) # <--- Mude aqui

        self.status_label = ctk.CTkLabel(
            self.bottom_frame, 
            text="Finish.", 
            anchor="w"
        )
        # Aqui o pady também afasta o texto da borda
        self.status_label.pack(side="left", padx=10, pady=10, expand=True, fill="x") 


        self.disable_editing()
        
        
        
        
    def insert_ids(self):
        """Insere novos IDs no arquivo dat."""
        if not self.editor:
            messagebox.showwarning("Aviso", "Carregue um arquivo .dat primeiro.")
            return
        
        id_string = self.id_operation_entry.get().strip()
        if not id_string:
            messagebox.showwarning("Aviso", "Digite os IDs que deseja inserir.")
            return
        
        ids_to_insert = self.parse_ids(id_string)
        if not ids_to_insert:
            messagebox.showerror("Erro", "Formato de ID inválido.")
            return
        
        # Validação: IDs devem ser sequenciais ao final
        max_current_id = self.editor.counts['items']
        
        inserted_count = 0
        for new_id in ids_to_insert:
            if new_id in self.editor.things['items']:
                continue  # ID já existe, pular
            
            # texture mínimo válido: 1 sprite vazio
            empty_texture = (
                b"\x01"  # width
                b"\x01"  # height
                b"\x01"  # layers
                b"\x01"  # patternX
                b"\x01"  # patternY
                b"\x01"  # patternZ
                b"\x01"  # frames
                b"\x00\x00\x00\x00"  # sprite ID vazio
            )

            empty_item = {
                "props": OrderedDict(),
                "texture_bytes": empty_texture
            }

            empty_item = {
                "props": OrderedDict(),
                "texture_bytes": empty_texture
            }
            self.editor.things['items'][new_id] = empty_item
            inserted_count += 1
            
            # Atualizar contador se necessário
            if new_id > self.editor.counts['items']:
                self.editor.counts['items'] = new_id
        
        if inserted_count > 0:
            self.status_label.configure(
                text=f"{inserted_count} ID(s) inserido(s) com sucesso.",
                text_color="green"
            )
            self.refresh_id_list()
            self.id_operation_entry.delete(0, "end")
        else:
            self.status_label.configure(
                text="Nenhum ID novo foi inserido (já existem).",
                text_color="yellow"
            )

    def delete_ids(self):
        """Remove IDs e re-organiza os índices para evitar corrupção."""
        if not self.editor:
            messagebox.showwarning("Aviso", "Carregue um arquivo .dat primeiro.")
            return
        
        id_string = self.id_operation_entry.get().strip()
        if not id_string:
            messagebox.showwarning("Aviso", "Digite os IDs que deseja deletar.")
            return
        
        ids_to_delete = self.parse_ids(id_string)
        if not ids_to_delete:
            return
        

        confirm = messagebox.askyesno(
            "Confirmar Exclusão",
            f"Isso irá remover {len(ids_to_delete)} itens e REINDEXAR todos os itens subsequentes.\n"
            "IDs de itens posteriores mudarão. Deseja continuar?"
        )
        
        if not confirm:
            return

        # Set para busca rápida
        delete_set = set(ids_to_delete)
        new_items = {}
        current_new_id = 100
        
        # Reconstrói a lista de itens sequencialmente, pulando os deletados
        old_max = self.editor.counts['items']
        for old_id in range(100, old_max + 1):
            if old_id in self.editor.things['items']:
                if old_id not in delete_set:
                    new_items[current_new_id] = self.editor.things['items'][old_id]
                    current_new_id += 1
                # Se estiver no delete_set, simplesmente ignoramos (não incrementa current_new_id)

        # Atualiza o editor
        self.editor.things['items'] = new_items
        new_count = current_new_id - 1
        deleted_count = self.editor.counts['items'] - new_count
        self.editor.counts['items'] = new_count

        self.status_label.configure(
            text=f"{deleted_count} itens removidos. IDs reindexados até {new_count}.",
            text_color="orange"
        )
        
        # Limpa a interface
        self.refresh_id_list()
        self.id_operation_entry.delete(0, "end")
        self.id_entry.delete(0, "end")
        self.clear_preview()

            
        
    def update_color_preview(self, attr_name):
        """Atualiza o preview de cor quando o usuário digita."""
        entry = self.numeric_entries.get(attr_name)
        preview = self.numeric_previews.get(attr_name)
        
        if not entry or not preview:
            return
        
        try:
            val = entry.get().strip()
            if not val:
                preview.configure(fg_color="black")
                return
                
            idx = int(val)
            
            if attr_name == "ShowOnMinimap":
                # Validação 0-215
                if 0 <= idx <= 215:
                    r, g, b = ob_index_to_rgb(idx)
                    preview.configure(fg_color=f"#{r:02x}{g:02x}{b:02x}")
                else:
                    preview.configure(fg_color="red")
            elif attr_name == "HasLight_Color":
                # Conversão de índice 16-bit para RGB
                if 0 <= idx <= 65535:
                    r, g, b = self.light_color_to_rgb(idx)
                    preview.configure(fg_color=f"#{r:02x}{g:02x}{b:02x}")
                else:
                    preview.configure(fg_color="red")
        except ValueError:
            preview.configure(fg_color="gray")

    def light_color_to_rgb(self, color_val):
        """Converte valor de cor de luz (RGB555/RGB565) para RGB888."""
        # Assumindo RGB555 (5 bits cada)
        r = ((color_val & 0x1F) << 3)
        g = (((color_val >> 5) & 0x1F) << 3)
        b = (((color_val >> 10) & 0x1F) << 3)
        return r, g, b
            
            
        
    def refresh_id_list(self):
        # limpa widgets anteriores
        for widget in self.ids_list_frame.winfo_children():
            widget.destroy()

        self.id_buttons.clear()

        total = self.editor.counts['items']
        start = self.current_page * self.ids_per_page + 100
        end = min(start + self.ids_per_page, total + 1)

        # cria os labels clicáveis
        for item_id in range(start, end):
            lbl = ctk.CTkLabel(
                self.ids_list_frame,
                text=str(item_id),
                fg_color=("gray15", "gray25"),
                width=120
            )
            lbl.pack(pady=1, fill="x")
            lbl.bind("<Button-1>", lambda e, iid=item_id: self.load_single_id(iid))
            self.id_buttons[item_id] = lbl

        # botões de paginação
        nav_frame = ctk.CTkFrame(self.ids_list_frame)
        nav_frame.pack(pady=10)

        if self.current_page > 0:
            prev_btn = ctk.CTkButton(
                nav_frame,
                text="⟵",
                width=60,
                command=self.prev_page
            )
            prev_btn.pack(side="left", padx=5)

        if end <= total:
            next_btn = ctk.CTkButton(
                nav_frame,
                text="⟶",
                width=60,
                command=self.next_page
            )
            next_btn.pack(side="left", padx=5)
            
            
    def next_page(self):
        self.current_page += 1
        self.refresh_id_list()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
        self.refresh_id_list()
            
        
    def load_single_id(self, item_id):
        if not self.editor:
            return

        # limpar seleção anterior
        self.current_ids = [item_id]
        self.id_entry.delete(0, "end")
        self.id_entry.insert(0, str(item_id))

        # atualizar UI
        self.update_checkboxes_for_ids()
        self.prepare_preview_for_current_ids()

        # destaque do botão clicado
        for iid, button in self.id_buttons.items():
            if iid == item_id:
                button.configure(
                    fg_color="#555555",        # cor de fundo "pressed"
                    text_color="cyan"          # destaca o texto
                )
            else:
                button.configure(
                    fg_color=("gray15", "gray25"),
                    text_color="white"
                )

        self.status_label.configure(text=f"ID {item_id} loaded.", text_color="cyan")


    def disable_editing(self):
        self.id_entry.configure(state="disabled")
        self.load_ids_button.configure(state="disabled")
        self.apply_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        for cb in self.checkboxes.values():
            cb.configure(state="disabled")
        self.numeric_entries["ShowOnMinimap"].configure(state="disabled")
        #self.load_spr_button.configure(state="normal")
        for entry in self.numeric_entries.values():
            entry.configure(state="disabled")
        self.insert_id_button.configure(state="disabled")  # NOVO
        self.delete_id_button.configure(state="disabled")  # NOVO         

    def enable_editing(self):
        self.id_entry.configure(state="normal")
        self.load_ids_button.configure(state="normal")
        self.apply_button.configure(state="normal")
        self.save_button.configure(state="normal")
        self.insert_id_button.configure(state="normal")  # NOVO
        self.delete_id_button.configure(state="normal")  # NOVO        
        for cb in self.checkboxes.values():
            cb.configure(state="normal")
        self.numeric_entries["ShowOnMinimap"].configure(state="normal")
        for entry in self.numeric_entries.values():
            entry.configure(state="normal")        

    def load_dat_file(self):
        filepath = filedialog.askopenfilename(
            title="Selecione o arquivo Tibia.dat",
            filetypes=[("DAT files", "*.dat"), ("All files", "*.*")]
        )
        if not filepath:
            return

        try:
            # --- Carrega o DAT normalmente ---
            self.editor = DatEditor(filepath)
            self.editor.load()
            self.current_page = 0
            self.refresh_id_list()
            self.file_label.configure(text=filepath, text_color="white")
            self.status_label.configure(
                text=f"Arquivo .dat carregado! Itens: {self.editor.counts['items']}",
                text_color="green"
            )
            self.enable_editing()
            
            
            # ----------------------------------------
            # 🔥 NOVO: AUTO-CARREGA O .SPR NA MESMA PASTA
            # ----------------------------------------
            import os
            spr_path = os.path.join(os.path.dirname(filepath), "Tibia.spr")

            if os.path.exists(spr_path):
                if self.spr:
                    self.spr.close()

                self.spr = SprReader(spr_path)
                self.spr.load()
                self.status_label.configure(
                    text=self.status_label.cget("text") +
                         f" | SPR carregado ({self.spr.sprite_count} sprites)",
                    text_color="cyan"
                )
                self.preview_info.configure(
                    text=f"SPR carregado automaticamente:\n{spr_path}"
                )
            else:
                self.preview_info.configure(
                    text="Aviso: Tibia.spr não encontrado na mesma pasta."
                )

        except Exception as e:
            print(e)
            messagebox.showerror(
                "Erro ao Carregar",
                f"Não foi possível carregar ou analisar o arquivo:\n{e}"
            )
            self.status_label.configure(text="Falha ao carregar o arquivo.", text_color="red")



    def load_spr_file(self):
        filepath = filedialog.askopenfilename(title="Selecione o arquivo Tibia.spr", filetypes=[("SPR files", "*.spr"), ("All files", "*.*")])
        if not filepath: return
        try:
            if self.spr:
                self.spr.close()
            self.spr = SprReader(filepath)
            self.spr.load()
            self.status_label.configure(text=f"SPR carregado! Sprites: {self.spr.sprite_count}", text_color="green")
            self.preview_info.configure(text=f"SPR carregado: {filepath}\nSprites: {self.spr.sprite_count}")
        except Exception as e:
            messagebox.showerror("Erro ao Carregar SPR", f"Não foi possível carregar/abrir o SPR:\n{e}")
            self.status_label.configure(text="Falha ao carregar SPR.", text_color="red")

    def parse_ids(self, id_string):
        ids = set()
        if not id_string: return []
        try:
            parts = id_string.split(',')
            for part in parts:
                part = part.strip()
                if not part: continue
                if '-' in part:
                    start, end = map(int, part.split('-'))
                    ids.update(range(start, end + 1))
                else:
                    ids.add(int(part))
            return sorted(list(ids))
        except ValueError:
            self.status_label.configure(text="Erro: Formato de ID inválido.", text_color="orange")
            return []

    def load_ids_from_entry(self):
        if not self.editor: return
        id_string = self.id_entry.get()
        self.current_ids = self.parse_ids(id_string)
        if not self.current_ids:
            if id_string:
                messagebox.showwarning("IDs Inválidos", "Formato incorreto. Use números, vírgulas e hifens (ex: 100, 105-110).")
            for cb in self.checkboxes.values():
                cb.deselect()
                cb.configure(text_color="white")
            self.clear_preview()
            return
        self.status_label.configure(text=f"Consultando {len(self.current_ids)} IDs...", text_color="cyan")
        self.update_checkboxes_for_ids()
        self.status_label.configure(text=f"{len(self.current_ids)} IDs carregados para edição.", text_color="white")
        # preparar preview de sprites (primeiro item)
        self.prepare_preview_for_current_ids()

    def update_checkboxes_for_ids(self):
        if not self.current_ids: return
        
        # Checkboxes (código original mantido)
        for attr_name, cb in self.checkboxes.items():
            states = [attr_name in self.editor.things['items'][item_id]['props'] 
                     for item_id in self.current_ids if item_id in self.editor.things['items']]
            if not states:
                cb.deselect(); cb.configure(text_color="gray")
            elif all(states):
                cb.select(); cb.configure(text_color="white")
            elif not any(states):
                cb.deselect(); cb.configure(text_color="white")
            else:
                cb.deselect(); cb.configure(text_color="cyan")
        
        # Carregar valores numéricos
        self.load_numeric_attribute("ShowOnMinimap", "ShowOnMinimap_data", 0)
        self.load_numeric_attribute("HasElevation", "HasElevation_data", 0)
        self.load_numeric_attribute("Ground", "Ground_data", 0)
        self.load_numeric_attribute("HasOffset_X", "HasOffset_data", 0)
        self.load_numeric_attribute("HasOffset_Y", "HasOffset_data", 1)
        self.load_numeric_attribute("HasLight_Level", "HasLight_data", 0)
        self.load_numeric_attribute("HasLight_Color", "HasLight_data", 1)

    def load_numeric_attribute(self, entry_key, data_key, index):
        """Carrega valor de atributo numérico para o entry correspondente."""
        entry = self.numeric_entries.get(entry_key)
        if not entry:
            return
            
            
            

            
        values = []
        for item_id in self.current_ids:
            item = self.editor.things['items'].get(item_id)
            if item and data_key in item['props']:
                data = item['props'][data_key]
                if isinstance(data, tuple) and len(data) > index:
                    values.append(data[index])
        
        if not values:
            entry.delete(0, "end")
            if entry_key in self.numeric_previews:
                self.numeric_previews[entry_key].configure(fg_color="black")
        elif all(v == values[0] for v in values):
            entry.delete(0, "end")
            entry.insert(0, str(values[0]))
            if entry_key in self.numeric_previews:
                self.update_color_preview(entry_key)
        else:
            entry.delete(0, "end")
            if entry_key in self.numeric_previews:
                self.numeric_previews[entry_key].configure(fg_color="gray")


    def apply_changes(self):
        if not self.editor or not self.current_ids:
            messagebox.showwarning("Nenhuma Ação", "Carregue um arquivo e consulte alguns IDs primeiro.")
            return
 

        to_set, to_unset = [], []
        original_states = {}

        for attr_name in self.checkboxes:
            states = [attr_name in self.editor.things['items'][item_id]['props']
                      for item_id in self.current_ids if item_id in self.editor.things['items']]
            if not states:
                original_states[attr_name] = 'none'
            elif all(states):
                original_states[attr_name] = 'all'
            elif not any(states):
                original_states[attr_name] = 'none'
            else:
                original_states[attr_name] = 'mixed'

        for attr_name, cb in self.checkboxes.items():
            if cb.get() == 1 and original_states[attr_name] != 'all':
                to_set.append(attr_name)
            elif cb.get() == 0 and original_states[attr_name] != 'none':
                to_unset.append(attr_name)
         

        
        changes_applied = False
        

        changes_applied |= self.apply_numeric_attribute("ShowOnMinimap", "ShowOnMinimap_data", 0, False)
        changes_applied |= self.apply_numeric_attribute("HasElevation", "HasElevation_data", 0, False)
        changes_applied |= self.apply_numeric_attribute("Ground", "Ground_data", 0, False)
        

        offset_applied = self.apply_offset_attribute()
        changes_applied |= offset_applied
        
 
        light_applied = self.apply_light_attribute()
        changes_applied |= light_applied
        
        if to_set or to_unset:
            self.editor.apply_changes(self.current_ids, to_set, to_unset)
            changes_applied = True
        
        if not changes_applied:
            self.status_label.configure(text="Nenhuma alteração detectada.", text_color="yellow")
            return
        
        self.status_label.configure(text="Alterações aplicadas. Salve com 'Compile as...'", text_color="green")
        self.update_checkboxes_for_ids()
        self.prepare_preview_for_current_ids()

    def apply_numeric_attribute(self, entry_key, data_key, index, signed):
        """Aplica um atributo numérico simples (1 valor)."""
        entry = self.numeric_entries.get(entry_key)
        if not entry:
            return False
            
        val_str = entry.get().strip()
        if not val_str:
            return False
            
        try:
            val = int(val_str)
            # Validações específicas
            if entry_key == "ShowOnMinimap" and not (0 <= val <= 215):
                return False
                
            for item_id in self.current_ids:
                if item_id in self.editor.things['items']:
                    props = self.editor.things['items'][item_id]['props']
                    attr_name = data_key.replace("_data", "")
                    props[attr_name] = True
                    props[data_key] = (val,)
            return True
        except ValueError:
            return False

    def apply_offset_attribute(self):
        """Aplica atributo HasOffset (X, Y) - pode ser negativo."""
        x_entry = self.numeric_entries.get("HasOffset_X")
        y_entry = self.numeric_entries.get("HasOffset_Y")
        
        if not x_entry or not y_entry:
            return False
            
        x_str = x_entry.get().strip()
        y_str = y_entry.get().strip()
        
        if not x_str and not y_str:
            return False
            
        try:
            x_val = int(x_str) if x_str else 0
            y_val = int(y_str) if y_str else 0
            
            for item_id in self.current_ids:
                if item_id in self.editor.things['items']:
                    props = self.editor.things['items'][item_id]['props']
                    props["HasOffset"] = True
                    props["HasOffset_data"] = (x_val, y_val)
            return True
        except ValueError:
            return False

    def apply_light_attribute(self):
        """Aplica atributo HasLight (level, color)."""
        level_entry = self.numeric_entries.get("HasLight_Level")
        color_entry = self.numeric_entries.get("HasLight_Color")
        
        if not level_entry or not color_entry:
            return False
            
        level_str = level_entry.get().strip()
        color_str = color_entry.get().strip()
        
        if not level_str and not color_str:
            return False
            
        try:
            level_val = int(level_str) if level_str else 0
            color_val = int(color_str) if color_str else 0
            
            for item_id in self.current_ids:
                if item_id in self.editor.things['items']:
                    props = self.editor.things['items'][item_id]['props']
                    props["HasLight"] = True
                    props["HasLight_data"] = (level_val, color_val)
            return True
        except ValueError:
            return False

    def save_dat_file(self):
        if not self.editor:
            messagebox.showerror("Erro", "Nenhum arquivo .dat está carregado.")
            return
        filepath = filedialog.asksaveasfilename(title="Salvar arquivo Tibia.dat como...", defaultextension=".dat", filetypes=[("DAT files", "*.dat"), ("All files", "*.*")])
        if not filepath: return
        try:
            self.editor.save(filepath)
            self.status_label.configure(text=f"Arquivo salvo com sucesso em: {filepath}", text_color="lightgreen")
            messagebox.showinfo("Sucesso", "O arquivo .dat modificado foi salvo com sucesso!")
        except Exception as e:
            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar o arquivo:\n{e}")
            self.status_label.configure(text="Falha ao salvar o arquivo.", text_color="red")

    # ---------------------------
    # Preview helpers
    # ---------------------------
    def prepare_preview_for_current_ids(self):
        """Pega os sprite_ids do primeiro item válido da seleção e prepara lista para navegar."""
        self.current_preview_sprite_list = []
        self.current_preview_index = 0
        if not self.editor or not self.spr or not self.current_ids:
            self.clear_preview()
            return
        # find first item that exists in editor
        for item_id in self.current_ids:
            item = self.editor.things['items'].get(item_id)
            if not item:
                continue
            sprite_ids = DatEditor.extract_sprite_ids_from_texture_bytes(item['texture_bytes'])
            if sprite_ids:
                self.current_preview_sprite_list = sprite_ids
                break
        if not self.current_preview_sprite_list:
            self.clear_preview()
            return
        # show first sprite (or the one previously selected)
        self.current_preview_index = 0
        self.show_preview_at_index(self.current_preview_index)

    def clear_preview(self):
        self.canvas.delete("all")
        self.prev_index_label.configure(text="Sprite 0 / 0")
        self.preview_info.configure(text="Nenhuma sprite disponível.")
        self.current_preview_sprite_list = []
        self.current_preview_index = 0
        self.tk_images_cache.clear()

    def change_preview_index(self, delta):
        if not self.current_preview_sprite_list:
            return
        self.current_preview_index = (self.current_preview_index + delta) % len(self.current_preview_sprite_list)
        self.show_preview_at_index(self.current_preview_index)

    def show_preview_at_index(self, idx):
        if not self.current_preview_sprite_list or not self.spr:
            self.clear_preview()
            return
        if idx < 0 or idx >= len(self.current_preview_sprite_list):
            return
        spr_id = self.current_preview_sprite_list[idx]
        img = self.spr.get_sprite(spr_id)
        if img is None:
            self.canvas.delete("all")
            self.preview_info.configure(text=f"Sprite ID {spr_id} não pôde ser decodificada pelo parser atual.")
            self.prev_index_label.configure(text=f"Sprite {idx+1} / {len(self.current_preview_sprite_list)} (ID {spr_id})")
            return
        # scale to fit canvas if needed (max 256)
        max_size = 256
        w, h = img.size
        scale = 1.0
        if max(w, h) > max_size:
            scale = max_size / max(w, h)
            nw = int(w * scale); nh = int(h * scale)
            img = img.resize((nw, nh), Image.NEAREST)
        tk_img = ImageTk.PhotoImage(img)
        self.tk_images_cache['preview'] = tk_img  # keep ref
        self.canvas.delete("all")
        self.canvas.create_image(2, 2, anchor=NW, image=tk_img)
        self.prev_index_label.configure(text=f"Sprite {idx+1} / {len(self.current_preview_sprite_list)} (ID {spr_id})")
        self.preview_info.configure(text=f"Sprite ID {spr_id} - {w}x{h} original, scale {scale:.2f}")
        ctk.set_appearance_mode("dark")


if __name__ == "__main__":
    ImageUpscaleApp().mainloop()
