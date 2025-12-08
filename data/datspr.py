from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QLabel, QPushButton, QLineEdit, QCheckBox, QComboBox,
                             QScrollArea, QFrame, QFileDialog, QMessageBox, QMenu,
                             QSizePolicy, QApplication)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPoint,QMimeData
from PyQt6.QtGui import QPixmap, QImage, QColor, QPainter, QContextMenuEvent, QDrag, QCursor
from collections import OrderedDict
import struct
import os
from PIL import Image
import shutil
import atexit

from sliceObd import SliceWindow  
from spriteOptmizer import SpriteOptimizerWindow 
from obdHandler import ObdHandler

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
            
            for item_id in range(100, self.counts['items'] + 1):
                self.things['items'][item_id] = self._parse_thing(f, 'items')

            for outfit_id in range(1, self.counts['outfits'] + 1):
                self.things['outfits'][outfit_id] = self._parse_thing(f, 'outfits')

            for effect_id in range(1, self.counts['effects'] + 1):
                self.things['effects'][effect_id] = self._parse_thing(f, 'effects')

            for missile_id in range(1, self.counts['missiles'] + 1):
                self.things['missiles'][missile_id] = self._parse_thing(f, 'missiles')


    def _parse_thing(self, f, category):
        props = OrderedDict()
        
        # --- 1. LEITURA DAS FLAGS ---
        while True:
            byte = f.read(1)
            # Se acabar o arquivo ou flag de fim (0xFF)
            if not byte or byte[0] == LAST_FLAG:
                break
            
            flag = byte[0]
            
            if flag in METADATA_FLAGS:
                name, fmt = METADATA_FLAGS[flag]
                
                if name == 'MarketItem':
                    # Lógica específica do Market
                    header = f.read(8)
                    if len(header) == 8:
                        # header: [Category:2][TradeAs:2][ShowAs:2][NameLen:2]
                        name_len = struct.unpack('<H', header[6:8])[0]
                        # Resto: [Name:Len][Voc:2][Level:2] = Len + 4 bytes
                        rest = f.read(name_len + 4)
                        props[name] = True
                        props[name + '_data'] = header + rest
                else:
                    props[name] = True
                    if fmt:
                        size = struct.calcsize(fmt)
                        data = f.read(size)
                        props[name + '_data'] = struct.unpack(fmt, data)

        # --- 2. LEITURA DA TEXTURA (Sequencial) ---
        # Usamos bytearray para acumular os dados enquanto lemos.
        # Isso evita erro de cálculo de seek.
        texture_bytes = bytearray()

        if category == 'outfits':
            # --- OUTFIT STRUCTURE ---
            # Frame Group Count
            b = f.read(1)
            if not b: return {"props": props, "texture_bytes": bytes(texture_bytes)}
            texture_bytes.extend(b)
            fg_count = b[0]
            props['FrameGroupCount'] = fg_count
            
            for i in range(fg_count):
                # Type (Idle/Walk)
                b = f.read(1) 
                texture_bytes.extend(b)
                if i == 0: props['FrameGroupType'] = b[0]

                # Width / Height
                b = f.read(2)
                texture_bytes.extend(b)
                w, h = struct.unpack('<BB', b)
                
                if i == 0:
                    props['Width'] = w
                    props['Height'] = h

                # Crop Size (Se maior que 1x1)
                if w > 1 or h > 1:
                    b = f.read(1)
                    texture_bytes.extend(b)
                    if i == 0: props['CropSize'] = b[0]

                # Headers de Animação
                b = f.read(5) # Layers, Px, Py, Pz, Frames
                texture_bytes.extend(b)
                layers, px, py, pz, frames = struct.unpack('<BBBBB', b)

                if i == 0:
                    props['Layers'] = layers
                    props['PatternX'] = px
                    props['PatternY'] = py
                    props['PatternZ'] = pz
                    props['Animation'] = frames

                # Animation Details (Timing)
                if frames > 1:
                    # Async(1) + Loop(4) + Start(1) + Durations(frames * 8)
                    detail_size = 1 + 4 + 1 + (frames * 8)
                    b = f.read(detail_size)
                    texture_bytes.extend(b)

                # Sprite IDs
                total_sprites = w * h * px * py * pz * layers * frames
                spr_size = 4 if self.extended else 2
                
                b = f.read(total_sprites * spr_size)
                texture_bytes.extend(b)

        else:
            # --- ITEM / EFFECT / MISSILE STRUCTURE ---
            # Width / Height
            b = f.read(2)
            if not b: return {"props": props, "texture_bytes": bytes(texture_bytes)}
            texture_bytes.extend(b)
            
            w, h = struct.unpack('<BB', b)
            props['Width'] = w
            props['Height'] = h
            props['CropSize'] = 0   

            # Crop Size
            if w > 1 or h > 1:
                b = f.read(1)
                texture_bytes.extend(b)
                props['CropSize'] = b[0]
            
            # Headers
            b = f.read(5)
            texture_bytes.extend(b)
            layers, px, py, pz, frames = struct.unpack('<BBBBB', b)
            
            props['Layers'] = layers
            props['PatternX'] = px
            props['PatternY'] = py
            props['PatternZ'] = pz
            props['Animation'] = frames     
            
            # Animation Details
            if frames > 1:
                detail_size = 1 + 4 + 1 + (frames * 8)
                b = f.read(detail_size)
                texture_bytes.extend(b)
            
            # Sprite IDs
            total_sprites = w * h * px * py * pz * layers * frames
            spr_size = 4 if self.extended else 2
            
            b = f.read(total_sprites * spr_size)
            texture_bytes.extend(b)

        return {"props": props, "texture_bytes": bytes(texture_bytes)}



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
        if not texture_bytes: return []
        
        def try_parse(offset):
            ids = []
            try:

                w, h = struct.unpack_from('<BB', texture_bytes, offset)
                curr = offset + 2
                if w > 1 or h > 1: curr += 1 
                layers, px, py, pz, frames = struct.unpack_from('<BBBBB', texture_bytes, curr)
                curr += 5
                
                if frames > 1:
                    curr += (1 + 4 + 1 + (frames * 8)) 

                total = w * h * px * py * pz * layers * frames
                remaining = len(texture_bytes) - curr
                
                if total == 0: return []
                
                spr_size = remaining // total
                if spr_size not in (2, 4): return [] 
                
                fmt = '<I' if spr_size == 4 else '<H'
                for _ in range(total):
                    val = struct.unpack_from(fmt, texture_bytes, curr)[0]
                    ids.append(val)
                    curr += spr_size
                return ids
            except:
                return []

        result = try_parse(0)
        if result: return result
        
        result_outfit = try_parse(2) 
        if result_outfit: return result_outfit
        
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
        
def pil_to_qpixmap(pil_image):
    """Converte PIL Image para QPixmap"""
    if pil_image is None:
        return QPixmap()
    
    if pil_image.mode == 'RGBA':
        qimage = QImage(pil_image.tobytes("raw", "RGBA"), pil_image.size[0], pil_image.size[1], QImage.Format.Format_RGBA8888)
    elif pil_image.mode == 'RGB':
        qimage = QImage(pil_image.tobytes("raw", "RGB"), pil_image.size[0], pil_image.size[1], QImage.Format.Format_RGB888)
    else:
        qimage = QImage(pil_image.tobytes("raw", pil_image.mode), pil_image.size[0], pil_image.size[1], QImage.Format.Format_RGB888)
    
    return QPixmap.fromImage(qimage)

class ScrollableFrame(QWidget):
    """Widget scrollável customizado"""
    def __init__(self, parent=None, label_text=""):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(2)
        
        if label_text:
            label = QLabel(label_text)
            label.setStyleSheet("font-weight: bold; padding: 5px;")
            self.layout.addWidget(label)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(2)
        self.scroll.setWidget(self.scroll_widget)
        self.layout.addWidget(self.scroll)
    

class ClickableLabel(QLabel):
    """QLabel com suporte a eventos de clique"""
    doubleClicked = pyqtSignal()
    rightClicked = pyqtSignal(QPoint)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)
    
    def contextMenuEvent(self, event):
        self.rightClicked.emit(event.globalPos())
        super().contextMenuEvent(event)
        
        
class DraggableLabel(ClickableLabel):
    """Label que permite arrastar o Sprite ID."""
    def __init__(self, sprite_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sprite_id = sprite_id
        self.drag_start_position = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_position = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self.drag_start_position:
            return
        
        if (event.pos() - self.drag_start_position).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        
        mime_data.setText(str(self.sprite_id))
        drag.setMimeData(mime_data)
        
        if self.pixmap():
            drag.setPixmap(self.pixmap().scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio))
            drag.setHotSpot(QPoint(16, 16))

        drag.exec(Qt.DropAction.CopyAction)

class DroppablePreviewLabel(ClickableLabel):
    """Label de Preview que aceita Sprites soltos e informa a posição."""
    spriteDropped = pyqtSignal(int, QPoint) 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            try:
                int(event.mimeData().text())
                event.acceptProposedAction()
            except ValueError:
                event.ignore()
        else:
            event.ignore()

    def dropEvent(self, event):
        try:
            sprite_id = int(event.mimeData().text())
            
            drop_position = event.position().toPoint()
            
            self.spriteDropped.emit(sprite_id, drop_position)
            event.acceptProposedAction()
        except ValueError:
            event.ignore()

class DatSprTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.editor = None  #  DatEditor
        self.spr = None     #  SprEditor        
        self._kept_image = None        
        self.current_preview_sprite_list = [] 
        self.current_preview_index = 0
        self.selected_sprite_id = None 
        self.is_animating = False

        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.update_animation_step) 
           
        self.visible_sprite_widgets = {}        
        self.current_ids = []
        self.checkboxes = {}
        self.sprites_per_page = 1000
        self.sprite_page = 0
        self.sprite_thumbs = {}               
        self.build_ui()             
        self.build_loading_overlay()
             
    def build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)
        
        # Top frame - file loading
        top_frame = QHBoxLayout()
        
        self.load_dat_button = QPushButton("Load dat/spr (10.98)")
        self.load_dat_button.clicked.connect(self.load_dat_file)
        top_frame.addWidget(self.load_dat_button)
        
        self.file_label = QLabel("No file loaded.")
        self.file_label.setStyleSheet("color: gray;")
        top_frame.addWidget(self.file_label, 1)
        
        self.chk_extended = QCheckBox("Extended")
        self.chk_extended.setChecked(True)
        top_frame.addWidget(self.chk_extended)
        
        self.chk_transparency = QCheckBox("Transparency")
        top_frame.addWidget(self.chk_transparency)
        
        main_layout.addLayout(top_frame)
        
        # Category combo
        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(["Item", "Effect", "Missile"])
        self.category_combo.currentTextChanged.connect(self.on_category_change)

        category_layout.addWidget(self.category_combo)
        category_layout.addStretch()
        main_layout.addLayout(category_layout)
        
        # Main horizontal layout - lists on sides, content in middle
        main_h_layout = QHBoxLayout()
        
        # Left: ID list
        self.ids_list_frame = ScrollableFrame(self, "List ID")
        self.ids_list_frame.setMinimumWidth(200)
        self.ids_list_frame.setMaximumWidth(250)
        main_h_layout.addWidget(self.ids_list_frame)
        
        # Middle: Main content area
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        
        # ID entry frame
        id_frame = QHBoxLayout()
        id_frame.addWidget(QLabel("ID: (Ex: 100, 105-110):"))
        self.id_entry = QLineEdit()
        self.id_entry.setPlaceholderText("Enter the item IDs here")
        self.id_entry.returnPressed.connect(self.load_ids_from_entry)
        id_frame.addWidget(self.id_entry, 1)
        
        self.load_ids_button = QPushButton("Search ID")
        self.load_ids_button.clicked.connect(self.load_ids_from_entry)
        id_frame.addWidget(self.load_ids_button)
        middle_layout.addLayout(id_frame)
        
        main_grid = QGridLayout()
        main_grid.setColumnStretch(0, 1)
        main_grid.setColumnStretch(1, 1)

        self.attributes_frame = ScrollableFrame(self, "Flags")
        main_grid.addWidget(self.attributes_frame, 0, 0)
        
        #Internal Flags/hide user
        INTERNAL_FLAGS = [
            "MarketItem", 
        ]

        all_attr_names = sorted(REVERSE_METADATA_FLAGS.keys())
        
        visible_attr_names = [name for name in all_attr_names if name not in INTERNAL_FLAGS]

        num_attrs = len(visible_attr_names)
        items_per_col = (num_attrs + 1) // 2 

        flags_layout = QGridLayout()
        flags_layout.setColumnStretch(0, 1)
        flags_layout.setColumnStretch(1, 1)
        
        for i, attr_name in enumerate(visible_attr_names):
            row = i % items_per_col
            col = i // items_per_col
            
            cb = QCheckBox(attr_name)
            flags_layout.addWidget(cb, row, col)
            
            self.checkboxes[attr_name] = cb
            
            
        #Direction
        self.attributes_frame.scroll_layout.addLayout(flags_layout)
        self.attributes_frame.scroll_layout.addStretch()

        self.direction_frame = ScrollableFrame(self, "Direction")
        main_grid.addWidget(self.direction_frame, 0, 1, 1, 1)
        
        dir_widget = QWidget()
        dir_layout = QGridLayout(dir_widget)
        dir_layout.setSpacing(1)
        dir_layout.setContentsMargins(0,0,0,0)

        grid_map = [
            (0, 1, "N", "↑"), 
            (1, 0, "W", "←"),  
            (1, 2, "E", "→"),
            (2, 1, "S", "↓"),
             
            #(0, 0, "NW", "↖")
            #(2, 0, "SW", "↙")
            #(0, 2, "NE", "↗")
            #(2, 2, "SE", "↘")
            #(1, 1, "C", "•")
        ]
        
        self.dir_buttons = {} 
        self.current_direction_key = "S"
        
        for r, c, key, label in grid_map:
            btn = QPushButton(label)
            btn.setFixedSize(60, 60)
            btn.clicked.connect(lambda _, k=key: self.change_direction(k))
            dir_layout.addWidget(btn, r, c)
            self.dir_buttons[key] = btn
            
        addon_layout = QHBoxLayout()
        self.addon_1_btn = QPushButton("Addon 1")
        self.addon_1_btn.setCheckable(True)
        self.addon_1_btn.setFixedSize(55, 55)
        addon_layout.addWidget(self.addon_1_btn)

        self.addon_2_btn = QPushButton("Addon 2")
        self.addon_2_btn.setCheckable(True)
        self.addon_2_btn.setFixedSize(55, 55)
        addon_layout.addWidget(self.addon_2_btn)
        
        self.addon_3_btn = QPushButton("Addon 3")
        self.addon_3_btn.setCheckable(True)
        self.addon_3_btn.setFixedSize(55, 55)       
        addon_layout.addWidget(self.addon_3_btn)  

        self.mask_btn = QPushButton("Mask")
        self.mask_btn.setCheckable(True)
        self.mask_btn.setFixedSize(55, 55)       
        addon_layout.addWidget(self.mask_btn)

        self.layer_btn = QPushButton("View Layer")
        self.layer_btn.setCheckable(True)
        self.layer_btn.setFixedSize(55, 55)       
        addon_layout.addWidget(self.layer_btn)         
        
        self.direction_frame.scroll_layout.addWidget(dir_widget)
        self.direction_frame.scroll_layout.addLayout(addon_layout)
        self.direction_frame.scroll_layout.addStretch()

        

        self.direction_frame.scroll_layout.addWidget(dir_widget)
        self.direction_frame.scroll_layout.addStretch()
        
        self.current_direction = 2 #

        # Properties        
        self.numeric_attrs_frame = ScrollableFrame(self, "Properties")
        main_grid.addWidget(self.numeric_attrs_frame, 1, 0)
        
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

        props_layout = QGridLayout()
        row = 0
        for label_text, attr_name, has_preview, preview_type in attrs_config:
            props_layout.addWidget(QLabel(label_text), row, 0)
            
            entry = QLineEdit()
            entry.setMaximumWidth(80)
            props_layout.addWidget(entry, row, 1)
            self.numeric_entries[attr_name] = entry
            
            if has_preview and preview_type == "color":
                preview = QLabel("   ")
                preview.setMinimumWidth(30)
                preview.setMaximumWidth(30)
                preview.setStyleSheet("background-color: black; border: 1px solid gray;")
                props_layout.addWidget(preview, row, 2)
                self.numeric_previews[attr_name] = preview
                entry.textChanged.connect(lambda text, attr=attr_name: self.update_color_preview(attr))
            
            row += 1
        
        self.numeric_attrs_frame.scroll_layout.addLayout(props_layout)
        self.numeric_attrs_frame.scroll_layout.addStretch()
        
        # Frames    
        self.preview_frame = QFrame()
        self.preview_frame.setFrameShape(QFrame.Shape.Box)
        preview_layout = QVBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        
        preview_label = QLabel("Preview")
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(preview_label)
        
        self.image_label = DroppablePreviewLabel() 
        self.image_label.setMinimumSize(390, 390)
        self.image_label.setMaximumSize(390, 390)
        self.image_label.setStyleSheet("background-color: #222121; border: 1px solid gray;")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setText("No sprite")
        self.image_label.doubleClicked.connect(self.on_preview_click)
        self.image_label.spriteDropped.connect(self.handle_preview_drop)    
        preview_layout.addWidget(self.image_label, 0, Qt.AlignmentFlag.AlignCenter)
     
        prev_controls = QHBoxLayout()
        self.prev_index_label = QLabel("Sprite 0 / 0")
        prev_controls.addWidget(self.prev_index_label)
        
        self.prev_prev_btn = QPushButton("<")
        self.prev_prev_btn.setMaximumWidth(30)
        self.prev_prev_btn.clicked.connect(lambda: self.change_preview_index(-1))
        prev_controls.addWidget(self.prev_prev_btn)
              
        self.prev_next_btn = QPushButton(">")
        self.prev_next_btn.setMaximumWidth(30)
        self.prev_next_btn.clicked.connect(lambda: self.change_preview_index(1))
        prev_controls.addWidget(self.prev_next_btn)
        
        self.anim_btn = QPushButton("▶")
        self.anim_btn.setMaximumWidth(30)
        self.anim_btn.setStyleSheet("background-color: #444444;")
        self.anim_btn.clicked.connect(self.toggle_animation)
        prev_controls.addWidget(self.anim_btn)
        
        preview_layout.addLayout(prev_controls)
        
        self.preview_info = QLabel("No sprite loaded.")
        self.preview_info.setWordWrap(True)
        preview_layout.addWidget(self.preview_info)
        
        main_grid.addWidget(self.preview_frame, 1, 1)
        middle_layout.addLayout(main_grid)
        main_h_layout.addWidget(middle_widget, 1)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        
        # List Sprites    
        self.sprite_list_frame = ScrollableFrame(self, "List Sprites")
        self.sprite_list_frame.setMinimumWidth(200)
        self.sprite_list_frame.setMaximumWidth(250)
        right_layout.addWidget(self.sprite_list_frame)
        
        main_h_layout.addWidget(right_widget)
        main_layout.addLayout(main_h_layout)
        
        bottom_frame = QHBoxLayout()
        
        id_operations_frame = QHBoxLayout()
        id_operations_frame.addWidget(QLabel("Manage IDs:"))
        
        self.id_operation_entry = QLineEdit()
        self.id_operation_entry.setPlaceholderText("ID (ex: 100-105)")
        self.id_operation_entry.setMaximumWidth(120)
        id_operations_frame.addWidget(self.id_operation_entry)

        self.insert_id_button = QPushButton("Insert ID")
        self.insert_id_button.setStyleSheet("background-color: #00b300;")
        self.insert_id_button.clicked.connect(self.insert_ids)
        id_operations_frame.addWidget(self.insert_id_button)

        self.delete_id_button = QPushButton("Delete ID")
        self.delete_id_button.setStyleSheet("background-color: #ff2626;")
        self.delete_id_button.clicked.connect(self.delete_ids)
        id_operations_frame.addWidget(self.delete_id_button)
        

        self.slicer_id_button = QPushButton("Slicer")
        self.slicer_id_button.clicked.connect(self.open_slicer) 
        id_operations_frame.addWidget(self.slicer_id_button)
        
        self.optimizer_button = QPushButton("Sprite Optimizer")
        self.optimizer_button.clicked.connect(self.open_optimizer)
        id_operations_frame.addWidget(self.optimizer_button)    
        
        bottom_frame.addLayout(id_operations_frame)
        
          
        self.apply_button = QPushButton("Save flags")
        self.apply_button.clicked.connect(self.apply_changes)
        bottom_frame.addWidget(self.apply_button)
        
        self.save_button = QPushButton("Compile as...")
        self.save_button.setStyleSheet("background-color: #00008c;")
        self.save_button.clicked.connect(self.save_dat_file)
        bottom_frame.addWidget(self.save_button)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: white;")
        bottom_frame.addWidget(self.status_label, 1)
        
        main_layout.addLayout(bottom_frame)
        
        self.disable_editing()
        
        # Context menu
        self.context_menu = QMenu(self)
        self.context_menu.addAction("Import", self.on_context_import)
        self.context_menu.addAction("Export", self.on_context_export)
        self.context_menu.addAction("Replace", self.on_context_replace)
        self.context_menu.addAction("Clear", self.on_context_delete)
        self.right_click_target = None
        
        self.id_buttons = {}
        self.ids_per_page = 1000
        self.current_page = 0
        
    def change_direction(self, dir_key):
        self.current_direction_key = dir_key
        
        # Atualiza visual dos botões
        for key, btn in self.dir_buttons.items():
            if key == dir_key:
                btn.setStyleSheet("background-color: #007acc; color: white; font-weight: bold;")
            else:
                btn.setStyleSheet("")

        # Reseta animação e atualiza preview
        self.current_preview_index = 0
        self.show_preview_at_index(0)

        
        
    def build_outfit_texture_bytes(self, width, height, frames, sprite_ids, layer_type=0):
        """
        Constrói a estrutura binária específica para Outfits (10.98+).
        Isso inclui o cabeçalho de FrameGroups.
        """
        out = bytearray()
        
        # --- OUTFIT HEADER ---
        # Byte 1: Frame Group Count (Geralmente 1 para monstros/items simples, 
        # mas players têm Idle+Walk+Mount...)
        # Ao importar uma imagem simples (PNG), estamos criando um outfit de 1 Grupo apenas.
        out.append(1) 
        
        # Byte 2: Frame Group Type (0 = Idle/Normal)
        out.append(layer_type) 
        
        # --- DATA BLOCK (Igual ao Item, mas identado dentro do grupo) ---
        out.extend(struct.pack('<BB', width, height))
        
        if width > 1 or height > 1:
            out.append(32) # CropSize
            
        # Layers, Px, Py, Pz, Frames
        # Outfit padrão geralmente é 1 Layer, 1 Pattern X/Y/Z
        layers = 1
        px = 1
        py = 1
        pz = 1
        
        out.extend(struct.pack('<BBBBB', layers, px, py, pz, frames))
        
        # Improved Animations (Obrigatório 10.98)
        if frames > 1:
            out.append(0) # Async/Mode (0 = Sync)
            out.extend(struct.pack('<I', 0)) # Loop Count (0 = Infinito)
            out.append(0) # Start Frame
            for _ in range(frames):
                # Duração: Monstros geralmente ~75ms, Outfits variam.
                out.extend(struct.pack('<I', 75)) 
        
        # Sprite IDs
        use_extended = self.editor.extended
        fmt = '<I' if use_extended else '<H'
        
        for sid in sprite_ids:
            out.extend(struct.pack(fmt, sid))
            
        return bytes(out)
        
        
        
    def handle_preview_drop(self, new_sprite_id, drop_pos):
        # ... (código inicial de verificação igual) ...
        if not self.current_ids or not self.editor:
            return

        cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
        current_cat_key = cat_map.get(self.category_combo.currentText(), "items")
        target_id = self.current_ids[0]
        
        if target_id not in self.editor.things[current_cat_key]:
            return

        item_data = self.editor.things[current_cat_key][target_id]
        props = item_data.get('props', {})
        
        width = props.get('Width', 1)
        height = props.get('Height', 1)
        width = 1 if width == 0 else width
        height = 1 if height == 0 else height

        # ... (cálculo de offset do pixmap igual) ...
        pixmap = self.image_label.pixmap()
        if not pixmap: return
        pm_w = pixmap.width()
        pm_h = pixmap.height()
        label_w = self.image_label.width()
        label_h = self.image_label.height()
        offset_x = (label_w - pm_w) // 2
        offset_y = (label_h - pm_h) // 2
        click_x = drop_pos.x() - offset_x
        click_y = drop_pos.y() - offset_y

        if click_x < 0 or click_x >= pm_w or click_y < 0 or click_y >= pm_h:
            return

        sprite_size = 32 
        col = int(click_x / sprite_size)
        row = int(click_y / sprite_size)

        if col >= width: col = width - 1
        if row >= height: row = height - 1
        
        # Inverte as coordenadas para o padrão do Tibia
        inverted_row = (height - 1) - row
        inverted_col = (width - 1) - col

        target_row = inverted_row
        target_col = inverted_col
        
        sprites_per_frame = width * height * props.get('Layers', 1)
        base_frame_index = self.current_preview_index * sprites_per_frame
        
        # --- CORREÇÃO FINAL PARA LINHA-PRIMEIRO (Row-Major) ---
        # Agora o índice é calculado baseado em (Row * Width) + Col
        local_index = (target_row * width) + target_col
        # -------------------------------------------------------
        
        final_index = base_frame_index + local_index
        
        current_sprites = self.current_preview_sprite_list
        if not current_sprites:
            current_sprites = [0] * (final_index + 1)

        # Se precisar expandir a lista
        if final_index >= len(current_sprites):
            current_sprites.extend([0] * (final_index - len(current_sprites) + 1))

        if 0 <= final_index < len(current_sprites):
            current_sprites[final_index] = new_sprite_id
            
            # Salva no editor
            original_bytes = item_data.get('texture_bytes', b'')
            new_texture_bytes = self.rebuild_texture_bytes(original_bytes, current_sprites)
            self.editor.things[current_cat_key][target_id]['texture_bytes'] = new_texture_bytes
            
            # Atualiza visualização
            self.prepare_preview_for_current_ids(current_cat_key)
            self.show_preview_at_index(self.current_preview_index)


            
    def open_slicer(self):
        if not self.spr:
            QMessageBox.warning(self, "Aviso", "Carregue um arquivo .spr primeiro.")
            return

        self.slicer_win = SliceWindow()
        # Conecta o sinal da janela Slicer ao método que processa as sprites
        self.slicer_win.sprites_imported.connect(self.handle_slicer_import)
        self.slicer_win.show()
        
        
    def open_optimizer(self):
        if not self.spr or not self.editor:
            QMessageBox.warning(self, "Aviso", "Carregue os arquivos DAT e SPR primeiro.")
            return

        # Passamos a instância do editor (DAT) e do spr (SPR) para o otimizador
        self.opt_win = SpriteOptimizerWindow(self.spr, self.editor, self)
        self.opt_win.show()
        

    def handle_slicer_import(self, sprite_list):
        if not self.spr or not sprite_list:
            return
            
        count = 0
        try:
            # Encontra o último ID
            last_id = self.spr.sprite_count
            
            for pil_img in sprite_list:
                new_id = last_id + 1
                # Usa o método existente replace_sprite que já lida com expansão do arquivo
                self.spr.replace_sprite(new_id, pil_img)
                last_id = new_id
                count += 1
            
            self.refresh_sprite_list()
            self.status_label.setText(f"{count} sprites importadas do Slicer com sucesso.")
            self.status_label.setStyleSheet("color: #90ee90;") # Light green
            
            # Vai para a última página para mostrar as novas sprites
            self.sprite_page = (self.spr.sprite_count - 1) // self.sprites_per_page
            self.refresh_sprite_list()
            
        except Exception as e:
            QMessageBox.critical(self, "Erro na Importação", f"Falha ao importar sprites: {e}")

        
    def toggle_animation(self):
        if self.is_animating:
            self.anim_timer.stop()
            self.is_animating = False
            self.anim_btn.setText("▶") 
        else:
            if not self.current_ids: return
            
            # Pega o número real de frames de animação do item
            cat_key = self.get_current_category_key()
            if self.current_ids[0] in self.editor.things[cat_key]:
                props = self.editor.things[cat_key][self.current_ids[0]].get('props', {})
                anim_count = props.get('Animation', 1)
            else:
                anim_count = 1

            if anim_count > 1:
                self.is_animating = True
                self.anim_btn.setText("■") 
                # Reinicia do frame 0 para garantir sincronia
                self.current_preview_index = 0
                self.anim_timer.start(200) # ~5 FPS
            else:
                self.status_label.setText("Item has only 1 animation frame.")

    def update_animation_step(self):
        if not self.is_animating: return
        
        cat_key = self.get_current_category_key()
        if not self.current_ids: 
            self.toggle_animation()
            return

        # Pega o limite de frames novamente
        item_data = self.editor.things[cat_key].get(self.current_ids[0])
        if not item_data: return
        
        anim_frames = item_data['props'].get('Animation', 1)
        
        # Incrementa
        self.current_preview_index += 1
        
        # Loop: Se passar do limite, volta pro 0
        if self.current_preview_index >= anim_frames:
            self.current_preview_index = 0
            
        # Atualiza a tela
        self.show_preview_at_index(self.current_preview_index)


    def animate_loop(self):
        if not self.is_animating or not self.current_preview_sprite_list:
            self.is_animating = False
            self.anim_btn.setText("▶")
            self.anim_btn.setStyleSheet("background-color: #444444;")
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
        
        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.animate_loop)
        self.anim_timer.setSingleShot(True)
        self.anim_timer.start(100)

        
        
    def build_texture_bytes(self, width, height, layers, px, py, pz, frames, sprite_ids):
        out = bytearray()
        
        out.extend(struct.pack('<BB', width, height))
        
        if width > 1 or height > 1:
            out.append(32) 
            
        out.extend(struct.pack('<BBBBB', layers, px, py, pz, frames))
        
        if frames > 1:
            out.append(0) # Async/Mode
            out.extend(struct.pack('<I', 0)) # Loop Count
            out.append(0) # Start Frame
            for _ in range(frames):
                out.extend(struct.pack('<I', 75)) 

        use_extended = self.editor.extended 
        fmt = '<I' if use_extended else '<H'
        
        for sid in sprite_ids:
            out.extend(struct.pack(fmt, sid))
            
        return bytes(out)
        
    def get_current_category_key(self):
        cat_map = {
            "Item": "items", 
            "Outfit": "outfits", 
            "Effect": "effects", 
            "Missile": "missiles"
        }
        return cat_map.get(self.category_combo.currentText(), "items")
 
           
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
        if isinstance(event, QContextMenuEvent):
            self.context_menu.exec(event.globalPos())
        elif hasattr(event, 'globalPos'):
            self.context_menu.exec(event.globalPos())
        else:
            self.context_menu.exec(QPoint(event.x(), event.y()))

    def on_context_export(self):
        if not self.current_ids:
            return
            
        target_id = self.current_ids[0]
        cat_key = self.get_current_category_key()
        
        # Mapeia nome da categoria interna para o nome do OB
        ob_type_map = {
            "items": "Item", "outfits": "Outfit", 
            "effects": "Effect", "missiles": "Missile"
        }
        ob_type = ob_type_map.get(cat_key, "Item")

        thing = self.editor.things[cat_key].get(target_id)
        if not thing: 
            QMessageBox.warning(self, "Erro", "Item não encontrado.")
            return

        file_path, filter_used = QFileDialog.getSaveFileName(
            self, f"Export {ob_type}", f"{target_id}", 
            "Object Builder (*.obd);;Images (*.png)"
        )
        
        if not file_path: return

        # --- EXTRAÇÃO DE SPRITES ---
        # Usa o método estático do editor para ler os IDs dos bytes brutos
        texture_bytes = thing.get('texture_bytes', b'')
        sprite_ids = self.editor.extract_sprite_ids_from_texture_bytes(texture_bytes)
        
        images = []
        if not sprite_ids:
            # Se não achou IDs nos bytes, tenta uma abordagem de fallback ou alerta
            # Pode acontecer se o item for invisível ou dados corrompidos
            print("Aviso: Nenhuma sprite encontrada nos dados do item.")
        else:
            for sid in sprite_ids:
                img = self.spr.get_sprite(sid)
                if img:
                    images.append(img)
                else:
                    # Sprite ID existe mas não tem imagem no SPR (vazio)
                    # Adiciona transparente 32x32 para manter a sincronia da animação
                    images.append(Image.new("RGBA", (32, 32), (0,0,0,0)))

        # --- SALVAR ---
        if filter_used == "Object Builder (*.obd)" or file_path.endswith(".obd"):
            try:
                # Passa o ob_type correto (Item/Outfit)
                ObdHandler.save_obd(file_path, thing['props'], images, ob_type)
                QMessageBox.information(self, "Sucesso", f"Exportado {len(images)} sprites para OBD.")
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao salvar OBD: {e}")
        else:
            # Exportação PNG (Opcional, se você tiver o método auxiliar)
            # self.export_as_png_sheet(file_path, images) 
            pass

   
    def on_context_delete(self):
        if not self.right_click_target:
            return

        target_id = self.right_click_target["id"]
        target_type = self.right_click_target["type"]

        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            f"Are you sure you want to clear {target_type} ID {target_id}?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if target_type == "id_list":
            if not self.editor:
                return

            cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
            current_cat_key = cat_map.get(self.category_combo.currentText(), "items")

            if target_id in self.editor.things[current_cat_key]:
                minimal_texture = b'\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00'
                
                self.editor.things[current_cat_key][target_id] = {
                    "props": OrderedDict(),
                    "texture_bytes": minimal_texture
                }
                
                self.refresh_id_list() 
                self.load_single_id(target_id)
                self.status_label.setText(f"ID {target_id} cleared successfully.")
                self.status_label.setStyleSheet("color: green;")

        elif target_type == "sprite_list":
            QMessageBox.information(self, "Not Implemented", "Sprite clearing requires SPR write logic.\nImplement 'replace_sprite' first.")
            

    def on_context_import(self):
        if not self.current_ids: return
        target_id = self.current_ids[0]
        cat_key = self.get_current_category_key()

        file_path, filter_used = QFileDialog.getOpenFileName(
            self, "Import Item", "", 
            "Supported Files (*.png *.jpg *.obd);;Object Builder (*.obd);;Images (*.png *.jpg)"
        )
        
        if not file_path: return

        new_props = {}
        new_images = []

        if file_path.endswith(".obd"):
            new_props, new_images = ObdHandler.load_obd(file_path)
            if not new_images:
                QMessageBox.warning(self, "Aviso", "OBD parece vazio ou inválido.")
                return
        else:
            try:
                img = Image.open(file_path).convert("RGBA")

                new_images = [img] 
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao abrir imagem: {e}")
                return

        if new_props:
            current_props = self.editor.things[cat_key][target_id]['props']
            current_props.update(new_props)
            self.load_ids_from_entry() 

        new_sprite_ids = []
        last_spr_id = self.spr.sprite_count
        
        for pil_img in new_images:

            if pil_img.size != (32, 32):
                pil_img = pil_img.resize((32, 32))
                
            last_spr_id += 1
            self.spr.replace_sprite(last_spr_id, pil_img)
            new_sprite_ids.append(last_spr_id)
            
        self.status_label.setText(f"Sprites adicionadas ao SPR. IDs: {new_sprite_ids[0]} - {new_sprite_ids[-1]}")

    
    
        is_outfit = (cat_key == 'outfits')
        
        width = 1
        height = 1
        layers = 1
        pattern_x = 1
        pattern_y = 1
        pattern_z = 1
        frames = len(new_sprite_ids)
        
        if is_outfit:
            # Usa o construtor com suporte a FrameGroups
            new_texture_bytes = self.build_outfit_texture_bytes(
                width, height, frames, new_sprite_ids
            )
        else:
            # Usa o construtor padrão (Item/Effect/Missile)
            new_texture_bytes = self.build_texture_bytes(
                width, height, 1, 1, 1, 1, frames, new_sprite_ids
            )
        
        self.editor.things[cat_key][target_id]['texture_bytes'] = new_texture_bytes
        
        self.on_preview_click() 
        QMessageBox.information(self, "Sucesso", "Importado com sucesso!")

        
    def on_context_replace(self):
        if not self.right_click_target:
            return
            
        target_id = self.right_click_target["id"]
        target_type = self.right_click_target["type"]
        
        if target_type != "sprite_list":
            QMessageBox.information(self, "Info", "Replace is currently only supported for Sprite List direct editing.")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Image Files (*.png *.bmp)"
        )
        
        if not file_path:
            return

        try:
            new_image = Image.open(file_path)
            
            self.spr.replace_sprite(target_id, new_image)
            
            self.refresh_sprite_list()
            self.status_label.setText(f"Sprite {target_id} replaced successfully.")
            self.status_label.setStyleSheet("color: green;")
            
            if self.selected_sprite_id == target_id:
                self.show_preview_at_index(self.current_preview_index)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to replace sprite: {e}")
            
        self.hide_loading()
        
        
    def on_category_change(self, text):
        self.ids_list_frame.scroll_layout.itemAt(0).widget().hide() 
        self.current_ids = []     
        self.load_ids_from_entry()
        
        

    def insert_ids(self):
        if not self.editor:
            QMessageBox.warning(self, "Warning", "Load a .dat file first.")
            return
        
        id_string = self.id_operation_entry.text().strip()
        ids_to_insert = []


        if not id_string:

            next_id = self.editor.counts['items'] + 1
            ids_to_insert = [next_id]
        else:
            ids_to_insert = self.parse_ids(id_string)
        
        if not ids_to_insert:
            QMessageBox.critical(self, "Error", "Invalid ID format.")

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
            self.status_label.setText(f"{inserted_count} ID(s) successfully inserted.")
            self.status_label.setStyleSheet("color: green;")
            self.refresh_id_list()
            self.id_operation_entry.clear()
            

            if len(ids_to_insert) == 1:
                self.load_single_id(ids_to_insert[0])
                
                target_page = (ids_to_insert[0] - 100) // self.ids_per_page
                if self.current_page != target_page:
                    self.current_page = target_page
                    self.refresh_id_list()
        else:
            self.status_label.setText("No new IDs were inserted (they already exist).")
            self.status_label.setStyleSheet("color: yellow;")

    def delete_ids(self):
        if not self.editor:
            QMessageBox.warning(self, "Warning", "Load a .dat file first.")
            return

        id_string = self.id_operation_entry.text().strip()
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

        reply = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"This will modify {len(ids_to_delete)} items.\n"
            "IDs in the middle of the list will be cleared.\n"
            "IDs at the end of the list will be removed.\n"
            "Do you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
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
            
        self.status_label.setText(status_message)
        self.status_label.setStyleSheet("color: orange;")

        self.current_ids = []
        self.refresh_id_list()
        self.id_operation_entry.clear()
        self.id_entry.clear()
        self.clear_preview()


    def update_color_preview(self, attr_name):
        entry = self.numeric_entries.get(attr_name)
        preview = self.numeric_previews.get(attr_name)
        
        if not entry or not preview:
            return
        
        try:
            val = entry.text().strip()
            if not val:
                preview.setStyleSheet("background-color: black; border: 1px solid gray;")
                return
                
            idx = int(val)
            
            if attr_name == "ShowOnMinimap":

                if 0 <= idx <= 215:
                    r, g, b = ob_index_to_rgb(idx)
                    preview.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); border: 1px solid gray;")
                else:
                    preview.setStyleSheet("background-color: red; border: 1px solid gray;")
            elif attr_name == "HasLight_Color":

                if 0 <= idx <= 65535:
                    r, g, b = self.light_color_to_rgb(idx)
                    preview.setStyleSheet(f"background-color: rgb({r}, {g}, {b}); border: 1px solid gray;")
                else:
                    preview.setStyleSheet("background-color: red; border: 1px solid gray;")
        except ValueError:
            preview.setStyleSheet("background-color: gray; border: 1px solid gray;")

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

        while self.ids_list_frame.scroll_layout.count():
            item = self.ids_list_frame.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.id_buttons.clear()
        
        if not self.editor:
            return 

        self.show_loading("Loading...\nPlease wait.")            

        cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
        current_cat_key = cat_map.get(self.category_combo.currentText(), "items")
        
        start_id_offset = 100 if current_cat_key == "items" else 1
        
        total_count = self.editor.counts[current_cat_key]
        
        start_index = self.current_page * self.ids_per_page
        current_start_id = start_index + start_id_offset

        max_id = total_count + 1
        
        end_id = min(current_start_id + self.ids_per_page, max_id)

        for item_id in range(current_start_id, end_id):

            item_frame = QFrame()
            item_frame.setFrameShape(QFrame.Shape.NoFrame)
            item_layout = QHBoxLayout(item_frame)
            item_layout.setContentsMargins(2, 1, 2, 1)
            
            sprite_label = ClickableLabel()
            sprite_label.setMinimumSize(80, 80)
            sprite_label.setMaximumSize(80, 80)
            sprite_label.setStyleSheet("background-color: #222121; border: 1px solid gray;")
            sprite_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            if self.spr and item_id in self.editor.things[current_cat_key]:
                item = self.editor.things[current_cat_key][item_id]
                sprite_ids = DatEditor.extract_sprite_ids_from_texture_bytes(item['texture_bytes'])
                
                if sprite_ids and sprite_ids[0] > 0:
                    try:
                        img = self.spr.get_sprite(sprite_ids[0])
                        if img:
                            img_resized = img.resize((72, 72), Image.NEAREST)
                            pixmap = pil_to_qpixmap(img_resized)
                            sprite_label.setPixmap(pixmap.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    except Exception as e:
                        print(f"Erro sprite {item_id}: {e}")
            
            item_layout.addWidget(sprite_label)
            
            id_label = ClickableLabel(str(item_id))
            id_label.setStyleSheet("background-color: gray15; padding: 5px;")
            id_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item_layout.addWidget(id_label, 1)
            
            def make_load_handler(iid):
                return lambda: self.load_single_id(iid)
            
            def make_context_handler(iid):
                return lambda pos: self.show_context_menu(pos, iid, "id_list")
            
            sprite_label.doubleClicked.connect(make_load_handler(item_id))
            id_label.doubleClicked.connect(make_load_handler(item_id))
            
            sprite_label.rightClicked.connect(make_context_handler(item_id))
            id_label.rightClicked.connect(make_context_handler(item_id))
                
            self.id_buttons[item_id] = id_label
            self.ids_list_frame.scroll_layout.addWidget(item_frame)

        nav_frame = QFrame()
        nav_layout = QHBoxLayout(nav_frame)
        nav_layout.setContentsMargins(5, 5, 5, 5)

        if self.current_page > 0:
            prev_btn = QPushButton("⟵")
            prev_btn.setMaximumWidth(60)
            prev_btn.clicked.connect(self.prev_page)
            nav_layout.addWidget(prev_btn)

        if end_id < max_id:
            next_btn = QPushButton("⟶")
            next_btn.setMaximumWidth(60)
            next_btn.clicked.connect(self.next_page)
            nav_layout.addWidget(next_btn)
            
        self.ids_list_frame.scroll_layout.addWidget(nav_frame)
        self.ids_list_frame.scroll_layout.addStretch()
        self.hide_loading()

            
    def refresh_sprite_list(self):
        # Clear existing widgets
        while self.sprite_list_frame.scroll_layout.count():
            item = self.sprite_list_frame.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self.sprite_thumbs.clear()
        self.visible_sprite_widgets = {} 

        if not self.spr: return
        
        self.show_loading("Loading...\nPlease wait.")

        total = self.spr.sprite_count
        start = self.sprite_page * self.sprites_per_page + 1
        end = min(start + self.sprites_per_page, total + 1)

        for spr_id in range(start, end):
            item_frame = QFrame()
            item_frame.setFrameShape(QFrame.Shape.NoFrame)
            item_layout = QHBoxLayout(item_frame)
            item_layout.setContentsMargins(2, 1, 2, 1)

            is_current = (spr_id == self.selected_sprite_id)
            
            bg_color = "#555555" if is_current else "transparent"
            txt_color = "cyan" if is_current else "white"

            def make_click_handler(sid):
                return lambda: self.select_sprite(sid, from_preview_click=False)

            img_label = DraggableLabel(sprite_id=spr_id)          
            img_label.setMinimumSize(80, 80)
            img_label.setMaximumSize(80, 80)
            img_label.setStyleSheet("background-color: #222121; border: 1px solid gray;")
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            text_label = ClickableLabel(str(spr_id))
            text_label.setMinimumWidth(60)
            text_label.setStyleSheet(f"background-color: {bg_color}; color: {txt_color}; padding: 5px;")
            text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            
            self.visible_sprite_widgets[spr_id] = text_label

            img = self.spr.get_sprite(spr_id)
            if img:
                thumb = img.resize((72, 72), Image.NEAREST)
                pixmap = pil_to_qpixmap(thumb)
                img_label.setPixmap(pixmap.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

            item_layout.addWidget(img_label)
            item_layout.addWidget(text_label, 1)
            
            img_label.doubleClicked.connect(make_click_handler(spr_id))
            text_label.doubleClicked.connect(make_click_handler(spr_id))
            
            
            def make_context_handler(sid):
                return lambda pos: self.show_context_menu(pos, sid, "sprite_list")
            
            img_label.rightClicked.connect(make_context_handler(spr_id))
            text_label.rightClicked.connect(make_context_handler(spr_id))

            self.sprite_list_frame.scroll_layout.addWidget(item_frame)

        nav = QFrame()
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(5, 5, 5, 5)

        if self.sprite_page > 0:
            prev_btn = QPushButton("⟵")
            prev_btn.setMaximumWidth(60)
            prev_btn.clicked.connect(self.prev_sprite_page)
            nav_layout.addWidget(prev_btn)

        if end <= total:
            next_btn = QPushButton("⟶")
            next_btn.setMaximumWidth(60)
            next_btn.clicked.connect(self.next_sprite_page)
            nav_layout.addWidget(next_btn)
    
        self.sprite_list_frame.scroll_layout.addWidget(nav)
        self.sprite_list_frame.scroll_layout.addStretch()
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
                    label_widget.setStyleSheet("background-color: #555555; color: cyan; padding: 5px;")
                except:
                    pass
            else:
                try:
                    label_widget.setStyleSheet("background-color: transparent; color: white; padding: 5px;")
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
            self.image_label.clear()
            self.image_label.setText("No sprite")
            self.prev_index_label.setText("Sprite 0 / 0")
            self.preview_info.setText("")
            return

        if self.current_preview_index < 0:
            self.current_preview_index = 0
        if self.current_preview_index >= len(self.current_preview_sprite_list):
            self.current_preview_index = 0

        sprite_id = self.current_preview_sprite_list[self.current_preview_index]

        img = self.spr.get_sprite(sprite_id)

        if img:
 
            preview_size = (32, 32) 
            img_resized = img.resize(preview_size, Image.NEAREST)

            pixmap = pil_to_qpixmap(img_resized)
            self.image_label.setPixmap(pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self._kept_image = pixmap
        else:
            self.image_label.clear()
            self.image_label.setText("Empty/Error")

        total = len(self.current_preview_sprite_list)
        self.prev_index_label.setText(f"Sprite {self.current_preview_index + 1} / {total}")
        self.preview_info.setText(f"Sprite ID: {sprite_id}")
                
    def on_preview_click(self):
        preview_list = getattr(self, 'current_preview_sprite_list', [])
        
        if not preview_list:
            return
        
        idx = getattr(self, 'current_preview_index', 0)
        if idx < 0 or idx >= len(preview_list):
            return

        current_sprite_id = preview_list[idx]
        
        self.select_sprite(current_sprite_id, from_preview_click=True) 
        
        if hasattr(self, 'status_label'):
            self.status_label.setText(f"Selected sprite {current_sprite_id} from preview.")
            self.status_label.setStyleSheet("color: cyan;")

            
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
            QTimer.singleShot(50, lambda: self._scroll_to_sprite(sprite_id))
        except:
            pass


    def _scroll_to_sprite(self, sprite_id):
        index_in_page = (sprite_id - 1) % self.sprites_per_page
        scroll_pos = index_in_page / self.sprites_per_page
        scrollbar = self.sprite_list_frame.scroll.verticalScrollBar()
        if scrollbar:
            max_val = scrollbar.maximum()
            scrollbar.setValue(int(scroll_pos * max_val))


    def load_single_id(self, item_id):
        if not self.editor: return

        cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
        current_cat_key = cat_map.get(self.category_combo.currentText(), "items")

        self.current_ids = [item_id]
        self.id_entry.setText(str(item_id))

        self.update_checkboxes_for_ids(current_cat_key) 
        self.prepare_preview_for_current_ids(current_cat_key)

        for iid, button in self.id_buttons.items():
            if iid == item_id:
                button.setStyleSheet("background-color: #555555; color: cyan; padding: 5px;")
            else:
                button.setStyleSheet("background-color: gray15; color: white; padding: 5px;")

        self.status_label.setText(f"ID {item_id} ({current_cat_key}) loaded.")
        self.status_label.setStyleSheet("color: cyan;")



    def disable_editing(self):
        self.id_entry.setEnabled(False)
        self.load_ids_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.save_button.setEnabled(False)
        for cb in self.checkboxes.values():
            cb.setEnabled(False)
        for entry in self.numeric_entries.values():
            entry.setEnabled(False)
        self.insert_id_button.setEnabled(False)  
        self.delete_id_button.setEnabled(False)       

    def enable_editing(self):
        self.id_entry.setEnabled(True)
        self.load_ids_button.setEnabled(True)
        self.apply_button.setEnabled(True)
        self.save_button.setEnabled(True)
        self.insert_id_button.setEnabled(True)  
        self.delete_id_button.setEnabled(True)     
        for cb in self.checkboxes.values():
            cb.setEnabled(True)
        for entry in self.numeric_entries.values():
            entry.setEnabled(True)        
          
    def load_dat_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select the .dat file",
            "",
            "DAT files (*.dat);;All files (*.*)"
        )
        if not filepath:
            return

        self.show_loading("Loading...\nPlease wait.")
        
        is_extended = self.chk_extended.isChecked()
        is_transparency = self.chk_transparency.isChecked()
        
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
                self.spr = SprEditor(spr_path, transparency=is_transparency)
                self.spr.load()

    
                self.preview_info.setText(
                    f"SPR loaded: {os.path.basename(spr_path)}\nSprites: {self.spr.sprite_count}"
                )
                self.sprite_page = 0

                self.refresh_sprite_list()
          
            self.refresh_id_list()                

        except Exception as e:
            print(e)
            QMessageBox.critical(self, "Load Error", f"Could not load or parse the file:\n{e}")
            self.status_label.setText("Failed to load the file.")
            self.status_label.setStyleSheet("color: red;")

        finally:
            self.hide_loading()
            
            spr_count = 0
            if hasattr(self, 'spr') and self.spr is not None:
                spr_count = self.spr.sprite_count

            self.status_label.setText(
                f"Files loaded! "
                f"Items: {self.editor.counts['items']}  /  "
                f"Outfits: {self.editor.counts['outfits']}  /  "
                f"Effects: {self.editor.counts['effects']}  /  "
                f"Missiles: {self.editor.counts['missiles']}  /  "
                f"Sprite Total: {spr_count}"
            )
            self.status_label.setStyleSheet("color: cyan;")
                           
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
            self.status_label.setText("Error: Invalid ID format.")
            self.status_label.setStyleSheet("color: orange;")
      
            return []

    def load_ids_from_entry(self):
        if not self.editor: return
        
        id_string = self.id_entry.text()
        self.current_ids = self.parse_ids(id_string)
        
        if not self.current_ids:
            if id_string:
                QMessageBox.warning(self, "Invalid IDs", "Incorrect format.")
            for cb in self.checkboxes.values():
                cb.setChecked(False)
            self.clear_preview()
            return


        cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
        current_cat_key = cat_map.get(self.category_combo.currentText(), "items")

        self.status_label.setText(f"Consultando {len(self.current_ids)} IDs...")
        self.status_label.setStyleSheet("color: cyan;")
        
        self.update_checkboxes_for_ids(category=current_cat_key)
        self.status_label.setText(f"{len(self.current_ids)} IDs loaded...")
        self.status_label.setStyleSheet("color: white;")
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
                    button.setStyleSheet("background-color: #555555; color: cyan; padding: 5px;")
                else:
                    button.setStyleSheet("background-color: gray15; color: white; padding: 5px;")

            try:
                index_in_page = (first_id - base_offset) % self.ids_per_page
                scroll_pos = max(0, index_in_page / self.ids_per_page)
                scrollbar = self.ids_list_frame.scroll.verticalScrollBar()
                if scrollbar:
                    max_val = scrollbar.maximum()
                    scrollbar.setValue(int(scroll_pos * max_val))
            except Exception:
                pass

    def update_checkboxes_for_ids(self, category="items"):
        if not self.current_ids: return
        
        things_dict = self.editor.things.get(category, {})

        for attr_name, cb in self.checkboxes.items():

            states = [attr_name in things_dict[item_id]['props'] 
                     for item_id in self.current_ids if item_id in things_dict]
            
            if not states:
                cb.setChecked(False)
                cb.setStyleSheet("color: gray;")
            elif all(states):
                cb.setChecked(True)
                cb.setStyleSheet("color: white;")
            elif not any(states):
                cb.setChecked(False)
                cb.setStyleSheet("color: white;")
            else:
                cb.setChecked(False)
                cb.setStyleSheet("color: cyan;")
        
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
            entry.clear()
            if entry_key in self.numeric_previews:
                self.numeric_previews[entry_key].setStyleSheet("background-color: #888888; border: 1px solid gray;")
        elif all(v == values[0] for v in values):
            entry.setText(str(values[0]))
            if entry_key in self.numeric_previews:
                self.update_color_preview(entry_key)
        else:
            entry.clear()
            if entry_key in self.numeric_previews:
                self.numeric_previews[entry_key].setStyleSheet("background-color: gray; border: 1px solid gray;")

    def apply_changes(self):
        if not self.editor or not self.current_ids:
            QMessageBox.warning(self, "No Action", "Load a file and check some IDs first.")
            return

        to_set, to_unset = [], []
        original_states = {}

        cat_map = {"Item": "items", "Outfit": "outfits", "Effect": "effects", "Missile": "missiles"}
        current_cat_key = cat_map.get(self.category_combo.currentText(), "items")
        
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
            if cb.isChecked() and original_states[attr_name] != 'all':
                to_set.append(attr_name)
            elif not cb.isChecked() and original_states[attr_name] != 'none':
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
            self.status_label.setText("No changes detected.")
            self.status_label.setStyleSheet("color: yellow;")
            return
     
        self.status_label.setText("Changes applied. Save with 'Compile as...'")
        self.status_label.setStyleSheet("color: green;")
        
        self.update_checkboxes_for_ids(category=current_cat_key)
        self.prepare_preview_for_current_ids(category=current_cat_key)


    def apply_numeric_attribute(self, entry_key, data_key, index, signed, category="items"):
        entry = self.numeric_entries.get(entry_key)
        if not entry: return False
        val_str = entry.text().strip()
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
        
        x_str = x_entry.text().strip()
        y_str = y_entry.text().strip()
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
        
        level_str = level_entry.text().strip()
        color_str = color_entry.text().strip()
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
            QMessageBox.critical(self, "Error", "No .dat file is loaded.")
            return
            
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save DAT and SPR file as...",
            "",
            "DAT files (*.dat);;All files (*.*)"
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

            self.status_label.setText(f"Saved successfully: {os.path.basename(filepath)}")
            self.status_label.setStyleSheet("color: #90ee90;") # Light green
            
            QMessageBox.information(self, "Success", f"Files compiled successfully!{msg_extra}")
            
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save the file:\n{e}")
            self.status_label.setText("Failed to save files.")
            self.status_label.setStyleSheet("color: red;")

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
            self.image_label.clear()
            self.image_label.setText("No sprite")
        except Exception:
            pass
            
        self._kept_image = None
        self.preview_info.setText("No sprite available.")
        self.current_preview_sprite_list = []
        self.current_preview_index = 0

    def change_preview_index(self, delta):
        if not self.current_preview_sprite_list:
            return
            
        new_index = self.current_preview_index + delta
        
        if 0 <= new_index < len(self.current_preview_sprite_list):
            self.current_preview_index = new_index
            self.show_preview_at_index(self.current_preview_index)

    def show_preview_at_index(self, anim_frame_index):
        if not self.current_preview_sprite_list:
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("No Sprite")
            return

        cat_key = self.get_current_category_key()
        
        # Propriedades salvas do item atual
        # Certifique-se de que essas variaveis (current_item_*) estão sendo setadas no load_ids_from_entry
        # Se não estiverem, use self.editor.things[cat_key][id]['props'] aqui mesmo.
        width = getattr(self, 'current_item_width', 1)
        height = getattr(self, 'current_item_height', 1)
        layers = getattr(self, 'current_item_layers', 1)
        pat_x = getattr(self, 'current_item_pat_x', 1)
        pat_y = getattr(self, 'current_item_pat_y', 1)
        
        # Tamanho de um bloco visual (1 frame de animação em 1 ângulo)
        sprites_per_view = width * height * layers
        
        dir_offset = 0
        
        # --- LÓGICA DE OUTFIT ---
        if cat_key == 'outfits':
            # Mapeia as chaves para os índices do Tibia (0=N, 1=E, 2=S, 3=W)
            # Outfits não têm diagonais, então mapeamos diagonais para os cardeais mais próximos
            outfit_dir_map = {
                "N": 0, "NW": 0, "NE": 0,
                "E": 1, 
                "S": 2, "SE": 2, "SW": 2,
                "W": 3,
                "C": 2 # Centro -> Sul
            }
            dir_idx = outfit_dir_map.get(self.current_direction_key, 2)
            
            # Pula frames de animação + direção
            # Cada frame de animação tem 4 direções
            sprites_per_anim_step = sprites_per_view * 4
            base_index = anim_frame_index * sprites_per_anim_step
            dir_offset = dir_idx * sprites_per_view
            
            final_start_index = base_index + dir_offset

        # --- LÓGICA DE MISSILE ---
        elif cat_key == 'missiles' and pat_x == 3 and pat_y == 3:
            # Míssil Direcional (3x3 = 9 sprites)
            # Mapeamento da Matriz 3x3
            missile_map = {
                "NW": 0, "N": 1, "NE": 2,
                "W": 3,  "C": 4, "E": 5,
                "SW": 6, "S": 7, "SE": 8
            }
            # Se a direção não existe no mapa, usa Centro (4) ou N (1)
            dir_idx = missile_map.get(self.current_direction_key, 4)
            
            # Mísseis não têm "Direções" da mesma forma que Outfits.
            # As direções SÃO os Patterns X/Y.
            # Então cada "frame de animação" contém todas as 9 direções.
            
            # Total de sprites por frame de animação = 9 * sprites_per_view
            sprites_per_anim_step = sprites_per_view * 9
            base_index = anim_frame_index * sprites_per_anim_step
            
            # O offset é simplesmente o índice da matriz (0 a 8)
            dir_offset = dir_idx * sprites_per_view
            
            final_start_index = base_index + dir_offset
            
        else:
            # --- OUTROS (Itens, Effects, Mísseis simples) ---
            # Ignora direção, mostra sequencial
            sprites_per_anim_step = sprites_per_view # * 1
            final_start_index = anim_frame_index * sprites_per_anim_step

        # --- RENDER ---
        # (O resto do código de renderização permanece igual)
        # --- RENDER ---
        total_w = width * 32
        total_h = height * 32
        combined_image = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
        
        current_spr_idx = final_start_index
        
        # ... (código anterior da função permanece igual) ...
        
        # --- RENDER NO PIL (Sem desenhar borda aqui) ---
        try:
            for l in range(layers):
                for y in range(height):
                     for x in range(width):
                        if current_spr_idx >= len(self.current_preview_sprite_list): break
                        
                        sprite_id = self.current_preview_sprite_list[current_spr_idx]
                        current_spr_idx += 1
                        
                        if sprite_id > 0 and self.spr:
                            img_data = self.spr.get_sprite(sprite_id)
                            if img_data:
                                px = (width - 1 - x) * 32
                                py = (height - 1 - y) * 32
                                combined_image.paste(img_data, (px, py), img_data)
        except Exception as e:
            print(f"Preview error: {e}")

        # 1. Converte para QPixmap
        qpix = pil_to_qpixmap(combined_image)
        
        # 2. Aplica o Zoom (2x)
        # O tamanho de cada sprite na tela será 64x64 (32 * 2)
        zoom_factor = 2
        qpix = qpix.scaled(total_w * zoom_factor, total_h * zoom_factor, 
                           Qt.AspectRatioMode.KeepAspectRatio, 
                           Qt.TransformationMode.FastTransformation)

        # 3. Desenha a Grade Fina usando QPainter (Sobre o Pixmap já ampliado)
        if width > 1 or height > 1:
            painter = QPainter(qpix)
            
            # Caneta Branca, Espessura 1 (Cosmetic Pen), Sólida
            pen = QColor(255, 255, 255, 200) # Branco com leve transparência (200 alpha)
            painter.setPen(pen)
            
            sprite_screen_size = 32 * zoom_factor # 64px
            
            for gx in range(width):
                for gy in range(height):
                    # Calcula posição na tela
                    x0 = gx * sprite_screen_size
                    y0 = gy * sprite_screen_size
                    
                    # Desenha o retangulo. Subtraímos 1 do tamanho para ficar dentro da imagem
                    painter.drawRect(x0, y0, sprite_screen_size - 1, sprite_screen_size - 1)
            
            painter.end()

        self.image_label.setPixmap(qpix)
        
        self.prev_index_label.setText(f"Frame: {anim_frame_index} | Dir: {self.current_direction_key}")




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
        self.loading_overlay = QFrame(self)
        self.loading_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        self.loading_overlay.hide()

        # Layout para centralizar o texto
        overlay_layout = QVBoxLayout(self.loading_overlay)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.loading_label = QLabel("Loading...", self.loading_overlay)
        self.loading_label.setStyleSheet("font-size: 24px; font-weight: bold; color: white; background: transparent;")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        overlay_layout.addWidget(self.loading_label)

    def show_loading(self, message="Loading..."):
        if hasattr(self, 'loading_overlay'):
            self.loading_label.setText(message)
            self.loading_overlay.resize(self.size()) 
            self.loading_overlay.raise_()
            self.loading_overlay.show()
            
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

    def hide_loading(self):
        if hasattr(self, 'loading_overlay'):
            self.loading_overlay.hide()

    def resizeEvent(self, event):
        if hasattr(self, 'loading_overlay') and self.loading_overlay.isVisible():
            self.loading_overlay.resize(self.size())
        super().resizeEvent(event)
