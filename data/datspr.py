import customtkinter as ctk
from tkinter import filedialog, messagebox, Canvas, Menu
from collections import OrderedDict
import struct
import threading
import os
from PIL import Image, ImageTk
import shutil
import atexit

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
    0x27: ('Usable', ''),      
}
REVERSE_METADATA_FLAGS = {info[0]: flag for flag, info in METADATA_FLAGS.items()}
LAST_FLAG = 0xFF

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
    
class DatEditor:
    def __init__(self, dat_path, extended=False):
        self.dat_path = dat_path
        self.signature = 0
        self.extended = extended   

        self.counts = {'items': 0, 'outfits': 0, 'effects': 0, 'missiles': 0}
        self.things = {
            'items': {}, 
            'outfits': {}, 
            'effects': {}, 
            'missiles': {}
        }

    def load(self):
        with open(self.dat_path, 'rb') as f:
            self.signature = struct.unpack('<I', f.read(4))[0]
            item_count, outfit_count, effect_count, missile_count = struct.unpack('<HHHH', f.read(8))
            self.counts = {'items': item_count, 'outfits': outfit_count, 'effects': effect_count, 'missiles': missile_count}
            
            # load Items 
            for item_id in range(100, self.counts['items'] + 1):
                self.things['items'][item_id] = self._parse_thing(f)

            # load Outfits 
            for outfit_id in range(1, self.counts['outfits'] + 1):
                self.things['outfits'][outfit_id] = self._parse_thing(f)

            # load Effects 
            for effect_id in range(1, self.counts['effects'] + 1):
                self.things['effects'][effect_id] = self._parse_thing(f)

            # load Missiles 
            for missile_id in range(1, self.counts['missiles'] + 1):
                self.things['missiles'][missile_id] = self._parse_thing(f)

    def _parse_thing(self, f):
        props = OrderedDict()
        while True:
            byte = f.read(1)

            if not byte or byte[0] == LAST_FLAG:
                break
            
            flag = byte[0]
            
            if flag in METADATA_FLAGS:
                name, fmt = METADATA_FLAGS[flag]
                
                if name == 'MarketItem':
                    header = f.read(8)
                    if len(header) == 8:
                        name_len = struct.unpack('<H', header[6:8])[0]
                        rest = f.read(name_len + 4)
                        props[name] = True
                        props[name + '_data'] = header + rest
                    pass 

                props[name] = True
                if fmt:
                    size = struct.calcsize(fmt)
                    data = f.read(size)
                    props[name + '_data'] = struct.unpack(fmt, data)
            
            else:
                pass 
        texture_block_start = f.tell()
        wh_bytes = f.read(2)
        if len(wh_bytes) < 2: return {"props": props, "texture_bytes": b""}
        
        width, height = struct.unpack('<BB', wh_bytes)
        
        props['Width'] = width
        props['Height'] = height
        props['CropSize'] = 0        
        
        texture_header_size = 2
        
        if width > 1 or height > 1:
            crop_byte = f.read(1)
            if len(crop_byte) == 1:
                props['CropSize'] = struct.unpack('<B', crop_byte)[0] 
            texture_header_size += 1
            
        header_rest = f.read(5)
        if len(header_rest) < 5: return {"props": props, "texture_bytes": b""}
        
        layers, patternX, patternY, patternZ, frames = struct.unpack('<BBBBB', header_rest)
        
        props['Layers'] = layers
        props['PatternX'] = patternX
        props['PatternY'] = patternY
        props['PatternZ'] = patternZ
        props['Animation'] = frames        
        
        texture_header_size += 5
        
        total_sprites = width * height * patternX * patternY * patternZ * layers * frames
        
        anim_detail_size = 0
        if frames > 1:
            anim_detail_size = 1 + 4 + 1 + (frames * 8)
            
        sprite_id_size = 4 if self.extended else 2
        
        texture_data_size = total_sprites * sprite_id_size
        
        f.seek(texture_block_start)
        total_read = texture_header_size + anim_detail_size + texture_data_size
        texture_bytes = f.read(total_read)
        
        return {"props": props, "texture_bytes": texture_bytes}

    def apply_changes(self, item_ids, attributes_to_set, attributes_to_unset, category='items'):

        if category not in self.things:
            return

        for item_id in item_ids:
            if item_id not in self.things[category]:
                continue
            
            item_props = self.things[category][item_id]['props']
            
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
            

            count_items = self.counts['items']
            count_outfits = self.counts['outfits']
            count_effects = self.counts['effects']
            count_missiles = self.counts['missiles']
            
            f.write(struct.pack('<HHHH', count_items, count_outfits, count_effects, count_missiles))
            

            def write_category(start_id, end_id, category_name):
                for tid in range(start_id, end_id + 1):
                    thing = self.things[category_name].get(tid)
                    
                    if thing and len(thing.get('texture_bytes', b'')) > 0:
                        self._write_thing_properties(f, thing['props'])
                        
                        f.write(struct.pack('<B', LAST_FLAG)) 
                        
                        f.write(thing['texture_bytes'])
                    else:
                        f.write(struct.pack('<B', LAST_FLAG)) 
                        f.write(b'\x01\x01\x01\x01\x01\x01\x01') 

                        if self.extended:
                            f.write(b'\x00\x00\x00\x00')
                        else:
                            f.write(b'\x00\x00')


            #  Items 
            write_category(100, count_items, 'items')
            
            #  Outfits 
            write_category(1, count_outfits, 'outfits')

            #  Effects 
            write_category(1, count_effects, 'effects')

            #  Missiles (
            write_category(1, count_missiles, 'missiles')
            

    def _write_thing_properties(self, f, props):
        for flag, (name, fmt) in METADATA_FLAGS.items():
  
            if name in props:
              
                if props[name] is True:
                    f.write(struct.pack('<B', flag))
                    
                    data_key = name + '_data'
                    if data_key in props:
                        data = props[data_key]
                        
                        if fmt:
                            try:
                                f.write(struct.pack(fmt, *data))
                            except Exception as e:
                                print(f"Erro salvando flag {name} ({hex(flag)}): {e}")
                        else:
                            if isinstance(data, bytes):
                                f.write(data)
                            else:
                                print(f"Erro: Dados de {name} não são bytes.")

    @staticmethod
    def extract_sprite_ids_from_texture_bytes(texture_bytes):
        if not texture_bytes or len(texture_bytes) < 2:
            return []
        try:
            offset = 0
            width, height = struct.unpack_from('<BB', texture_bytes, offset)
            offset += 2
            if width > 1 or height > 1:
                offset += 1  
            layers, px, py, pz, frames = struct.unpack_from('<BBBBB', texture_bytes, offset)
            offset += 5
            total_sprites = width * height * px * py * pz * layers * frames
   
            anim_offset = 0
            if frames > 1:

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

class SprEditor:
    def __init__(self, spr_path, transparency=False):
        self.spr_path = spr_path
        self.transparency = transparency
        self.signature = 0
        self.sprite_count = 0
        self.sprites_data = {} 
        self.modified = False

    def load(self):
        if not os.path.exists(self.spr_path):
            return

        with open(self.spr_path, 'rb') as f:
            header = f.read(8)
            if len(header) < 8:
                raise ValueError("Invalid SPR file.")
            
            self.signature, self.sprite_count = struct.unpack('<II', header)
            
            offsets = []
            for _ in range(self.sprite_count):
                offsets.append(struct.unpack('<I', f.read(4))[0])
            
     
            file_size = f.seek(0, 2)
            
            for i, offset in enumerate(offsets):
                sprite_id = i + 1
                if offset == 0:
                    self.sprites_data[sprite_id] = b''
                    continue

                next_offset = 0
                for j in range(i + 1, len(offsets)):
                    if offsets[j] != 0:
                        next_offset = offsets[j]
                        break
                
                if next_offset == 0:
                    size = file_size - offset
                else:
                    size = next_offset - offset
                
                f.seek(offset)
                self.sprites_data[sprite_id] = f.read(size)

    def save(self, output_path):
        with open(output_path, 'wb') as f:
            f.write(struct.pack('<II', self.signature, self.sprite_count))
            
            current_offset = 8 + (self.sprite_count * 4)
            
            offsets_start_pos = f.tell()
            f.write(b'\x00\x00\x00\x00' * self.sprite_count)
            
            final_offsets = []
            
            for sprite_id in range(1, self.sprite_count + 1):
                data = self.sprites_data.get(sprite_id, b'')
                
                if not data:
                    final_offsets.append(0)
                else:
                    final_offsets.append(current_offset)
                    f.write(data)
                    current_offset += len(data)
            
            f.seek(offsets_start_pos)
            for off in final_offsets:
                f.write(struct.pack('<I', off))

    def get_sprite(self, sprite_id):
        raw_data = self.sprites_data.get(sprite_id)
        if not raw_data:
            return None
            
        start_idx = 0
        if len(raw_data) >= 3 and raw_data[0] == 0xFF and raw_data[1] == 0x00 and raw_data[2] == 0xFF:
            start_idx = 3
            
        if start_idx + 2 <= len(raw_data):
            start_idx += 2
            
        sprite_content = raw_data[start_idx:]
        
        if self.transparency:
            return self._decode_1098_rgba(sprite_content)
        else:
            return self._decode_standard(sprite_content)

    def replace_sprite(self, sprite_id, image):
        if sprite_id < 1: return
        

        if image.size != (32, 32):
            image = image.resize((32, 32), Image.NEAREST)
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        if self.transparency:
            encoded_bytes = self._encode_1098_rgba(image) 
            if encoded_bytes is None: 
                 encoded_bytes = self._encode_standard(image)
        else:
            encoded_bytes = self._encode_standard(image)
            
        full_data = bytearray()
        size = len(encoded_bytes)
        full_data.extend(struct.pack('<H', size))
        full_data.extend(encoded_bytes)
        
        if sprite_id > self.sprite_count:
            for i in range(self.sprite_count + 1, sprite_id):
                self.sprites_data[i] = b''
            self.sprite_count = sprite_id
            
        self.sprites_data[sprite_id] = bytes(full_data)
        self.modified = True
        

    def _decode_standard(self, data):
        try:
            w, h = 32, 32
            img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            pixels = img.load()
            p = 0; x = 0; y = 0; drawn = 0
            while p < len(data) and drawn < 1024:
                if p + 4 > len(data): break
                trans, colored = struct.unpack_from('<HH', data, p)
                p += 4
                drawn += trans
                current = y * w + x + trans
                y, x = divmod(current, w)
                if p + colored * 3 > len(data): break
                for _ in range(colored):
                    if y >= h: break
                    pixels[x, y] = (data[p], data[p+1], data[p+2], 255)
                    p += 3; x += 1; drawn += 1
                    if x >= w: x=0; y+=1
            return img
        except: return None
        
    def _encode_standard(self, image):
        pixels = image.load()
        width, height = image.size
        
        output = bytearray()
        
        transparent_count = 0
        colored_pixels = []
        
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                

                is_transparent = (a < 10) 
                
                if is_transparent:
                    if colored_pixels:
         
                        output.extend(struct.pack('<HH', transparent_count, len(colored_pixels)))
                        for cr, cg, cb in colored_pixels:
                            output.extend(bytes([cr, cg, cb]))
                        
                        transparent_count = 0
                        colored_pixels = []
                    
                    transparent_count += 1
                else:
                    colored_pixels.append((r, g, b))
        
        if colored_pixels or transparent_count > 0:
            output.extend(struct.pack('<HH', transparent_count, len(colored_pixels)))
            for cr, cg, cb in colored_pixels:
                output.extend(bytes([cr, cg, cb]))
                
        return output
        
    def _decode_1098_rgba(self, data):
        """ Decodifica sprite com canal Alpha real (formato estendido) """
        try:
            w, h = 32, 32
            img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            pixels = img.load()

            x = 0
            y = 0
            p = 0
            total_pixels = w * h
            drawn = 0

            while p + 4 <= len(data) and drawn < total_pixels:

                transparent, colored = struct.unpack_from('<HH', data, p)
                p += 4

                drawn += transparent
                for _ in range(transparent):
                    x += 1
                    if x >= w:
                        x = 0
                        y += 1
                        if y >= h: break

                if p + colored * 4 > len(data): 
                    break

                for _ in range(colored):
                    if y >= h: break

                    r = data[p]
                    g = data[p+1]
                    b = data[p+2]
                    a = data[p+3]
                    p += 4
                    
                    if a == 0 and (r!=0 or g!=0 or b!=0): a = 255 

                    pixels[x, y] = (r, g, b, a)

                    x += 1
                    drawn += 1
                    if x >= w:
                        x = 0
                        y += 1
                        if y >= h: break

            return img

        except Exception as e:
            print("DEBUG: error in _decode_1098_rgba:", e)
            return None

    def _encode_1098_rgba(self, image):
        """ Codifica sprite para formato RGBA (4 bytes por pixel) """
        pixels = image.load()
        width, height = image.size
        
        output = bytearray()
        
        transparent_count = 0
        colored_pixels = [] 
        
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                

                is_transparent = (a == 0) 
                
                if is_transparent:

                    if colored_pixels:
                        output.extend(struct.pack('<HH', transparent_count, len(colored_pixels)))
                        for cr, cg, cb, ca in colored_pixels:
                            output.extend(bytes([cr, cg, cb, ca]))
                        
                        transparent_count = 0
                        colored_pixels = []
                    
                    transparent_count += 1
                else:
                    colored_pixels.append((r, g, b, a))

        if colored_pixels or transparent_count > 0:
            output.extend(struct.pack('<HH', transparent_count, len(colored_pixels)))
            for cr, cg, cb, ca in colored_pixels:
                output.extend(bytes([cr, cg, cb, ca]))
                
        return output
        
class DatSprTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.editor = None  #  DatEditor
        self.spr = None     #  SprEditor        
        self._kept_image = None        
        self.current_preview_sprite_list = [] 
        self.current_preview_index = 0
        self.selected_sprite_id = None 
        self.is_animating = False
        self.anim_job = None          
        self.visible_sprite_widgets = {}  
        self.dragged_sprite_id = None         
        self.current_ids = []
        self.checkboxes = {}
        self.build_ui()              
        self.sprites_per_page = 250
        self.sprite_page = 0
        self.sprite_thumbs = {}               
        self.build_loading_overlay()
             
    def build_ui(self):
        
        self.category_var = ctk.StringVar(value="Item")
        self.category_combo = ctk.CTkComboBox(
            self,
            values=["Item", "Outfit", "Effect", "Missile"],
            command=self.on_category_change, 
            variable=self.category_var,            
            border_width=1,
            border_color="gray30")
            
        self.category_combo.pack(
            side="top",
            anchor="w",   
            padx= 10,
            pady= 1 )
        
        
        self.ids_list_frame = ctk.CTkScrollableFrame(self, label_text="List ID", border_width=1, border_color="gray30")        
        self.ids_list_frame.pack(side="left", padx=10, pady=2, fill="y")
        
        self.sprite_list_frame = ctk.CTkScrollableFrame(self, label_text="List Sprites", border_width=1, border_color="gray30")        
        self.sprite_list_frame.pack(side="right", padx=10, pady=2, fill="y")       
        
        self.selected_sprite_id = None 
        self.id_buttons = {}
        self.ids_per_page = 250
        self.current_page = 0

        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.pack(padx=10, pady=10, fill="x")
        
        
        self.bottom_frame = ctk.CTkFrame(self, border_width=1, border_color="gray30")
        self.bottom_frame.pack(padx=10, pady=10, fill="x")

        id_operations_frame = ctk.CTkFrame(self.bottom_frame)
        id_operations_frame.pack(side="left", padx=10, pady=1)

        ctk.CTkLabel(id_operations_frame, text="Manage IDs:").pack(side="left", padx=(0, 5), pady=1)

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
            text="No file loaded.",
            text_color="gray"
        )
        self.file_label.pack(side="left", padx=10, expand=True, fill="x")
        
        
        self.chk_extended = ctk.CTkCheckBox(self.top_frame, text="Extended")
        self.chk_extended.pack(side="left", padx=5)
        self.chk_extended.select() #init extended true

        self.chk_transparency = ctk.CTkCheckBox(self.top_frame, text="Transparency")
        self.chk_transparency.pack(side="left", padx=5)        
                
        self.id_frame = ctk.CTkFrame(self, border_width=1, border_color="gray30")        
        self.id_frame.pack(padx=10, pady=(0,1), fill="x")
        
        ctk.CTkLabel(self.id_frame, text="ID: (Ex: 100, 105-110):").pack(side="left", padx=5)
        
        self.id_entry = ctk.CTkEntry(
            self.id_frame, 
            placeholder_text="Enter the item IDs here"

        )    
        self.id_entry.pack(side="left", padx=10,pady=1, expand=True, fill="x")
        self.id_entry.bind("<Return>", lambda event: self.load_ids_from_entry())
        
        self.load_ids_button = ctk.CTkButton(
            self.id_frame, 
            text="Search ID", 
            command=self.load_ids_from_entry, 
            width=100
        )
        self.load_ids_button.pack(side="left", padx=5)


        self.main_layout = ctk.CTkFrame(self)
        self.main_layout.pack(padx=10, pady=5, fill="both", expand=True)


        self.main_layout.grid_columnconfigure(0, minsize=340, weight=0)
        self.main_layout.grid_columnconfigure(1, minsize=200, weight=1)

        self.main_layout.grid_rowconfigure(0, weight=1)
        self.main_layout.grid_rowconfigure(1, weight=0)


        self.attributes_frame = ctk.CTkScrollableFrame(
            self.main_layout,
            label_text="Flags",
            border_width=1,
            border_color="gray30"
        )
        self.attributes_frame.grid(row=0, column=0, padx=10, pady=5, sticky="nsew")

        #Internal Flags/hide user
        INTERNAL_FLAGS = [
            "MarketItem", 
        ]


        all_attr_names = sorted(REVERSE_METADATA_FLAGS.keys())
        
        visible_attr_names = [name for name in all_attr_names if name not in INTERNAL_FLAGS]


        num_attrs = len(visible_attr_names)
        items_per_col = (num_attrs + 1) // 2 

        for i, attr_name in enumerate(visible_attr_names):
            row = i % items_per_col
            col = i // items_per_col
            
            cb = ctk.CTkCheckBox(self.attributes_frame, text=attr_name)
            cb.grid(row=row, column=col, padx=10, pady=5, sticky="w")
            
            self.checkboxes[attr_name] = cb

        self.direction_frame = ctk.CTkScrollableFrame(
            self.main_layout,
            label_text="Direction",
            border_width=1,
            border_color="gray30"
        )
        self.direction_frame.grid(row=0, column=1, rowspan=2,  padx=10, pady=5, sticky="nsew")

        self.numeric_attrs_frame = ctk.CTkScrollableFrame(
            self.main_layout,
            label_text="Properties", 
            border_width=1,
            border_color="gray30"
        )
        self.numeric_attrs_frame.grid(row=1, column=0, padx=10, pady=(0,5), sticky="nsew")

        self.numeric_entries = {}
        self.numeric_previews = {}

        attrs_config = [
            ("Light Level: (0-10)", "HasLight_Level", False, None),
            ("Light Color: (0-215)", "HasLight_Color", True, "color"),        
            ("Minimap (0-215):", "ShowOnMinimap", True, "color"),
            ("Elevation (0-32):", "HasElevation", False, None),
            ("Ground Speed (0-1000):", "Ground", False, None),
            ("Offset X (-64 to 64):", "HasOffset_X", False, None),
            ("Offset Y (-64 to 64):", "HasOffset_Y", False, None),
            ("Width:", "Width", False, None),
            ("Height:", "Height", False, None),
            ("Crop Size:", "CropSize", False, None),
            ("Layers:", "Layers", False, None),
            ("Pattern X:", "PatternX", False, None),
            ("Pattern Y:", "PatternY", False, None),
            ("Pattern Z:", "PatternZ", False, None),
            ("Anim (Frames):", "Animation", False, None),
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


        self.preview_frame = ctk.CTkFrame(self, border_width=1, border_color="gray30")
        self.preview_frame.pack(side="right", padx=10, pady=10, fill="both", expand=False)
        
        ctk.CTkLabel(self.preview_frame, text="Preview").pack(pady=(6,0))
        
        
        self.image_label = ctk.CTkLabel(
            self.preview_frame, 
            text="",          
            width=150,         
            height=150,
            fg_color="#222121",  
            text_color="white",   
            corner_radius=6
        )
        self.image_label.pack(padx=6, pady=6)
        self.image_label.bind("<Double-Button-1>", self.on_preview_click)
     
    
        self.prev_controls = ctk.CTkFrame(self.preview_frame)
        self.prev_controls.pack(padx=6, pady=2, fill="x")
        
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
        
        self.anim_btn = ctk.CTkButton(
            self.prev_controls,
            text="▶",
            width=30,
            fg_color="#444444",
            command=self.toggle_animation
        )
        self.anim_btn.pack(side="left", padx=4)        
        
        self.preview_info = ctk.CTkLabel(
            self.preview_frame, 
            text="No sprite loaded.",
            wraplength=250, 
            justify="left"
        )
        self.preview_info.pack(padx=6, pady=(0,6))

        self.bottom_frame = ctk.CTkFrame(self)
        self.bottom_frame.pack(padx=5, pady=5, fill="x")

        self.apply_button = ctk.CTkButton(
            self.bottom_frame, 
            text="Save flags",
            width=15,             
            command=self.apply_changes
        )
        self.apply_button.pack(side="left", padx=5, pady=5) 
        
        self.save_button = ctk.CTkButton(
            self.bottom_frame, 
            text="Sprite Optimizer (Clean)", 
        )
        self.save_button.pack(side="left", padx=5, pady=5)             

        self.save_button = ctk.CTkButton(
            self.bottom_frame, 
            text="Compile as...", 
            width=25,  
            fg_color="#7373ff",              
            command=self.save_dat_file
        )
        self.save_button.pack(side="left", padx=5, pady=5) 
        
        self.status_label = ctk.CTkLabel(
            self.bottom_frame, 
            text="", 
            anchor="w"
        )             
        self.status_label.pack(side="left", padx=7, pady=10, expand=True, fill="x") 
        self.disable_editing()
              
        self.context_menu = Menu(self, tearoff=0)
        self.context_menu.add_command(label="Import", command=self.on_context_import)
        self.context_menu.add_command(label="Export", command=self.on_context_export)
        self.context_menu.add_command(label="Replace", command=self.on_context_replace)
        self.context_menu.add_command(label="Clear", command=self.on_context_delete)
        self.right_click_target = None
        
        
        
        
    def toggle_animation(self):
        if not self.current_preview_sprite_list:
            return

        self.is_animating = not self.is_animating

        if self.is_animating:
            self.anim_btn.configure(text="⏹", fg_color="#ff5555") 
            self.animate_loop()
        else:
            self.anim_btn.configure(text="▶", fg_color="#444444") 
            if self.anim_job:
                self.after_cancel(self.anim_job)
                self.anim_job = None

    def animate_loop(self):
        if not self.is_animating or not self.current_preview_sprite_list:
            self.is_animating = False
            self.anim_btn.configure(text="▶", fg_color="#444444")
            return

        group_size = self.current_item_width * self.current_item_height * self.current_item_layers
        if group_size == 0: group_size = 1
        total_views = len(self.current_preview_sprite_list) // group_size
        
        if total_views <= 1:
            self.toggle_animation()
            return

        next_index = self.current_preview_index + 1
        if next_index >= total_views:
            next_index = 0
            
        self.show_preview_at_index(next_index)
        
        self.anim_job = self.after(100, self.animate_loop)        
        
        
    def on_drag_start(self, event, sprite_id):
        self.dragged_sprite_id = sprite_id

        self.configure(cursor="hand2") 

    def on_drag_end(self, event):
        """Finaliza o arraste e verifica se soltou no alvo"""
        self.configure(cursor="")
        
        if self.dragged_sprite_id is None:
            return

        x_root, y_root = self.winfo_pointerxy()
        
        preview_x = self.image_label.winfo_rootx()
        preview_y = self.image_label.winfo_rooty()
        preview_w = self.image_label.winfo_width()
        preview_h = self.image_label.winfo_height()

        if (preview_x <= x_root <= preview_x + preview_w) and \
           (preview_y <= y_root <= preview_y + preview_h):
            
            self.on_drop_success(self.dragged_sprite_id)
        
        self.dragged_sprite_id = None

    def on_drop_success(self, sprite_id):
        if not self.editor or not self.current_ids:
            messagebox.showwarning("Aviso", "Selecione um ID (Item/Outfit) primeiro para editar.")
            return
            
        target_id = self.current_ids[0] 
        
        cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
        category = cat_map.get(self.category_var.get(), "items")
        
        if target_id not in self.editor.things[category]:
            return

        thing = self.editor.things[category][target_id]
        
        current_sprites = DatEditor.extract_sprite_ids_from_texture_bytes(thing['texture_bytes'])

        if not current_sprites:
            current_sprites = [sprite_id]
        else:
            idx = self.current_preview_index
            
            if idx < len(current_sprites):
                current_sprites[idx] = sprite_id
                print(f"Substituindo indice {idx} pelo sprite {sprite_id}")
            else:
                current_sprites[0] = sprite_id

        try:
            new_texture_bytes = self.rebuild_texture_bytes(thing['texture_bytes'], current_sprites)
            thing['texture_bytes'] = new_texture_bytes
            
            self.status_label.configure(text=f"Sprite {sprite_id} aplicado ao ID {target_id}!", text_color="#00ff00")
            
            self.load_single_id(target_id)
            
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao aplicar textura: {e}")
            
            
    def rebuild_texture_bytes(self, original_bytes, new_sprite_ids):
        if not original_bytes:

            header = b'\x01\x01\x01\x01\x01\x01\x01'
        else:
            offset = 0
            width, height = struct.unpack_from('<BB', original_bytes, offset)
            offset += 2
            
            if width > 1 or height > 1:
                offset += 1
                
            layers, px, py, pz, frames = struct.unpack_from('<BBBBB', original_bytes, offset)
            offset += 5
            
            anim_detail_size = 0
            if frames > 1:
                anim_detail_size = 1 + 4 + 1 + (frames * 8)
                
            offset += anim_detail_size
            
            header = original_bytes[:offset]

        ids_data = bytearray()
       
        is_extended = self.editor.extended 
        fmt = '<I' if is_extended else '<H'
        
        for sid in new_sprite_ids:
            ids_data.extend(struct.pack(fmt, int(sid)))
            
        return header + ids_data
            


              
    def show_context_menu(self, event, item_id, context_type):
        self.right_click_target = {"id": item_id, "type": context_type}
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def on_context_export(self):
        if not self.right_click_target:
            return
            
        target_id = self.right_click_target["id"]
        target_type = self.right_click_target["type"]
        try:
            img_to_save = None
            default_name = ""

            if target_type == "sprite_list":
                if self.spr:
                    img_to_save = self.spr.get_sprite(target_id)
                    default_name = f"sprite_{target_id}.png"
            
            elif target_type == "id_list":
                cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
                current_cat_key = cat_map.get(self.category_var.get(), "items")
                
                if self.editor and target_id in self.editor.things[current_cat_key]:
                    item = self.editor.things[current_cat_key][target_id]
                    sprite_ids = DatEditor.extract_sprite_ids_from_texture_bytes(item['texture_bytes'])
                    if sprite_ids and sprite_ids[0] > 0 and self.spr:
                        img_to_save = self.spr.get_sprite(sprite_ids[0])
                        default_name = f"{current_cat_key}_{target_id}.png"

            if img_to_save:
                save_path = filedialog.asksaveasfilename(
                    defaultextension=".png",
                    filetypes=[("PNG Image", "*.png")],
                    initialfile=default_name,
                    title="Export Image"
                )
                if save_path:
                    img_to_save.save(save_path)
                    messagebox.showinfo("Export", f"Saved to {save_path}")
            else:
                messagebox.showwarning("Export", "No image data found for this ID.")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to export: {e}")
            
            
    def on_context_delete(self):
        if not self.right_click_target:
            return

        target_id = self.right_click_target["id"]
        target_type = self.right_click_target["type"]

        confirm = messagebox.askyesno(
            "Confirm Clear",
            f"Are you sure you want to clear {target_type} ID {target_id}?\nThis action cannot be undone."
        )
        if not confirm:
            return

        if target_type == "id_list":
            if not self.editor:
                return

            cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
            current_cat_key = cat_map.get(self.category_var.get(), "items")

            if target_id in self.editor.things[current_cat_key]:
                minimal_texture = b'\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00'
                
                self.editor.things[current_cat_key][target_id] = {
                    "props": OrderedDict(),
                    "texture_bytes": minimal_texture
                }
                
                self.refresh_id_list() 
                self.load_single_id(target_id)
                self.status_label.configure(text=f"ID {target_id} cleared successfully.", text_color="green")

        elif target_type == "sprite_list":
            messagebox.showinfo("Not Implemented", "Sprite clearing requires SPR write logic.\nImplement 'replace_sprite' first.")
            

    def on_context_import(self):
        if not self.spr:
            messagebox.showwarning("Aviso", "Nenhum arquivo .spr carregado.")
            return

        file_path = filedialog.askopenfilename(
            title="Importar Sprite",
            filetypes=[("Imagens", "*.png *.bmp")]
        )
        
        if not file_path:
            return

        try:
            new_image = Image.open(file_path)         
            new_id = self.spr.sprite_count + 1            
            self.spr.replace_sprite(new_id, new_image)           
            self.status_label.configure(text=f"Sprite {new_id} importado com sucesso.", text_color="green")           
            self.select_sprite(new_id)

        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao importar sprite: {e}")

        self.hide_loading()
        
    def on_context_replace(self):
        if not self.right_click_target:
            return
            
        target_id = self.right_click_target["id"]
        target_type = self.right_click_target["type"]
        
        if target_type != "sprite_list":
            messagebox.showinfo("Info", "Replace is currently only supported for Sprite List direct editing.")
            return

        file_path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[("Image Files", "*.png *.bmp")]
        )
        
        if not file_path:
            return

        try:
            new_image = Image.open(file_path)
            
            self.spr.replace_sprite(target_id, new_image)
            
            self.refresh_sprite_list()
            self.status_label.configure(text=f"Sprite {target_id} replaced successfully.", text_color="green")
            
            if self.selected_sprite_id == target_id:
                self.show_preview_at_index(self.current_preview_index)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to replace sprite: {e}")
            
        self.hide_loading()
        
    def on_category_change(self, choice):
        self.category_var.set(choice)        
        self.current_page = 0
        self.id_entry.delete(0, "end") 
        self.refresh_id_list()
        

    def insert_ids(self):
        if not self.editor:
            messagebox.showwarning("Warning", "Load a .dat file first.")
            return
        
        id_string = self.id_operation_entry.get().strip()
        ids_to_insert = []


        if not id_string:

            next_id = self.editor.counts['items'] + 1
            ids_to_insert = [next_id]
        else:
            ids_to_insert = self.parse_ids(id_string)
        
        if not ids_to_insert:
            messagebox.showerror("Error", "Invalid ID format.")

            return
        

        inserted_count = 0
        for new_id in ids_to_insert:
            if new_id in self.editor.things['items']:
                continue 
            
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
            self.editor.things['items'][new_id] = empty_item
            inserted_count += 1
            
            if new_id > self.editor.counts['items']:
                self.editor.counts['items'] = new_id
        
        if inserted_count > 0:
            self.status_label.configure(
                text=f"{inserted_count} ID(s) successfully inserted.",
                text_color="green"
            )
            self.refresh_id_list()
            self.id_operation_entry.delete(0, "end")
            

            if len(ids_to_insert) == 1:
                self.load_single_id(ids_to_insert[0])
                
                target_page = (ids_to_insert[0] - 100) // self.ids_per_page
                if self.current_page != target_page:
                    self.current_page = target_page
                    self.refresh_id_list()
        else:
            self.status_label.configure(
                text="No new IDs were inserted (they already exist).",
                text_color="yellow"
            )

    def delete_ids(self):
        if not self.editor:
            messagebox.showwarning("Warning", "Load a .dat file first.")
            return

        id_string = self.id_operation_entry.get().strip()
        ids_to_delete = []

        if not id_string:
            if self.current_ids:
                ids_to_delete = self.current_ids
            else:
                last_id = self.editor.counts['items']
                if last_id < 100:
                    return
                ids_to_delete = [last_id]
        else:
            ids_to_delete = self.parse_ids(id_string)

        if not ids_to_delete:
            return

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"This will modify {len(ids_to_delete)} items.\n"
            "IDs in the middle of the list will be cleared.\n"
            "IDs at the end of the list will be removed.\n"
            "Do you want to continue?"
        )

        if not confirm:
            return

        ids_to_delete.sort(reverse=True)

        deleted_count = 0
        emptied_count = 0
        
        last_item_id = self.editor.counts['items']
        ids_to_delete_set = set(ids_to_delete)
        
        while last_item_id in ids_to_delete_set:
            if last_item_id in self.editor.things['items']:
                del self.editor.things['items'][last_item_id]
                ids_to_delete_set.remove(last_item_id)
                deleted_count += 1
            last_item_id -= 1
            
        self.editor.counts['items'] = last_item_id
        
        for item_id in ids_to_delete_set:
            if item_id in self.editor.things['items']:
 
                minimal_texture = b'\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00'
                self.editor.things['items'][item_id] = {
                    "props": OrderedDict(),
                    "texture_bytes": minimal_texture
                }
                emptied_count += 1
                

        status_message = ""
        if emptied_count > 0:
            status_message += f"{emptied_count} IDs were cleared. "
        if deleted_count > 0:
            status_message += f"{deleted_count} IDs at the end of the list were removed."
            
        self.status_label.configure(
            text=status_message,
            text_color="orange"
        )

        self.current_ids = []
        self.refresh_id_list()
        self.id_operation_entry.delete(0, "end")
        self.id_entry.delete(0, "end")
        self.clear_preview()


    def update_color_preview(self, attr_name):
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

                if 0 <= idx <= 215:
                    r, g, b = ob_index_to_rgb(idx)
                    preview.configure(fg_color=f"#{r:02x}{g:02x}{b:02x}")
                else:
                    preview.configure(fg_color="red")
            elif attr_name == "HasLight_Color":

                if 0 <= idx <= 65535:
                    r, g, b = self.light_color_to_rgb(idx)
                    preview.configure(fg_color=f"#{r:02x}{g:02x}{b:02x}")
                else:
                    preview.configure(fg_color="red")
        except ValueError:
            preview.configure(fg_color="gray")

    def light_color_to_rgb(self, color_val):
        r = ((color_val & 0x1F) << 3)
        g = (((color_val >> 5) & 0x1F) << 3)
        b = (((color_val >> 10) & 0x1F) << 3)
        return r, g, b
            
    def next_page(self):
        self.current_page += 1
        self.refresh_id_list()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
        self.refresh_id_list()            
        
    def refresh_id_list(self):
        for widget in self.ids_list_frame.winfo_children():
            widget.destroy()

        self.id_buttons.clear()
        
        if not self.editor:
            return 

        self.show_loading("Loading...\nPlease wait.")            

        cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
        current_cat_key = cat_map.get(self.category_var.get(), "items")
        
        start_id_offset = 100 if current_cat_key == "items" else 1
        
        total_count = self.editor.counts[current_cat_key]
        
        start_index = self.current_page * self.ids_per_page
        current_start_id = start_index + start_id_offset

        max_id = total_count + 1
        
        end_id = min(current_start_id + self.ids_per_page, max_id)

        for item_id in range(current_start_id, end_id):

            item_frame = ctk.CTkFrame(self.ids_list_frame, fg_color="transparent")
            item_frame.pack(pady=1, fill="x")
            
            sprite_label = ctk.CTkLabel(item_frame, text="", width=80, height=80, fg_color="#222121")
            sprite_label.pack(side="left", padx=(2, 5))
            
            if self.spr and item_id in self.editor.things[current_cat_key]:
                item = self.editor.things[current_cat_key][item_id]
                sprite_ids = DatEditor.extract_sprite_ids_from_texture_bytes(item['texture_bytes'])
                
                if sprite_ids and sprite_ids[0] > 0:
                    try:
                        img = self.spr.get_sprite(sprite_ids[0])
                        if img:
                            img_resized = img.resize((32, 32), Image.NEAREST)
                            tk_img = ctk.CTkImage(light_image=img_resized, dark_image=img_resized, size=(72, 72))
                            sprite_label.configure(image=tk_img, text="")
                            sprite_label.image = tk_img 
                    except Exception as e:
                        print(f"Erro sprite {item_id}: {e}")
            
            id_label = ctk.CTkLabel(
                item_frame,
                text=str(item_id),
                fg_color=(("gray15", "gray25")),
                width=80,
                anchor="w"
            )
            id_label.pack(side="left", fill="x", expand=True)
            
            item_frame.bind("<Double-Button-1>", lambda e, iid=item_id: self.load_single_id(iid))
            sprite_label.bind("<Double-Button-1>", lambda e, iid=item_id: self.load_single_id(iid))
            id_label.bind("<Double-Button-1>", lambda e, iid=item_id: self.load_single_id(iid))
            
            item_frame.bind("<Button-3>", lambda e, iid=item_id: self.show_context_menu(e, iid, "id_list"))
            sprite_label.bind("<Button-3>", lambda e, iid=item_id: self.show_context_menu(e, iid, "id_list"))
            id_label.bind("<Button-3>", lambda e, iid=item_id: self.show_context_menu(e, iid, "id_list"))
                
            self.id_buttons[item_id] = id_label

        nav_frame = ctk.CTkFrame(self.ids_list_frame)
        nav_frame.pack(pady=10)

        if self.current_page > 0:
            ctk.CTkButton(nav_frame, text="⟵", width=60, command=self.prev_page).pack(side="left", padx=5)

        if end_id < max_id:
            ctk.CTkButton(nav_frame, text="⟶", width=60, command=self.next_page).pack(side="left", padx=5)
            
        self.hide_loading()

            
    def refresh_sprite_list(self):
        for w in self.sprite_list_frame.winfo_children():
            w.destroy()
        
        self.sprite_thumbs.clear()
        self.visible_sprite_widgets = {} 

        if not self.spr: return
        
        self.show_loading("Loading...\nPlease wait.")

        total = self.spr.sprite_count
        start = self.sprite_page * self.sprites_per_page + 1
        end = min(start + self.sprites_per_page, total + 1)

        for spr_id in range(start, end):
            item_frame = ctk.CTkFrame(self.sprite_list_frame, fg_color="transparent")
            item_frame.pack(pady=1, fill="x")

            is_current = (spr_id == self.selected_sprite_id)
            
            bg_color = "#555555" if is_current else "transparent"
            txt_color = "cyan" if is_current else "white"

            def on_item_click(e, sid=spr_id):
                self.select_sprite(sid, from_preview_click=False)

            img_label = ctk.CTkLabel(item_frame, text="", width=80, height=80, fg_color="#222121")
            img_label.pack(side="left", padx=(2, 5))
            
            text_label = ctk.CTkLabel(
                item_frame,
                text=str(spr_id),
                width=60,
                anchor="w",
                fg_color=bg_color,   
                text_color=txt_color 
            )
            text_label.pack(side="left", fill="x", expand=True)
            
            self.visible_sprite_widgets[spr_id] = text_label

            img = self.spr.get_sprite(spr_id)
            if img:
                thumb = img.resize((32, 32), Image.NEAREST)
                tk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=(72, 72))
                img_label.configure(image=tk_img)
                self.sprite_thumbs[spr_id] = tk_img

            item_frame.bind("<Double-Button-1>", on_item_click)
            img_label.bind("<Double-Button-1>", on_item_click)
            text_label.bind("<Double-Button-1>", on_item_click)
                        
            item_frame.bind("<ButtonPress-1>", lambda e, s=spr_id: self.on_drag_start(e, s))
            img_label.bind("<ButtonPress-1>", lambda e, s=spr_id: self.on_drag_start(e, s))
            text_label.bind("<ButtonPress-1>", lambda e, s=spr_id: self.on_drag_start(e, s))

            item_frame.bind("<ButtonRelease-1>", self.on_drag_end)
            img_label.bind("<ButtonRelease-1>", self.on_drag_end)
            text_label.bind("<ButtonRelease-1>", self.on_drag_end)            
            
            item_frame.bind("<Button-3>", lambda e, sid=spr_id: self.show_context_menu(e, sid, "sprite_list"))
            img_label.bind("<Button-3>", lambda e, sid=spr_id: self.show_context_menu(e, sid, "sprite_list"))
            text_label.bind("<Button-3>", lambda e, sid=spr_id: self.show_context_menu(e, sid, "sprite_list"))

        nav = ctk.CTkFrame(self.sprite_list_frame)
        nav.pack(pady=10)

        if self.sprite_page > 0:
            ctk.CTkButton(
                nav, text="⟵", width=60,
                command=self.prev_sprite_page
            ).pack(side="left", padx=5)

        if end <= total:
            ctk.CTkButton(
                nav, text="⟶", width=60,
                command=self.next_sprite_page
            ).pack(side="left", padx=5)
    
            self.hide_loading()

    
            
    def update_list_selection_visuals(self):
        """
        Atualiza apenas as cores dos itens visíveis na lista, sem recarregar imagens.
        """
        if not hasattr(self, 'visible_sprite_widgets'):
            return

        for spr_id, label_widget in self.visible_sprite_widgets.items():
            if spr_id == self.selected_sprite_id:
                try:
                    label_widget.configure(fg_color="#555555", text_color="cyan")
                except:
                    pass
            else:
                try:
                    label_widget.configure(fg_color="transparent", text_color="white")
                except:
                    pass
            
                  
    def next_sprite_page(self):
        if not self.spr:
            return
        max_page = (self.spr.sprite_count - 1) // self.sprites_per_page
        if self.sprite_page < max_page:
            self.sprite_page += 1
            self.refresh_sprite_list()

    def prev_sprite_page(self):
        if self.sprite_page > 0:
            self.sprite_page -= 1
            self.refresh_sprite_list()
            
            
    def update_preview_image(self):
        if not self.spr or not hasattr(self, 'current_preview_sprite_list') or not self.current_preview_sprite_list:
            self.image_label.configure(image=None, text="No sprite")
            self.prev_index_label.configure(text="Sprite 0 / 0")
            self.preview_info.configure(text="")
            return

        if self.current_preview_index < 0:
            self.current_preview_index = 0
        if self.current_preview_index >= len(self.current_preview_sprite_list):
            self.current_preview_index = 0

        sprite_id = self.current_preview_sprite_list[self.current_preview_index]

        img = self.spr.get_sprite(sprite_id)

        if img:
 
            preview_size = (128, 128) 
            img_resized = img.resize(preview_size, Image.NEAREST)

            tk_img = ctk.CTkImage(
                light_image=img_resized,
                dark_image=img_resized,
                size=preview_size
            )
            
            self.image_label.configure(image=tk_img, text="")
            self.image_label.image = tk_img 
        else:
            self.image_label.configure(image=None, text="Empty/Error")

        total = len(self.current_preview_sprite_list)
        self.prev_index_label.configure(text=f"Sprite {self.current_preview_index + 1} / {total}")
        self.preview_info.configure(text=f"Sprite ID: {sprite_id}")
            

        
    def on_preview_click(self, event):
        preview_list = getattr(self, 'current_preview_sprite_list', [])
        
        if not preview_list:
            return
        
        idx = getattr(self, 'current_preview_index', 0)
        if idx < 0 or idx >= len(preview_list):
            return

        current_sprite_id = preview_list[idx]
        
        self.select_sprite(current_sprite_id, from_preview_click=True) 
        
        if hasattr(self, 'status_label'):
            self.status_label.configure(
                text=f"Selected sprite {current_sprite_id} from preview.",
                text_color="cyan"
            )

            
    def select_sprite(self, sprite_id, from_preview_click=False):
        if not self.spr or sprite_id <= 0 or sprite_id > self.spr.sprite_count:
            return

        self.selected_sprite_id = sprite_id

        if not from_preview_click:
            self.current_preview_sprite_list = [sprite_id]
            self.current_preview_index = 0
            self.update_preview_image() 

        target_page = (sprite_id - 1) // self.sprites_per_page

        if self.sprite_page != target_page:
            self.sprite_page = target_page
            self.refresh_sprite_list()
        else:
            self.update_list_selection_visuals()

        try:
            self.after(50, lambda: self._scroll_to_sprite(sprite_id))
        except:
            pass


    def _scroll_to_sprite(self, sprite_id):
        index_in_page = (sprite_id - 1) % self.sprites_per_page
        scroll_pos = index_in_page / self.sprites_per_page
        self.sprite_list_frame._parent_canvas.yview_moveto(scroll_pos)


    def load_single_id(self, item_id):
        if not self.editor: return

        cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
        current_cat_key = cat_map.get(self.category_var.get(), "items")

        self.current_ids = [item_id]
        self.id_entry.delete(0, "end")
        self.id_entry.insert(0, str(item_id))

        self.update_checkboxes_for_ids(current_cat_key) 
        self.prepare_preview_for_current_ids(current_cat_key)

        for iid, button in self.id_buttons.items():
            if iid == item_id:
                button.configure(fg_color="#555555", text_color="cyan")
            else:
                button.configure(fg_color=("gray15", "gray25"), text_color="white")

        self.status_label.configure(text=f"ID {item_id} ({current_cat_key}) loaded.", text_color="cyan")



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
        self.insert_id_button.configure(state="disabled")  
        self.delete_id_button.configure(state="disabled")       

    def enable_editing(self):
        self.id_entry.configure(state="normal")
        self.load_ids_button.configure(state="normal")
        self.apply_button.configure(state="normal")
        self.save_button.configure(state="normal")
        self.insert_id_button.configure(state="normal")  
        self.delete_id_button.configure(state="normal")     
        for cb in self.checkboxes.values():
            cb.configure(state="normal")
        self.numeric_entries["ShowOnMinimap"].configure(state="normal")
        for entry in self.numeric_entries.values():
            entry.configure(state="normal")        

          
    def load_dat_file(self):
        filepath = filedialog.askopenfilename(
            title="Select the .dat file",
            filetypes=[("DAT files", "*.dat"), ("All files", "*.*")]
        )
        if not filepath:
            return

        self.show_loading("Loading...\nPlease wait.")
        
        is_extended = bool(self.chk_extended.get())
        is_transparency = bool(self.chk_transparency.get())
        
        try:

            self.editor = DatEditor(filepath, extended=is_extended)            
            self.editor.load()
            self.current_page = 0

         
            self.enable_editing()

            base_path = os.path.splitext(filepath)[0]
            spr_path = base_path + ".spr"

            if os.path.exists(spr_path):
                self.show_loading("Found .spr file.\nLoading sprites...")
                
                if hasattr(self, 'spr') and self.spr:
                    pass  
                self.spr = SprEditor(spr_path, transparency=self.chk_transparency.get())
                self.spr.load()

    
                self.preview_info.configure(
                    text=f"SPR loaded: {spr_path}\nSprites: {self.spr.sprite_count}"
                )
                self.sprite_page = 0

                # update sprite list
                self.refresh_sprite_list()
            # update list id's              
            self.refresh_id_list()                

        except Exception as e:
            print(e)
            messagebox.showerror("Load Error", f"Could not load or parse the file:\n{e}")
            self.status_label.configure(text="Failed to load the file.", text_color="red")

        finally:
            self.hide_loading()
            
            spr_count = 0
            if hasattr(self, 'spr') and self.spr is not None:
                spr_count = self.spr.sprite_count

            self.status_label.configure(
                text=(
                    f"Files loaded! "
                    f"Items: {self.editor.counts['items']}  /  "
                    f"Outfits: {self.editor.counts['outfits']}  /  "
                    f"Effects: {self.editor.counts['effects']}  /  "
                    f"Missiles: {self.editor.counts['missiles']}  /  "
                    f"Sprite Total: {spr_count}"
                ),
                text_color="cyan"
            )
                           
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
            self.status_label.configure(text="Error: Invalid ID format.", text_color="orange")
      
            return []

    def load_ids_from_entry(self):
        if not self.editor: return
        
        id_string = self.id_entry.get()
        self.current_ids = self.parse_ids(id_string)
        
        if not self.current_ids:
            if id_string:
                messagebox.showwarning("Invalid IDs", "Incorrect format.")
            for cb in self.checkboxes.values():
                cb.deselect()
                cb.configure(text_color="white")
            self.clear_preview()
            return


        cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
        current_cat_key = cat_map.get(self.category_var.get(), "items")

        self.status_label.configure(text=f"Consultando {len(self.current_ids)} IDs...", text_color="cyan")
        
        self.update_checkboxes_for_ids(category=current_cat_key)
        self.status_label.configure(text=f"{len(self.current_ids)} IDs loaded...", text_color="white")
        self.prepare_preview_for_current_ids(category=current_cat_key)

        first_id = self.current_ids[0]
        base_offset = 100 if current_cat_key == "items" else 1
        
        if first_id >= base_offset:
            target_page = (first_id - base_offset) // self.ids_per_page
            if self.current_page != target_page:
                self.current_page = target_page
                self.refresh_id_list()
            else:
                self.refresh_id_list()

            for iid, button in self.id_buttons.items():
                if iid in self.current_ids:
                    button.configure(fg_color="#555555", text_color="cyan")
                else:
                    button.configure(fg_color=("gray15", "gray25"), text_color="white")

            try:
                index_in_page = (first_id - base_offset) % self.ids_per_page
                scroll_pos = max(0, index_in_page / self.ids_per_page)
                self.ids_list_frame._parent_canvas.yview_moveto(scroll_pos)
            except Exception:
                pass

    def update_checkboxes_for_ids(self, category="items"):
        if not self.current_ids: return
        
        things_dict = self.editor.things.get(category, {})

        for attr_name, cb in self.checkboxes.items():

            states = [attr_name in things_dict[item_id]['props'] 
                     for item_id in self.current_ids if item_id in things_dict]
            
            if not states:
                cb.deselect(); cb.configure(text_color="gray")
            elif all(states):
                cb.select(); cb.configure(text_color="white")
            elif not any(states):
                cb.deselect(); cb.configure(text_color="white")
            else:
                cb.deselect(); cb.configure(text_color="cyan")
        
        self.load_numeric_attribute("ShowOnMinimap", "ShowOnMinimap_data", 0, category)
        self.load_numeric_attribute("HasElevation", "HasElevation_data", 0, category)
        self.load_numeric_attribute("Ground", "Ground_data", 0, category)
        self.load_numeric_attribute("HasOffset_X", "HasOffset_data", 0, category)
        self.load_numeric_attribute("HasOffset_Y", "HasOffset_data", 1, category)
        self.load_numeric_attribute("HasLight_Level", "HasLight_data", 0, category)
        self.load_numeric_attribute("HasLight_Color", "HasLight_data", 1, category)
        self.load_numeric_attribute("Width", "Width", 0, category)
        self.load_numeric_attribute("Height", "Height", 0, category)
        self.load_numeric_attribute("CropSize", "CropSize", 0, category)
        self.load_numeric_attribute("Layers", "Layers", 0, category)
        self.load_numeric_attribute("PatternX", "PatternX", 0, category)
        self.load_numeric_attribute("PatternY", "PatternY", 0, category)
        self.load_numeric_attribute("PatternZ", "PatternZ", 0, category)
        self.load_numeric_attribute("Animation", "Animation", 0, category)        

    def load_numeric_attribute(self, entry_key, data_key, index, category="items"):
        entry = self.numeric_entries.get(entry_key)
        if not entry: return
            
        values = []
        things_dict = self.editor.things.get(category, {})

        for item_id in self.current_ids:
            item = things_dict.get(item_id)
            if item and data_key in item['props']:
                data = item['props'][data_key]
                
                if isinstance(data, tuple):
                    if len(data) > index:
                        values.append(data[index])
                else:
                    values.append(data)
        
        if not values:
            entry.delete(0, "end")
            if entry_key in self.numeric_previews:
                self.numeric_previews[entry_key].configure(fg_color="#888888")
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
            messagebox.showwarning("No Action", "Load a file and check some IDs first.")
            return

        to_set, to_unset = [], []
        original_states = {}

        cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
        current_cat_key = cat_map.get(self.category_var.get(), "items")
        
        things_dict = self.editor.things.get(current_cat_key, {})

        for attr_name in self.checkboxes:
            states = [attr_name in things_dict[item_id]['props']
                      for item_id in self.current_ids if item_id in things_dict]
            
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
        
        changes_applied |= self.apply_numeric_attribute("ShowOnMinimap", "ShowOnMinimap_data", 0, False, category=current_cat_key)
        changes_applied |= self.apply_numeric_attribute("HasElevation", "HasElevation_data", 0, False, category=current_cat_key)
        changes_applied |= self.apply_numeric_attribute("Ground", "Ground_data", 0, False, category=current_cat_key)

        offset_applied = self.apply_offset_attribute(category=current_cat_key)
        changes_applied |= offset_applied
        
        light_applied = self.apply_light_attribute(category=current_cat_key)
        changes_applied |= light_applied
        
        if to_set or to_unset:
            self.editor.apply_changes(self.current_ids, to_set, to_unset, category=current_cat_key)
            changes_applied = True
        
        if not changes_applied:
            self.status_label.configure(text="No changes detected.", text_color="yellow")
            return
     
        self.status_label.configure(text="Changes applied. Save with 'Compile as...'", text_color="green")
        
        self.update_checkboxes_for_ids(category=current_cat_key)
        self.prepare_preview_for_current_ids(category=current_cat_key)


    def apply_numeric_attribute(self, entry_key, data_key, index, signed, category="items"):
        entry = self.numeric_entries.get(entry_key)
        if not entry: return False
        val_str = entry.get().strip()
        if not val_str: return False
            
        try:
            val = int(val_str)
              
            for item_id in self.current_ids:
                if item_id in self.editor.things[category]:
                    props = self.editor.things[category][item_id]['props']
                    attr_name = data_key.replace("_data", "")
                    props[attr_name] = True
                    props[data_key] = (val,)
            return True
        except ValueError:
            return False

    def apply_offset_attribute(self, category="items"):
        x_entry = self.numeric_entries.get("HasOffset_X")
        y_entry = self.numeric_entries.get("HasOffset_Y")
        if not x_entry or not y_entry: return False
        x_str = x_entry.get().strip()
        y_str = y_entry.get().strip()
        if not x_str and not y_str: return False
            
        try:
            x_val = int(x_str) if x_str else 0
            y_val = int(y_str) if y_str else 0
            
            for item_id in self.current_ids:
                if item_id in self.editor.things[category]:
                    props = self.editor.things[category][item_id]['props']
                    props["HasOffset"] = True
                    props["HasOffset_data"] = (x_val, y_val)
            return True
        except ValueError:
            return False

    def apply_light_attribute(self, category="items"):
        level_entry = self.numeric_entries.get("HasLight_Level")
        color_entry = self.numeric_entries.get("HasLight_Color")
        if not level_entry or not color_entry: return False
        level_str = level_entry.get().strip()
        color_str = color_entry.get().strip()
        if not level_str and not color_str: return False
            
        try:
            level_val = int(level_str) if level_str else 0
            color_val = int(color_str) if color_str else 0
            
            for item_id in self.current_ids:
                if item_id in self.editor.things[category]:
                    props = self.editor.things[category][item_id]['props']
                    props["HasLight"] = True
                    props["HasLight_data"] = (level_val, color_val)
            return True
        except ValueError:
            return False


    def save_dat_file(self):
        if not self.editor:
            messagebox.showerror("Error", "No .dat file is loaded.")
            return
            
        filepath = filedialog.asksaveasfilename(
            title="Save DAT and SPR file as...", 
            defaultextension=".dat", 
            filetypes=[("DAT files", "*.dat"), ("All files", "*.*")]
        )
        
        if not filepath: 
            return
            
        try:
            self.editor.save(filepath)
            
            msg_extra = ""

            if self.spr:
                base_path = os.path.splitext(filepath)[0]
                spr_dest_path = base_path + ".spr"
                

                self.spr.save(spr_dest_path)
                
                msg_extra = f"\nAnd the .spr file was compiled/saved to:\n{os.path.basename(spr_dest_path)}"
            else:
                msg_extra = "\nWarning: No .spr was loaded/saved."

            self.status_label.configure(
                text=f"Saved successfully: {os.path.basename(filepath)}", 
                text_color="lightgreen"
            )
            messagebox.showinfo("Success", f"Files compiled successfully!{msg_extra}")
            
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save the file:\n{e}")
            self.status_label.configure(text="Failed to save files.", text_color="red")

    def prepare_preview_for_current_ids(self, category="items"):
        self.current_preview_sprite_list = []
        self.current_preview_index = 0
        
        self.current_item_width = 1
        self.current_item_height = 1
        self.current_item_layers = 1
        
        if self.is_animating:
            self.toggle_animation()        
        
        if not self.editor or not self.spr or not self.current_ids:
            self.clear_preview()
            return
            
        things_dict = self.editor.things.get(category, {})

        for item_id in self.current_ids:
            item = things_dict.get(item_id)
            if not item:
                continue
            
            props = item.get('props', {})
            self.current_item_width = props.get('Width', 1)
            self.current_item_height = props.get('Height', 1)
            self.current_item_layers = props.get('Layers', 1)
            
            sprite_ids = DatEditor.extract_sprite_ids_from_texture_bytes(item['texture_bytes'])
            if sprite_ids:
                self.current_preview_sprite_list = sprite_ids
                break
        
        if not self.current_preview_sprite_list:
            self.clear_preview()
            return

        self.current_preview_index = 0
        self.show_preview_at_index(self.current_preview_index) 

    def clear_preview(self):
        
        if self.is_animating:
            self.toggle_animation()
            
        try:
            self.image_label.configure(image=None, text="")
        except Exception:
            pass
            
        self.image_label.image = None
        self.preview_info.configure(text="No sprite available.")
        self.current_preview_sprite_list = []
        self.current_preview_index = 0

    def change_preview_index(self, delta):
        if not self.current_preview_sprite_list:
            return
            
        new_index = self.current_preview_index + delta
        
        if 0 <= new_index < len(self.current_preview_sprite_list):
            self.current_preview_index = new_index
            self.show_preview_at_index(self.current_preview_index)

    def show_preview_at_index(self, idx):
        if not self.current_preview_sprite_list or not self.spr:
            self.clear_preview()
            return
            
        group_size = self.current_item_width * self.current_item_height * self.current_item_layers
        if group_size == 0: group_size = 1
        
        total_views = len(self.current_preview_sprite_list) // group_size
        
        if idx < 0: idx = 0
        if idx >= total_views: idx = total_views - 1
        self.current_preview_index = idx

        start_pos = idx * group_size
        end_pos = start_pos + group_size
        chunk_ids = self.current_preview_sprite_list[start_pos:end_pos]
        
        full_img = self.reconstruct_item_image(chunk_ids)
        
        if full_img is None:
            self.image_label.configure(image=None, text="Error")
            return

        w, h = full_img.size
        target_size = 128
        
        scale = min(target_size / w, target_size / h)
        if scale < 1: 
            final_w, final_h = int(w * scale), int(h * scale)
        else:
            final_w, final_h = int(w * scale), int(h * scale)

        img_resized = full_img.resize((final_w, final_h), Image.NEAREST)

        new_tk_image = ctk.CTkImage(
            light_image=img_resized,
            dark_image=img_resized,
            size=(final_w, final_h)
        )
        
        self._kept_image = new_tk_image 
        
        self.image_label.configure(image=self._kept_image, text="")
   
        first_spr_id = chunk_ids[0] if chunk_ids else 0
        self.prev_index_label.configure(text=f"Frame {idx+1}/{total_views} (Ref ID: {first_spr_id})")
        self.preview_info.configure(text=f"Size: {w}x{h} | W:{self.current_item_width} H:{self.current_item_height} L:{self.current_item_layers}")


    def reconstruct_item_image(self, sprite_ids):
        width = self.current_item_width
        height = self.current_item_height
        layers = self.current_item_layers
        
        expected_count = width * height * layers
        if len(sprite_ids) < expected_count:
            return None

        canvas_w = width * 32
        canvas_h = height * 32
        canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
        
        idx = 0
        
        for l in range(layers):
            for h in range(height):       
                for w in range(width):   
                    
                    if idx >= len(sprite_ids): break
                    
                    sid = sprite_ids[idx]
                    idx += 1
                    
                    if sid > 0:
                        spr = self.spr.get_sprite(sid)
                        if spr:

                            dest_y = (height - h - 1) * 32                           
                            dest_x = (width - w - 1) * 32

                            canvas.alpha_composite(spr, (dest_x, dest_y))               
        return canvas

    def build_loading_overlay(self):
        self.loading_overlay = ctk.CTkFrame(self, fg_color="gray10", corner_radius=0)

        self.loading_label = ctk.CTkLabel(
            self.loading_overlay, 
            text="Loading...", 
            font=("Arial", 24, "bold"),
            text_color="white"
        )
        self.loading_label.place(relx=0.5, rely=0.5, anchor="center")

    def show_loading(self, message="Loading..."):
        self.loading_label.configure(text=message)
        self.loading_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.update() 

    def hide_loading(self):
        self.loading_overlay.place_forget()
