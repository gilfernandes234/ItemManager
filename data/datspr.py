import atexit
import io
import os
import re
import shutil
import struct
import sys
import uuid

from collections import OrderedDict
from copy import deepcopy

from particleEditor import ParticleGenerator
from shaderEditor import ShaderEditor
from spell_maker import SpellMakerWindow
from obdHandler import ObdHandler
from looktype_generator import LookTypeGeneratorWindow
from monster_generator import MonsterGeneratorWindow
from spriteEditor import SliceWindow
from spriteOptmizer import SpriteOptimizerWindow

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(BASE_DIR, "..", "assets", "window")

from interface_utils import ToggleSwitch, ModernLabel


from PIL import Image, ImageDraw, ImageFilter
from PyQt6.QtCore import Qt, QTimer, QSize, QSettings, QPoint, pyqtSignal, QRect
from PyQt6.QtGui import (
    QColor,
    QContextMenuEvent,
    QCursor,
    QDrag,
    QIcon,
    QImage,
    QKeyEvent,
    QPainter,
    QPixmap,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsObject,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QLayout,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QSlider,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

METADATA_FLAGS = {
    0x00: ("Ground", "<H"),
    0x01: ("GroundBorder", ""),
    0x02: ("OnBottom", ""),
    0x03: ("OnTop", ""),
    0x04: ("Container", ""),
    0x05: ("Stackable", ""),
    0x06: ("ForceUse", ""),
    0x07: ("MultiUse", ""),
    0x08: ("Writable", "<H"),
    0x09: ("WritableOnce", "<H"),
    0x0A: ("FluidContainer", ""),
    0x0B: ("IsFluid", ""),
    0x0C: ("Unpassable", ""),
    0x0D: ("Unmoveable", ""),
    0x0E: ("BlockMissile", ""),
    0x0F: ("BlockPathfind", ""),
    0x10: ("NoMoveAnimation", ""),
    0x11: ("Pickupable", ""),
    0x12: ("Hangable", ""),
    0x13: ("HookVertical", ""),
    0x14: ("HookHorizontal", ""),
    0x15: ("Rotatable", ""),
    0x16: ("HasLight", "<HH"),
    0x17: ("DontHide", ""),
    0x18: ("Translucent", ""),
    0x19: ("HasOffset", "<hh"),
    0x1A: ("HasElevation", "<H"),
    0x1B: ("LyingObject", ""),
    0x1C: ("AnimateAlways", ""),
    0x1D: ("ShowOnMinimap", "<H"),
    0x1E: ("LensHelp", "<H"),
    0x1F: ("FullGround", ""),
    0x20: ("IgnoreLook", ""),
    0x21: ("IsCloth", "<H"),
    0x22: ("MarketItem", None),
    0x23: ("DefaultAction", "<H"),
    0x24: ("Wrappable", ""),
    0x25: ("Unwrappable", ""),
    0x26: ("TopEffect", ""),
    0x27: ("Usable", ""),
    0x28: ("ChangedToExpire", "<H"),
    0x29: ("Corpse", ""),
    0x2A: ("PlayerCorpse", ""),
    0x2B: ("CyclopediaItem", "<H"),
    0x2C: ("Ammo", ""),
    0x2D: ("ShowOffSocket", ""),
    0x2E: ("Reportable", ""),
    0x2F: ("UpgradeClassification", "<H"),
    0x30: ("Wearout", ""),
    0x31: ("ClockExpire", ""),
    0x32: ("Expire", ""),
    0x33: ("ExpireStop", ""),
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

        self.counts = {"items": 0, "outfits": 0, "effects": 0, "missiles": 0}
        self.things = {"items": {}, "outfits": {}, "effects": {}, "missiles": {}}

    def load(self):
        with open(self.dat_path, "rb") as f:
            self.signature = struct.unpack("<I", f.read(4))[0]
            item_count, outfit_count, effect_count, missile_count = struct.unpack(
                "<HHHH", f.read(8)
            )
            self.counts = {
                "items": item_count,
                "outfits": outfit_count,
                "effects": effect_count,
                "missiles": missile_count,
            }

            for item_id in range(100, self.counts["items"] + 1):
                self.things["items"][item_id] = self._parse_thing(f, "items")

            for outfit_id in range(1, self.counts["outfits"] + 1):
                self.things["outfits"][outfit_id] = self._parse_thing(f, "outfits")

            for effect_id in range(1, self.counts["effects"] + 1):
                self.things["effects"][effect_id] = self._parse_thing(f, "effects")

            for missile_id in range(1, self.counts["missiles"] + 1):
                self.things["missiles"][missile_id] = self._parse_thing(f, "missiles")

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

                if name == "MarketItem":
                    # Lógica específica do Market
                    header = f.read(8)
                    if len(header) == 8:
                        # header: [Category:2][TradeAs:2][ShowAs:2][NameLen:2]
                        name_len = struct.unpack("<H", header[6:8])[0]
                        # Resto: [Name:Len][Voc:2][Level:2] = Len + 4 bytes
                        rest = f.read(name_len + 4)
                        props[name] = True
                        props[name + "_data"] = header + rest
                else:
                    props[name] = True
                    if fmt:
                        size = struct.calcsize(fmt)
                        data = f.read(size)
                        props[name + "_data"] = struct.unpack(fmt, data)

        texture_bytes = bytearray()

        if category == "outfits":
            b = f.read(1)
            if not b:
                return {"props": props, "texture_bytes": bytes(texture_bytes)}
            texture_bytes.extend(b)
            fg_count = b[0]
            props["FrameGroupCount"] = fg_count

            for i in range(fg_count):
                # Type (Idle/Walk)
                b = f.read(1)
                texture_bytes.extend(b)
                if i == 0:
                    props["FrameGroupType"] = b[0]

                # Width / Height
                b = f.read(2)
                texture_bytes.extend(b)
                w, h = struct.unpack("<BB", b)

                if i == 0:
                    props["Width"] = w
                    props["Height"] = h

                # Crop Size (Se maior que 1x1)
                if w > 1 or h > 1:
                    b = f.read(1)
                    texture_bytes.extend(b)
                    if i == 0:
                        props["CropSize"] = b[0]

                # Headers de Animação
                b = f.read(5)  # Layers, Px, Py, Pz, Frames
                texture_bytes.extend(b)
                layers, px, py, pz, frames = struct.unpack("<BBBBB", b)

                if i == 0:
                    props["Layers"] = layers
                    props["PatternX"] = px
                    props["PatternY"] = py
                    props["PatternZ"] = pz
                    props["Animation"] = frames

                # Animation Details (Timing)
                if frames > 1:
                    # Async(1) + Loop(4) + Start(1) + Durations(frames * 8)
                    # detail_size = 1 + 4 + 1 + (frames * 8)
                    # b = f.read(detail_size)
                    
                    # 1. Async
                    b = f.read(1)
                    texture_bytes.extend(b)
                    props["AnimAsync"] = b[0]
                    
                    # 2. Loop Count
                    b = f.read(4)
                    texture_bytes.extend(b)
                    props["AnimLoop"] = struct.unpack("<I", b)[0]
                    
                    # 3. Start Frame
                    b = f.read(1)
                    texture_bytes.extend(b)
                    props["AnimStart"] = b[0]
                    
                    # 4. Frame Durations (8 bytes each: 4 min, 4 max)
                    durations = []
                    for _ in range(frames):
                         b = f.read(8)
                         texture_bytes.extend(b)
                         min_dur, max_dur = struct.unpack("<II", b)
                         durations.append((min_dur, max_dur))
                    props["FrameDurations"] = durations

                # Sprite IDs
                total_sprites = w * h * px * py * pz * layers * frames
                spr_size = 4 if self.extended else 2

                b = f.read(total_sprites * spr_size)
                texture_bytes.extend(b)

        else:
            # --- ITEM / EFFECT / MISSILE STRUCTURE ---
            # Width / Height
            b = f.read(2)
            if not b:
                return {"props": props, "texture_bytes": bytes(texture_bytes)}
            texture_bytes.extend(b)

            w, h = struct.unpack("<BB", b)
            props["Width"] = w
            props["Height"] = h
            props["CropSize"] = 0

            # Crop Size
            if w > 1 or h > 1:
                b = f.read(1)
                texture_bytes.extend(b)
                props["CropSize"] = b[0]

            # Headers
            b = f.read(5)
            texture_bytes.extend(b)
            layers, px, py, pz, frames = struct.unpack("<BBBBB", b)

            props["Layers"] = layers
            props["PatternX"] = px
            props["PatternY"] = py
            props["PatternZ"] = pz
            props["Animation"] = frames

            # Animation Details
            if frames > 1:
                # detail_size = 1 + 4 + 1 + (frames * 8)
                # b = f.read(detail_size)

                # 1. Async
                b = f.read(1)
                texture_bytes.extend(b)
                props["AnimAsync"] = b[0]

                # 2. Loop Count
                b = f.read(4)
                texture_bytes.extend(b)
                props["AnimLoop"] = struct.unpack("<I", b)[0]

                # 3. Start Frame
                b = f.read(1)
                texture_bytes.extend(b)
                props["AnimStart"] = b[0]

                # 4. Frame Durations
                durations = []
                for _ in range(frames):
                     b = f.read(8)
                     texture_bytes.extend(b)
                     min_dur, max_dur = struct.unpack("<II", b)
                     durations.append((min_dur, max_dur))
                props["FrameDurations"] = durations

            # Sprite IDs
            total_sprites = w * h * px * py * pz * layers * frames
            spr_size = 4 if self.extended else 2

            b = f.read(total_sprites * spr_size)
            texture_bytes.extend(b)

        return {"props": props, "texture_bytes": bytes(texture_bytes)}

    def apply_changes(
        self, item_ids, attributes_to_set, attributes_to_unset, category="items"
    ):
        if category not in self.things:
            return

        for item_id in item_ids:
            if item_id not in self.things[category]:
                continue

            item_props = self.things[category][item_id]["props"]

            for attr in attributes_to_set:
                if attr in REVERSE_METADATA_FLAGS:
                    item_props[attr] = True
                    flag_val = REVERSE_METADATA_FLAGS[attr]
                    _name, fmt = METADATA_FLAGS[flag_val]
                    if fmt:
                        data_key = attr + "_data"
                        if data_key not in item_props:
                            num_bytes = struct.calcsize(fmt)
                            num_values = len(struct.unpack(fmt, b"\x00" * num_bytes))
                            item_props[data_key] = tuple([0] * num_values)

            for attr in attributes_to_unset:
                if attr in REVERSE_METADATA_FLAGS and attr in item_props:
                    del item_props[attr]
                    if attr + "_data" in item_props:
                        del item_props[attr + "_data"]

    def save(self, output_path):
        with open(output_path, "wb") as f:
            f.write(struct.pack("<I", self.signature))

            count_items = self.counts["items"]
            count_outfits = self.counts["outfits"]
            count_effects = self.counts["effects"]
            count_missiles = self.counts["missiles"]

            f.write(
                struct.pack(
                    "<HHHH", count_items, count_outfits, count_effects, count_missiles
                )
            )

            def write_category(start_id, end_id, category_name):
                for tid in range(start_id, end_id + 1):
                    thing = self.things[category_name].get(tid)

                    if thing and len(thing.get("texture_bytes", b"")) > 0:
                        self._write_thing_properties(f, thing["props"])

                        f.write(struct.pack("<B", LAST_FLAG))

                        f.write(thing["texture_bytes"])
                    else:
                        f.write(struct.pack("<B", LAST_FLAG))
                        f.write(b"\x01\x01\x01\x01\x01\x01\x01")

                        if self.extended:
                            f.write(b"\x00\x00\x00\x00")
                        else:
                            f.write(b"\x00\x00")

            #  Items
            write_category(100, count_items, "items")

            #  Outfits
            write_category(1, count_outfits, "outfits")

            #  Effects
            write_category(1, count_effects, "effects")

            #  Missiles (
            write_category(1, count_missiles, "missiles")

    def _write_thing_properties(self, f, props):
        for flag, (name, fmt) in METADATA_FLAGS.items():
            if name in props:
                if props[name] is True:
                    f.write(struct.pack("<B", flag))

                    data_key = name + "_data"
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
        if not texture_bytes:
            return []

        def try_parse(offset):
            ids = []
            try:
                w, h = struct.unpack_from("<BB", texture_bytes, offset)
                curr = offset + 2
                if w > 1 or h > 1:
                    curr += 1
                layers, px, py, pz, frames = struct.unpack_from(
                    "<BBBBB", texture_bytes, curr
                )
                curr += 5

                if frames > 1:
                    curr += 1 + 4 + 1 + (frames * 8)

                total = w * h * px * py * pz * layers * frames
                remaining = len(texture_bytes) - curr

                if total == 0:
                    return []

                spr_size = remaining // total
                if spr_size not in (2, 4):
                    return []

                fmt = "<I" if spr_size == 4 else "<H"
                for _ in range(total):
                    val = struct.unpack_from(fmt, texture_bytes, curr)[0]
                    ids.append(val)
                    curr += spr_size
                return ids
            except:
                return []

        result = try_parse(0)
        if result:
            return result

        result_outfit = try_parse(2)
        if result_outfit:
            return result_outfit

        return []

    @staticmethod
    def extract_sprite_ids_from_outfit_texture(texture_bytes):

        if not texture_bytes or len(texture_bytes) < 3:
            return []

        try:
            fg_count = texture_bytes[0]
            offset = 1

            for i in range(fg_count):
                if offset >= len(texture_bytes):
                    return []

                fg_type = texture_bytes[offset]
                offset += 1

                if offset + 2 > len(texture_bytes):
                    return []
                w, h = struct.unpack_from("BB", texture_bytes, offset)
                offset += 2

                if w > 1 or h > 1:
                    offset += 1

                if offset + 5 > len(texture_bytes):
                    return []
                layers, px, py, pz, frames = struct.unpack_from(
                    "<BBBBB", texture_bytes, offset
                )
                offset += 5

                if frames > 1:
                    offset += 1 + 4 + 1 + (frames * 8)

                if i == 0:
                    total_sprites = w * h * px * py * pz * layers * frames
                    remaining = len(texture_bytes) - offset

                    if total_sprites == 0:
                        return []

                    if remaining >= total_sprites * 4:
                        spr_size = 4
                    elif remaining >= total_sprites * 2:
                        spr_size = 2
                    else:
                        print(
                            f"DEBUG Outfit: Not enough bytes. Need {total_sprites * 2}, have {remaining}"
                        )
                        return []

                    fmt = "<I" if spr_size == 4 else "<H"
                    ids = []

                    for _ in range(total_sprites):
                        if offset + spr_size > len(texture_bytes):
                            break
                        sprite_id = struct.unpack_from(fmt, texture_bytes, offset)[0]
                        ids.append(sprite_id)
                        offset += spr_size

                    print(
                        f"DEBUG Outfit: w={w}, h={h}, layers={layers}, frames={frames}, total_sprites={total_sprites}, extracted={len(ids)}"
                    )
                    return ids
                else:
                    total_sprites = w * h * px * py * pz * layers * frames
                    if total_sprites > 0:
                        remaining = len(texture_bytes) - offset
                        spr_size = 4 if remaining >= total_sprites * 4 else 2
                        offset += total_sprites * spr_size

            return []

        except Exception as e:
            print(f"DEBUG: Error extracting outfit sprites: {e}")
            import traceback

            traceback.print_exc()
            return []

    @staticmethod
    def extract_outfit_group_sprites(texturebytes, target_fg_index=0, extended=True):

        if not texturebytes or len(texturebytes) < 3:
            return []

        try:
            fgcount = texturebytes[0]
            offset = 1

            for i in range(fgcount):
                if offset >= len(texturebytes):
                    return []

                # Frame Group Type
                fgtype = texturebytes[offset]
                offset += 1

                # Width/Height
                if offset + 2 > len(texturebytes):
                    return []
                w, h = struct.unpack_from("BB", texturebytes, offset)
                offset += 2

                # Crop size (se w>1 ou h>1)
                if w > 1 or h > 1:
                    if offset + 1 > len(texturebytes):
                        return []
                    offset += 1

                # Layers, PatternX/Y/Z, Frames
                if offset + 5 > len(texturebytes):
                    return []
                layers, px, py, pz, frames = struct.unpack_from(
                    "BBBBB", texturebytes, offset
                )
                offset += 5

                # Animation details
                if frames > 1:
                    detailsize = 1 + 4 + 1 + (frames * 8)
                    if offset + detailsize > len(texturebytes):
                        return []
                    offset += detailsize

                # Calcular total de sprites
                totalsprites = w * h * px * py * pz * layers * frames
                if totalsprites <= 0:
                    continue

                # Se não é o grupo alvo, pular os IDs
                if i != target_fg_index:
                    sprsize = 4 if extended else 2
                    offset += totalsprites * sprsize
                    continue

                # Extrair IDs do grupo alvo
                remaining = len(texturebytes) - offset
                sprsize = 4 if remaining >= totalsprites * 4 else 2
                fmt = "I" if sprsize == 4 else "H"

                ids = []
                for _ in range(totalsprites):
                    if offset + sprsize > len(texturebytes):
                        break
                    spriteid = struct.unpack_from(fmt, texturebytes, offset)[0]
                    ids.append(spriteid)
                    offset += sprsize

                return ids

            return []
        except Exception as e:
            print(f"ERROR extract_outfit_group_sprites: {e}")
            return []


class SprEditor:
    
    def __init__(self, spr_path, transparency=False):
        self.spr_path = spr_path
        self.transparency = transparency
        self.signature = 0
        self.sprite_count = 0
        self.sprites_data = {}
        self.modified = False

    def load(self, progress_callback=None):
        
        if not os.path.exists(self.spr_path):
            return

        with open(self.spr_path, "rb") as f:
            header = f.read(8)
            if len(header) < 8:
                raise ValueError("Invalid SPR file.")

            self.signature, self.sprite_count = struct.unpack("<II", header)

            offsets = []
            for _ in range(self.sprite_count):
                offsets.append(struct.unpack("<I", f.read(4))[0])

            file_size = f.seek(0, 2)

            total_iter = len(offsets)
            
            for i, offset in enumerate(offsets):
                if progress_callback and i % 2000 == 0:
                     progress_callback(i, total_iter)
                     
                sprite_id = i + 1
                if offset == 0:
                    self.sprites_data[sprite_id] = b""
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
        
        with open(output_path, "wb") as f:
            f.write(struct.pack("<II", self.signature, self.sprite_count))

            current_offset = 8 + (self.sprite_count * 4)

            offsets_start_pos = f.tell()
            f.write(b"\x00\x00\x00\x00" * self.sprite_count)

            final_offsets = []

            for sprite_id in range(1, self.sprite_count + 1):
                data = self.sprites_data.get(sprite_id, b"")

                if not data:
                    final_offsets.append(0)
                else:
                    final_offsets.append(current_offset)
                    f.write(data)
                    current_offset += len(data)

            f.seek(offsets_start_pos)
            for off in final_offsets:
                f.write(struct.pack("<I", off))

    def get_sprite(self, sprite_id):
        raw_data = self.sprites_data.get(sprite_id)
        if not raw_data:
            return None

        start_idx = 0
        if (
            len(raw_data) >= 3
            and raw_data[0] == 0xFF
            and raw_data[1] == 0x00
            and raw_data[2] == 0xFF
        ):
            start_idx = 3

        if start_idx + 2 <= len(raw_data):
            start_idx += 2

        sprite_content = raw_data[start_idx:]

        if self.transparency:
            return self._decode_1098_rgba(sprite_content)
        else:
            return self._decode_standard(sprite_content)

    def replace_sprite(self, sprite_id, image):
        
        if sprite_id < 1:
            return

        if image.size != (32, 32):
            image = image.resize((32, 32), Image.NEAREST)
        if image.mode != "RGBA":
            image = image.convert("RGBA")

        if self.transparency:
            encoded_bytes = self._encode_1098_rgba(image)
            if encoded_bytes is None:
                encoded_bytes = self._encode_standard(image)
        else:
            encoded_bytes = self._encode_standard(image)

        full_data = bytearray()
        size = len(encoded_bytes)
        full_data.extend(struct.pack("<H", size))
        full_data.extend(encoded_bytes)

        if sprite_id > self.sprite_count:
            for i in range(self.sprite_count + 1, sprite_id):
                self.sprites_data[i] = b""
            self.sprite_count = sprite_id

        self.sprites_data[sprite_id] = bytes(full_data)
        self.modified = True

    def _decode_standard(self, data):
        
        try:
            w, h = 32, 32
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            pixels = img.load()
            p = 0
            x = 0
            y = 0
            drawn = 0
            while p < len(data) and drawn < 1024:
                if p + 4 > len(data):
                    break
                trans, colored = struct.unpack_from("<HH", data, p)
                p += 4
                drawn += trans
                current = y * w + x + trans
                y, x = divmod(current, w)
                if p + colored * 3 > len(data):
                    break
                for _ in range(colored):
                    if y >= h:
                        break
                    pixels[x, y] = (data[p], data[p + 1], data[p + 2], 255)
                    p += 3
                    x += 1
                    drawn += 1
                    if x >= w:
                        x = 0
                        y += 1
            return img
        except:
            return None

    def _encode_standard(self, image):
        
        pixels = image.load()
        width, height = image.size

        output = bytearray()

        transparent_count = 0
        colored_pixels = []

        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]

                is_transparent = a < 10

                if is_transparent:
                    if colored_pixels:
                        output.extend(
                            struct.pack("<HH", transparent_count, len(colored_pixels))
                        )
                        for cr, cg, cb in colored_pixels:
                            output.extend(bytes([cr, cg, cb]))

                        transparent_count = 0
                        colored_pixels = []

                    transparent_count += 1
                else:
                    colored_pixels.append((r, g, b))

        if colored_pixels or transparent_count > 0:
            output.extend(struct.pack("<HH", transparent_count, len(colored_pixels)))
            for cr, cg, cb in colored_pixels:
                output.extend(bytes([cr, cg, cb]))

        return output

    def _decode_1098_rgba(self, data):

        try:
            w, h = 32, 32
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            pixels = img.load()

            x = 0
            y = 0
            p = 0
            total_pixels = w * h
            drawn = 0

            while p + 4 <= len(data) and drawn < total_pixels:
                transparent, colored = struct.unpack_from("<HH", data, p)
                p += 4

                drawn += transparent
                for _ in range(transparent):
                    x += 1
                    if x >= w:
                        x = 0
                        y += 1
                        if y >= h:
                            break

                if p + colored * 4 > len(data):
                    break

                for _ in range(colored):
                    if y >= h:
                        break

                    r = data[p]
                    g = data[p + 1]
                    b = data[p + 2]
                    a = data[p + 3]
                    p += 4

                    if a == 0 and (r != 0 or g != 0 or b != 0):
                        a = 255

                    pixels[x, y] = (r, g, b, a)

                    x += 1
                    drawn += 1
                    if x >= w:
                        x = 0
                        y += 1
                        if y >= h:
                            break

            return img

        except Exception as e:
            print("DEBUG: error in _decode_1098_rgba:", e)
            return None

    def _encode_1098_rgba(self, image):

        pixels = image.load()
        width, height = image.size

        output = bytearray()

        transparent_count = 0
        colored_pixels = []

        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]

                is_transparent = a == 0

                if is_transparent:
                    if colored_pixels:
                        output.extend(
                            struct.pack("<HH", transparent_count, len(colored_pixels))
                        )
                        for cr, cg, cb, ca in colored_pixels:
                            output.extend(bytes([cr, cg, cb, ca]))

                        transparent_count = 0
                        colored_pixels = []

                    transparent_count += 1
                else:
                    colored_pixels.append((r, g, b, a))

        if colored_pixels or transparent_count > 0:
            output.extend(struct.pack("<HH", transparent_count, len(colored_pixels)))
            for cr, cg, cb, ca in colored_pixels:
                output.extend(bytes([cr, cg, cb, ca]))

        return output


def pil_to_qpixmap(pil_image):

    if pil_image is None:
        return QPixmap()

    if pil_image.mode == "RGBA":
        qimage = QImage(
            pil_image.tobytes("raw", "RGBA"),
            pil_image.size[0],
            pil_image.size[1],
            QImage.Format.Format_RGBA8888,
        )
    elif pil_image.mode == "RGB":
        qimage = QImage(
            pil_image.tobytes("raw", "RGB"),
            pil_image.size[0],
            pil_image.size[1],
            QImage.Format.Format_RGB888,
        )
    else:
        qimage = QImage(
            pil_image.tobytes("raw", pil_image.mode),
            pil_image.size[0],
            pil_image.size[1],
            QImage.Format.Format_RGB888,
        )

    return QPixmap.fromImage(qimage)


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, hSpacing=-1, vSpacing=-1):
        super(FlowLayout, self).__init__(parent)
        self._hSpace = hSpacing
        self._vSpace = vSpacing
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def horizontalSpacing(self):
        if self._hSpace >= 0:
            return self._hSpace
        else:
            return self.smartSpacing(QStyle.PixelMetric.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self):
        if self._vSpace >= 0:
            return self._vSpace
        else:
            return self.smartSpacing(QStyle.PixelMetric.PM_LayoutVerticalSpacing)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0
        spacingX = self.horizontalSpacing()
        spacingY = self.verticalSpacing()

        for item in self._items:
            if not item.isEmpty():  # Use isEmpty instead of isHidden/isVisible logic for QLayoutItems
                wid = item.widget()
            else:
                 continue
            
            nextX = x + item.sizeHint().width() + spacingX
            if nextX - spacingX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spacingY
                nextX = x + item.sizeHint().width() + spacingX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()

    def smartSpacing(self, pm):
        parent = self.parent()
        if not parent:
            return -1
        elif parent.isWidgetType():
            return parent.style().pixelMetric(pm, None, parent)
        else:
            return parent.spacing()


class ScrollableFrame(QWidget):


    def __init__(self, parent=None, label_text="", layout_cls=QVBoxLayout):
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
        self.scroll_layout = layout_cls(self.scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(2)
        self.scroll.setWidget(self.scroll_widget)
        self.layout.addWidget(self.scroll)


class ClickableLabel(QLabel):


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

        if (
            event.pos() - self.drag_start_position
        ).manhattanLength() < QApplication.startDragDistance():
            return

        drag = QDrag(self)
        mime_data = QMimeData()

        mime_data.setText(str(self.sprite_id))
        drag.setMimeData(mime_data)

        if self.pixmap():
            drag.setPixmap(
                self.pixmap().scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio)
            )
            drag.setHotSpot(QPoint(16, 16))

        drag.exec(Qt.DropAction.CopyAction)


class DroppablePreviewLabel(ClickableLabel):
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




class OutfitDialog(QDialog):
    def __init__(self, parent_tab):
        super().__init__(parent_tab)
        self.setWindowTitle("Outfit Filters")
        self.setFixedWidth(250)
        self.setStyleSheet("""
            QDialog {
                background: #1a1a2e;
                border: 2px solid #5b9bd5;
                border-radius: 8px;
            }
            QCheckBox {
                color: #e0e0e0; font-size: 14px; padding: 5px; spacing: 10px;
            }
            QCheckBox::indicator {
                width: 18px; height: 18px;
                border: 2px solid #555555;
                border-radius: 4px;
                background: #2a2a3a;
            }
            QCheckBox::indicator:checked {
                background: #4a90e2;
                border: 2px solid #4a90e2;
            }
            QPushButton {
                background: #4a90e2; color: white; border-radius: 4px; padding: 6px; font-weight: bold;
            }
            QPushButton:hover { background: #5b9bd5; }
        """)
        
        layout = QVBoxLayout(self)
        
        # Addon 1
        self.chk_addon1 = QCheckBox("Addon 1")
        self.chk_addon1.setChecked(parent_tab.outfit_addon1_enabled)
        self.chk_addon1.toggled.connect(parent_tab.on_toggle_addon1)
        layout.addWidget(self.chk_addon1)
        
        # Addon 2
        self.chk_addon2 = QCheckBox("Addon 2")
        self.chk_addon2.setChecked(parent_tab.outfit_addon2_enabled)
        self.chk_addon2.toggled.connect(parent_tab.on_toggle_addon2)
        layout.addWidget(self.chk_addon2)
        
        # Mount
        self.chk_mount = QCheckBox("Mount")
        self.chk_mount.setChecked(parent_tab.outfit_mount_enabled)
        self.chk_mount.toggled.connect(parent_tab.on_toggle_mount)
        layout.addWidget(self.chk_mount)
        
        # Mask
        self.chk_mask = QCheckBox("Mask / Color")
        self.chk_mask.setChecked(parent_tab.outfit_mask_enabled)
        self.chk_mask.toggled.connect(parent_tab.on_toggle_mask)
        layout.addWidget(self.chk_mask)
        
        # Walk
        self.chk_walk = QCheckBox("Walk Animation")
        self.chk_walk.setChecked(parent_tab.outfit_walk_enabled)
        self.chk_walk.toggled.connect(parent_tab.on_toggle_walk)
        layout.addWidget(self.chk_walk)

        layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)


class FlagsDialog(QDialog):
    def __init__(self, checkboxes_dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Flags")
        self.setFixedWidth(500)
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1a2e, stop:1 #16161f);
                border: 2px solid #4a90e2;
                border-radius: 10px;
            }
            QLabel { color: #e0e0e0; font-weight: bold; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Grid area for flags
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        grid = QGridLayout(content)
        grid.setSpacing(10)
        
        INTERNAL_FLAGS = ["MarketItem"]
        all_attr_names = sorted(REVERSE_METADATA_FLAGS.keys())
        visible_attr_names = [n for n in all_attr_names if n not in INTERNAL_FLAGS]

        cols = 2
        for i, attr_name in enumerate(visible_attr_names):
            row = i // cols
            col = i % cols
            
            container = QWidget()
            cont_layout = QHBoxLayout(container)
            cont_layout.setContentsMargins(0,0,0,0)
            cont_layout.setSpacing(10)
            
            # Create ToggleSwitch if not already in dict (it starts empty)
            if attr_name not in checkboxes_dict:
                 checkboxes_dict[attr_name] = ToggleSwitch()

            toggle = checkboxes_dict[attr_name]
            
            label = QLabel(attr_name)
            label.setStyleSheet("color: #cccccc; font-size: 11px;")
            
            cont_layout.addWidget(toggle)
            cont_layout.addWidget(label)
            cont_layout.addStretch()
            
            grid.addWidget(container, row, col)

        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        # Close Button
        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            background: #4a90e2; color: white; border: none; padding: 8px; border-radius: 4px; font-weight: bold;
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

class DatSprTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.editor = None  #  DatEditor
        self.spr = None  #  SprEditor
        self._kept_image = None
        self.current_preview_sprite_list = []
        self.current_preview_index = 0
        self.selected_sprite_id = None
        self.is_animating = False

        self.current_framegroup_index = 0  
        self.outfit_addon1_enabled = False
        self.outfit_addon2_enabled = False
        self.outfit_mount_enabled = False
        self.outfit_mask_enabled = False
        self.outfit_walk_enabled = False
        self.current_direction_key = "S"


        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self.update_animation_step)

        self.visible_sprite_widgets = {}
        self.current_ids = []
        self.checkboxes = {}
        self.numeric_entries = {}
        self.numeric_previews = {}
        self.dir_buttons = {}
        self.sprites_per_page = 1000
        self.sprite_page = 0
        self.sprite_thumbs = {}
        
        self.flags_dialog = None # Initialize to None
        
        self.build_ui()
        self.settings = QSettings("TibiaItemManager", "DatSprEditor")
        self.load_settings()

    def open_outfit_dialog(self):
        # We assume self.outfit_dialog can be reused or created new
        # Since state is in parent (self), we can create new or store it.
        # Let's create new to keep it simple and stateless regarding the window itself.
        dialog = OutfitDialog(self)
        dialog.exec()

    def open_flags_dialog(self):
        if not self.flags_dialog:
             self.flags_dialog = FlagsDialog(self.checkboxes, self)
        self.flags_dialog.show()
        self.flags_dialog.raise_()
        self.flags_dialog.activateWindow()

    def show_options_help(self):
        msg = (
            "<b>Extended:</b> Check this if your client is version 9.60 or higher (uses uint16 IDs).<br><br>"
            "<b>Transparency:</b> Check this if your client is version 10.50 or higher (supports transparency in sprites).<br><br>"
            "<i>If loading fails, try changing these options.</i>"
        )
        QMessageBox.information(self, "Loading Options Help", msg)

    def load_settings(self):
        saved_path = self.settings.value("last_spr_path", "")
        if saved_path:
            self.file_input.setText(saved_path)
            # User prefers to click Load manually
            # QTimer.singleShot(100, lambda: self.load_dat_file_from_path(saved_path))

    def save_settings(self, path):
        self.settings.setValue("last_spr_path", path)

    def build_ui(self):
        # Main Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 1. Top Toolbar ---
        top_toolbar = QFrame()
        top_toolbar.setObjectName("topToolbar")
        top_toolbar.setFixedHeight(50)
        toolbar_layout = QHBoxLayout(top_toolbar)
        toolbar_layout.setContentsMargins(15, 5, 15, 5)
        toolbar_layout.setSpacing(5) # Reduced spacing

        # Title/Icon
        title_lbl = QLabel("📁 File Manager")
        title_lbl.setStyleSheet("color: #5b9bd5; font-weight: bold; text-transform: uppercase; margin-right: 0px;")
        toolbar_layout.addWidget(title_lbl)

        # File Input
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Path to Tibia.dat/.spr")
        self.file_input.setReadOnly(True)
        self.file_input.setMaximumWidth(350)
        toolbar_layout.addWidget(self.file_input)

        # Config Group (Extended, Transparency, Help)
        config_frame = QFrame()
        config_layout = QHBoxLayout(config_frame)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(2) # Very tight spacing

        self.chk_extended = QCheckBox("Extended")
        self.chk_extended.setToolTip("Check this if your client version is 9.60+ (uses u16 ids).")
        self.chk_extended.setChecked(False)
        self.chk_extended.setStyleSheet("color: white; margin-right: 5px;")
        config_layout.addWidget(self.chk_extended)

        self.chk_transparency = QCheckBox("Transparency")
        self.chk_transparency.setToolTip("Check this if your SPR has transparency support (usually 10.50+).")
        self.chk_transparency.setChecked(False)
        self.chk_transparency.setStyleSheet("color: white; margin-right: 5px;")
        config_layout.addWidget(self.chk_transparency)

        # Help Button
        help_btn = QPushButton("?")
        help_btn.setFixedSize(25, 25)
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.setStyleSheet("""
            QPushButton {
                background: none;
                border: none;
                color: #4a90e2;
                font-weight: bold;
                font-size: 18px;
                padding: 0px;
                margin-left: 5px;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        help_btn.setToolTip("Click for help on options")
        help_btn.clicked.connect(self.show_options_help)
        config_layout.addWidget(help_btn)

        toolbar_layout.addWidget(config_frame)

        # Actions Button Group
        btns_frame = QFrame()
        btns_layout = QHBoxLayout(btns_frame)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.setSpacing(5)

        # Browse Button
        browse_btn = QPushButton("📂 Browse")
        browse_btn.setFixedSize(90, 30)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self.browse_file)
        btns_layout.addWidget(browse_btn)

        # Load Button
        self.load_btn = QPushButton("⚡ Load")
        self.load_btn.setObjectName("primaryBtn")
        self.load_btn.setFixedSize(80, 30)
        self.load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.load_btn.clicked.connect(self.on_load_clicked)
        btns_layout.addWidget(self.load_btn)

        # Save Button
        self.save_button = QPushButton("💾 Save SPR")
        self.save_button.setObjectName("successBtn")
        self.save_button.setFixedSize(100, 30)
        self.save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_button.clicked.connect(self.save_dat_file)
        btns_layout.addWidget(self.save_button)

        toolbar_layout.addWidget(btns_frame)

        # Push everything to the left
        toolbar_layout.addStretch()

        main_layout.addWidget(top_toolbar)

        # --- 2. Main Content (Splitter) ---
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(1) # Thin divider
        self.main_splitter.setChildrenCollapsible(False)

        # --- LEFT SIDEBAR (List ID) ---
        left_widget = QWidget()
        left_widget.setStyleSheet("background-color: rgba(20, 20, 30, 0.7); border-right: 1px solid rgba(74, 144, 226, 0.2);")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Sidebar Header
        sidebar_header = QWidget()
        sidebar_header.setStyleSheet("background: rgba(30, 30, 46, 0.6); border-bottom: 1px solid rgba(74, 144, 226, 0.2);")
        header_layout = QVBoxLayout(sidebar_header)
        header_layout.setContentsMargins(10, 10, 10, 10)
        
        lbl_list_id = QLabel("List ID")
        lbl_list_id.setStyleSheet("color: #5b9bd5; font-size: 12px; font-weight: bold; text-transform: uppercase;")
        header_layout.addWidget(lbl_list_id)

        # Search Box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search ID...")
        self.search_input.textChanged.connect(self.filter_id_list)
        header_layout.addWidget(self.search_input)
        left_layout.addWidget(sidebar_header)

        # ID List Area
        self.ids_list_frame = ScrollableFrame(self, "", layout_cls=FlowLayout)
        self.ids_list_frame.layout.setContentsMargins(5,5,5,5)
        
        self.category_combo = QComboBox()
        self.category_combo.addItems(["Item", "Outfit", "Effect", "Missile"])
        self.category_combo.currentTextChanged.connect(self.on_category_change)
        header_layout.insertWidget(1, self.category_combo)

        left_layout.addWidget(self.ids_list_frame)
        self.main_splitter.addWidget(left_widget)

        # --- CENTER PANEL (Flags & Properties) ---
        center_scroll = QScrollArea()
        center_scroll.setWidgetResizable(True)
        center_scroll.setStyleSheet("background: transparent; border: none;")
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(15, 15, 15, 15)
        center_layout.setSpacing(15)

        # Actions Toolbar (ID & Tools)
        actions_frame = QFrame()
        actions_frame.setStyleSheet("background: rgba(30, 30, 46, 0.5); border-radius: 6px;")
        actions_layout = QHBoxLayout(actions_frame)
        actions_layout.setContentsMargins(10, 5, 10, 5)
        actions_layout.setSpacing(10)

        # ID Input
        # ID Input
        lbl_id = QLabel("Current ID:")
        lbl_id.setStyleSheet("color: white; font-weight: bold; margin-right: 5px;")
        actions_layout.addWidget(lbl_id)

        self.id_entry = QLineEdit()
        self.id_entry.setPlaceholderText("ID")
        self.id_entry.setFixedWidth(60)
        self.id_entry.setStyleSheet("background-color: #3e3e50; border: 1px solid #5b9bd5; border-radius: 4px; color: white; padding: 2px; font-weight: bold;")
        self.id_entry.returnPressed.connect(self.load_ids_from_entry)
        actions_layout.addWidget(self.id_entry)

        self.load_ids_button = QPushButton("GO")
        self.load_ids_button.setFixedWidth(50)
        self.load_ids_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.load_ids_button.setStyleSheet("background-color: #4a90e2; color: white; border-radius: 4px; font-weight: bold; font-size: 12px;")
        self.load_ids_button.clicked.connect(self.load_ids_from_entry)
        actions_layout.addWidget(self.load_ids_button)

        actions_layout.addStretch()

        # Tools
        self.insert_id_button = QPushButton("+ NEW")
        self.insert_id_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.insert_id_button.setStyleSheet("font-weight: bold; color: white;")
        self.insert_id_button.clicked.connect(self.insert_new_id)
        actions_layout.addWidget(self.insert_id_button)

        self.delete_id_button = QPushButton("- DEL")
        self.delete_id_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_id_button.setStyleSheet("font-weight: bold; color: white;")
        self.delete_id_button.clicked.connect(self.delete_current_id)
        actions_layout.addWidget(self.delete_id_button)

        self.delete_id_button.clicked.connect(self.delete_current_id)
        actions_layout.addWidget(self.delete_id_button)

        # Manage Flags Button (Compact UI)
        self.flags_btn = QPushButton("🚩 Flags")
        self.flags_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.flags_btn.setStyleSheet("font-weight: bold; color: #e0e0e0; border: 1px solid #5b9bd5; border-radius: 4px;")
        self.flags_btn.clicked.connect(self.open_flags_dialog)
        actions_layout.addWidget(self.flags_btn)

        # Apply
        self.apply_button = QPushButton("APPLY CHANGES")
        self.apply_button.setObjectName("primaryBtn")
        self.apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_button.setStyleSheet("font-weight: bold; font-size: 11px;")
        self.apply_button.clicked.connect(self.apply_changes)
        actions_layout.addWidget(self.apply_button)

        center_layout.addWidget(actions_frame)



        # Outfit Options were moved to Right Panel (Preview)

        # Pre-initialize checkboxes for background logic (Compact Mode)
        # We don't add them to the main layout anymore, they live in FlagsDialog
        INTERNAL_FLAGS = ["MarketItem"]
        all_attr_names = sorted(REVERSE_METADATA_FLAGS.keys())
        visible_attr_names = [n for n in all_attr_names if n not in INTERNAL_FLAGS]

        for attr_name in visible_attr_names:
            if attr_name not in self.checkboxes:
                 self.checkboxes[attr_name] = ToggleSwitch()
                 # We don't addWidget here. They are used in FlagsDialog.

        # Properties Section
        props_group = QGroupBox("⚙️ Properties")
        props_layout = QGridLayout(props_group)
        props_layout.setSpacing(10)
        
        attrs_config = [
            ("Light Level (0-10)", "HasLight_Level", False, None),
            ("Light Color (0-215)", "HasLight_Color", True, "color"),
            ("Minimap (0-215)", "ShowOnMinimap", True, "color"),
            ("Elevation (0-32)", "HasElevation", False, None),
            ("Ground Speed (0-1000)", "Ground", False, None),
            ("Offset X", "HasOffset_X", False, None),
            ("Offset Y", "HasOffset_Y", False, None),
            ("Width", "Width", False, None),
            ("Height", "Height", False, None),
            ("Crop Size", "CropSize", False, None),
            ("Layers", "Layers", False, None),
            ("Pattern X", "PatternX", False, None),
            ("Pattern Y", "PatternY", False, None),
            ("Pattern Z", "PatternZ", False, None),
            ("Anim Frames", "Animation", False, None),
        ]

        p_row = 0
        for label_text, attr_name, has_preview, preview_type in attrs_config:
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #a0a0a0; font-size: 11px;")
            props_layout.addWidget(lbl, p_row, 0)
            
            # Slider
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100) # Placeholder range
            props_layout.addWidget(slider, p_row, 1)

            # Input
            entry = QLineEdit()
            entry.setFixedWidth(60)
            entry.setText("0")
            props_layout.addWidget(entry, p_row, 2)
            self.numeric_entries[attr_name] = entry

            if has_preview and preview_type == "color":
                 preview = QLabel()
                 preview.setFixedSize(16, 16)
                 preview.setStyleSheet("background-color: black; border: 1px solid #4a90e2; border-radius: 3px;")
                 props_layout.addWidget(preview, p_row, 3)
                 self.numeric_previews[attr_name] = preview

            p_row += 1

        center_layout.addWidget(props_group)
        center_scroll.setWidget(center_widget)
        self.main_splitter.addWidget(center_scroll)

        # --- RIGHT PANEL (Preview & Sprites) ---
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: rgba(20, 20, 30, 0.7); border-left: 1px solid rgba(74, 144, 226, 0.2);")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(15)

        # Preview Container
        preview_container = QGroupBox("🖼️ Preview")
        prev_layout = QVBoxLayout(preview_container)
        
        self.image_label = DroppablePreviewLabel()
        self.image_label.setMinimumSize(250, 300)
        self.image_label.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1a1a2a, stop:1 #2a2a3a); border: 1px solid rgba(74, 144, 226, 0.3); border-radius: 6px;")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setText("Drop Sprite Here")
        self.image_label.doubleClicked.connect(self.on_preview_click)
        self.image_label.spriteDropped.connect(self.handle_preview_drop)
        prev_layout.addWidget(self.image_label)

        # 1. Direction Controls (Centered & Compact)
        dir_container = QWidget()
        dir_layout = QHBoxLayout(dir_container)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.addStretch()
        
        dir_grid = QGridLayout()
        dir_grid.setSpacing(5)
        # Grid: Row, Col, DirectionKey, ArrowSymbol
        grid_map = [
            (0, 1, "N", "↑"), (1, 0, "W", "←"), (1, 2, "E", "→"), (2, 1, "S", "↓"),
            (0, 0, "NW", "↖"), (2, 0, "SW", "↙"), (0, 2, "NE", "↗"), (2, 2, "SE", "↘")
        ]
        
        for r, c, key, label in grid_map:
            btn = QPushButton(label)
            btn.setFixedSize(32, 32) # Slightly smaller for compact look
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # Dark square style
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3a;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    color: #d0d0d0;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 0px; 
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #777777;
                }
                QPushButton:pressed {
                    background-color: #2a2a2a;
                    border-color: #4a90e2;
                }
            """)
            btn.clicked.connect(lambda _, k=key: self.change_direction(k))
            dir_grid.addWidget(btn, r, c)
            self.dir_buttons[key] = btn
            
        center_btn = QPushButton("●")
        center_btn.setFixedSize(32, 32)
        center_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3a3a3a;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    color: #5b9bd5;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                }
        """)
        dir_grid.addWidget(center_btn, 1, 1) # Center button
        
        dir_layout.addLayout(dir_grid)
        dir_layout.addStretch()
        prev_layout.addWidget(dir_container)
        
        
        # 2. Anim Controls (Centered Row) + Outfit Button
        controls_container = QWidget()
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 5, 0, 5)
        controls_layout.setSpacing(5)

        # Anim Row
        anim_row = QWidget()
        anim_layout = QHBoxLayout(anim_row)
        anim_layout.setContentsMargins(0,0,0,0)
        anim_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Prev Button
        self.prev_btn = QPushButton("<") 
        self.prev_btn.setFixedSize(30, 30)
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.setToolTip("Previous Frame")
        self.prev_btn.setStyleSheet("font-weight: bold; font-size: 14px; background-color: #3a3a3a; color: white; border: 1px solid #555; padding: 0px;")
        self.prev_btn.clicked.connect(lambda: self.change_preview_index(-1))
        anim_layout.addWidget(self.prev_btn)
        
        # Anim Button
        self.anim_btn = QPushButton("PLAY")
        self.anim_btn.setToolTip("Play Animation")
        self.anim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.anim_btn.setFixedSize(110, 30)
        self.anim_btn.setStyleSheet("font-size: 11px; font-weight: bold; background-color: #4a90e2; color: white; border-radius: 4px;")
        self.anim_btn.clicked.connect(self.toggle_animation)
        anim_layout.addWidget(self.anim_btn)

        # Next Button
        self.next_btn = QPushButton(">") 
        self.next_btn.setFixedSize(30, 30)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.setToolTip("Next Frame")
        self.next_btn.setStyleSheet("font-weight: bold; font-size: 14px; background-color: #3a3a3a; color: white; border: 1px solid #555; padding: 0px;")
        self.next_btn.clicked.connect(lambda: self.change_preview_index(1))
        anim_layout.addWidget(self.next_btn)
        
        controls_layout.addWidget(anim_row)

        # Outfit Button (Replaces Checkboxes)
        self.outfit_btn = QPushButton("⚙️ Outfit Options")
        self.outfit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.outfit_btn.setFixedHeight(28)
        self.outfit_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 30, 46, 0.6);
                border: 1px solid #4a90e2;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: rgba(74, 144, 226, 0.2);
            }
        """)
        self.outfit_btn.clicked.connect(self.open_outfit_dialog)
        controls_layout.addWidget(self.outfit_btn)

        # Preview Info Labels (Restored)
        self.prev_index_label = QLabel("Frame: 0")
        self.prev_index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prev_index_label.setStyleSheet("color: #a0a0a0; font-size: 10px;")
        controls_layout.addWidget(self.prev_index_label)

        self.preview_info = QLabel("")
        self.preview_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_info.setStyleSheet("color: #808080; font-size: 10px;")
        controls_layout.addWidget(self.preview_info)

        prev_layout.addWidget(controls_container)

        right_layout.addWidget(preview_container)

        # Right Sidebar (Sprites)
        # We need to add it to the main splitter
        self.main_splitter.addWidget(right_widget)

        # --- RIGHT SIDEBAR (Sprite List) ---
        sprites_widget = QWidget()
        sprites_widget.setStyleSheet("background-color: rgba(20, 20, 30, 0.7); border-left: 1px solid rgba(74, 144, 226, 0.2);")
        sprites_layout = QVBoxLayout(sprites_widget)
        sprites_layout.setContentsMargins(0, 0, 0, 0)
        
        sprite_header = QWidget()
        sprite_header.setStyleSheet("background: rgba(30, 30, 46, 0.6); border-bottom: 1px solid rgba(74, 144, 226, 0.2);")
        sph_layout = QVBoxLayout(sprite_header)
        sph_layout.setContentsMargins(10, 10, 10, 10)
        lbl_sprites = QLabel("Sprites")
        lbl_sprites.setStyleSheet("color: #5b9bd5; font-size: 12px; font-weight: bold; text-transform: uppercase;")
        sph_layout.addWidget(lbl_sprites)
        
        # Go To Sprite ID Input
        sprite_goto_frame = QFrame()
        sprite_goto_layout = QHBoxLayout(sprite_goto_frame)
        sprite_goto_layout.setContentsMargins(0, 5, 0, 0)
        sprite_goto_layout.setSpacing(5)
        
        self.sprite_goto_entry = QLineEdit()
        self.sprite_goto_entry.setPlaceholderText("Sprite ID...")
        self.sprite_goto_entry.setStyleSheet("background-color: #3e3e50; border: 1px solid #5b9bd5; border-radius: 4px; color: white; padding: 4px;")
        self.sprite_goto_entry.returnPressed.connect(self.goto_sprite_id)
        sprite_goto_layout.addWidget(self.sprite_goto_entry)
        
        sprite_go_btn = QPushButton("GO")
        sprite_go_btn.setFixedSize(50, 28)
        sprite_go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sprite_go_btn.setStyleSheet("background-color: #4a90e2; color: white; border-radius: 4px; font-weight: bold;")
        sprite_go_btn.clicked.connect(self.goto_sprite_id)
        sprite_goto_layout.addWidget(sprite_go_btn)
        
        sph_layout.addWidget(sprite_goto_frame)
        sprites_layout.addWidget(sprite_header)

        self.sprite_list_frame = ScrollableFrame(self, "", layout_cls=QVBoxLayout)
        self.sprite_list_frame.layout.setContentsMargins(5,5,5,5)
        sprites_layout.addWidget(self.sprite_list_frame)

        self.main_splitter.addWidget(sprites_widget)

        # Set Splitter Ratios: Left(1), Center(2), RightPanel(2), RightSidebar(1)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 4)
        self.main_splitter.setStretchFactor(2, 3)
        self.main_splitter.setStretchFactor(3, 1)

        main_layout.addWidget(self.main_splitter)

        # --- 3. Status Bar ---
        status_bar = QFrame()
        status_bar.setObjectName("statusBar")
        status_bar.setFixedHeight(30)
        status_bar.setStyleSheet("background: rgba(20, 20, 30, 0.9); border-top: 1px solid rgba(74, 144, 226, 0.2);")
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(15, 0, 15, 0)
        
        # Pulse Indicator
        pulse_indicator = QLabel()
        pulse_indicator.setFixedSize(8, 8)
        pulse_indicator.setStyleSheet("background: #4a90e2; border-radius: 4px;")
        status_layout.addWidget(pulse_indicator)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        self.mem_label = QLabel("Memory: 0 MB")
        self.mem_label.setStyleSheet("color: #888; font-size: 11px;")
        status_layout.addWidget(self.mem_label)

        main_layout.addWidget(status_bar)

        self.disable_editing()
        self.build_loading_overlay()

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
        
  
    def open_shader(self):
        self.shader_win = ShaderEditor(
        )
        self.shader_win.show()       
        
    def open_particle(self):
        self.particle_win = ParticleGenerator(
        )
        self.particle_win.run()   
        
    def open_monster_generator(self):
        self.monster_win = MonsterGeneratorWindow(
        )
        self.monster_win.show()
        
    def open_spell_maker(self):
        self.spell_win = SpellMakerWindow(
        )
        self.spell_win.show()        
    
    def open_looktype_generator(self):
        if not self.spr or not self.editor:
            QMessageBox.warning(
                self, "Warning", "Upload the DAT and SPR files first.."
            )
            return
       
        self.looktype_win = LookTypeGeneratorWindow(
            spr_editor=self.spr,
            dat_editor=self.editor,
            parent=self
        )
        self.looktype_win.show()        

    def on_toggle_addon1(self, checked):
        print("DEBUG: Executing on_toggle_addon1 fixed") 
        self.outfit_addon1_enabled = checked
        if checked:
            self.outfit_addon2_enabled = False
        else:
            self.current_framegroup_index = 0 
        
        if self.get_current_category_key() == "outfits":
            self.prepare_preview_for_current_ids("outfits")

    def on_toggle_addon2(self, checked):
        print("DEBUG: Executing on_toggle_addon2 fixed")
        self.outfit_addon2_enabled = checked
        if checked:
            self.outfit_addon1_enabled = False
        else:
            self.current_framegroup_index = 0 
        
        if self.get_current_category_key() == "outfits":
            self.prepare_preview_for_current_ids("outfits")

    def on_toggle_mount(self, checked):

        self.outfit_mount_enabled = checked          
        if checked:
            self.outfit_mount_enabled = checked                
             
        else:
            self.current_framegroup_index = 0 
        
        if self.get_current_category_key() == "outfits":
            self.prepare_preview_for_current_ids("outfits")

    def on_toggle_mask(self, checked):
        self.outfit_mask_enabled = checked
        if self.get_current_category_key() == "outfits":
            self.prepare_preview_for_current_ids("outfits")


    def on_toggle_walk(self, checked):
        """Alterna entre Idle (0) e Walk (1)"""
        self.outfit_walk_enabled = checked
        
        if checked:
            self.current_framegroup_index = 1                    
        else:
            self.current_framegroup_index = 0  
        
        if self.get_current_category_key() == "outfits":
            self.prepare_preview_for_current_ids("outfits")



    def change_direction(self, dir_key):
        self.current_direction_key = dir_key

        default_style = """
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555555;
                border-radius: 4px;
                color: #d0d0d0;
                font-size: 14px;
                font-weight: bold;
                padding: 0px; 
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #777777;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
                border-color: #4a90e2;
            }
        """
        active_style = """
            QPushButton {
                background-color: #007acc;
                border: 1px solid #34ce57;
                border-radius: 4px;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
            }
        """

        # Atualiza visual dos botões
        for key, btn in self.dir_buttons.items():
            if key == dir_key:
                btn.setStyleSheet(active_style)
            else:
                btn.setStyleSheet(default_style)

        # Reseta animação e atualiza preview
        self.current_preview_index = 0
        self.show_preview_at_index(0)

    def build_outfit_texture_bytes(
        self, width, height, frames, sprite_ids, layer_type=0
    ):

        out = bytearray()

        out.append(1)

        # Byte 2: Frame Group Type (0 = Idle/Normal)
        out.append(layer_type)

   
        out.extend(struct.pack("<BB", width, height))

        if width > 1 or height > 1:
            out.append(32)  # CropSize

        layers = 1
        px = 1
        py = 1
        pz = 1

        out.extend(struct.pack("<BBBBB", layers, px, py, pz, frames))

        # Improved Animations
        if frames > 1:
            out.append(0)  # Async/Mode (0 = Sync)
            out.extend(struct.pack("<I", 0))  
            out.append(0)  
            for _ in range(frames):

                out.extend(struct.pack("<I", 75))

        # Sprite IDs
        use_extended = self.editor.extended
        fmt = "<I" if use_extended else "<H"

        for sid in sprite_ids:
            out.extend(struct.pack(fmt, sid))

        return bytes(out)

    def handle_preview_drop(self, new_sprite_id, drop_pos):

        if not self.current_ids or not self.editor:
            return

        cat_map = {
            "Item": "items",
            "Outfit": "outfits",
            "Effect": "effects",
            "Missile": "missiles",
        }
        current_cat_key = cat_map.get(self.category_combo.currentText(), "items")
        target_id = self.current_ids[0]

        if target_id not in self.editor.things[current_cat_key]:
            return

        item_data = self.editor.things[current_cat_key][target_id]
        props = item_data.get("props", {})

        width = props.get("Width", 1)
        height = props.get("Height", 1)
        width = 1 if width == 0 else width
        height = 1 if height == 0 else height

        pixmap = self.image_label.pixmap()
        if not pixmap:
            return
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

        if col >= width:
            col = width - 1
        if row >= height:
            row = height - 1

        inverted_row = (height - 1) - row
        inverted_col = (width - 1) - col

        target_row = inverted_row
        target_col = inverted_col

        sprites_per_frame = width * height * props.get("Layers", 1)
        base_frame_index = self.current_preview_index * sprites_per_frame


        local_index = (target_row * width) + target_col
   

        final_index = base_frame_index + local_index

        current_sprites = self.current_preview_sprite_list
        if not current_sprites:
            current_sprites = [0] * (final_index + 1)

        if final_index >= len(current_sprites):
            current_sprites.extend([0] * (final_index - len(current_sprites) + 1))

        if 0 <= final_index < len(current_sprites):
            current_sprites[final_index] = new_sprite_id


            original_bytes = item_data.get("texture_bytes", b"")
            new_texture_bytes = self.rebuild_texture_bytes(
                original_bytes, current_sprites
            )
            self.editor.things[current_cat_key][target_id]["texture_bytes"] = (
                new_texture_bytes
            )

            self.prepare_preview_for_current_ids(current_cat_key)
            self.show_preview_at_index(self.current_preview_index)

    def open_slicer(self):
        if not self.spr:
            QMessageBox.warning(self, "Aviso", "Carregue um arquivo .spr primeiro.")
            return

        self.slicer_win = SliceWindow()

        self.slicer_win.sprites_imported.connect(self.handle_slicer_import)
        self.slicer_win.show()

    def open_optimizer(self):
        if not self.spr or not self.editor:
            QMessageBox.warning(
                self, "Aviso", "Carregue os arquivos DAT e SPR primeiro."
            )
            return


        self.opt_win = SpriteOptimizerWindow(self.spr, self.editor, self)
        self.opt_win.show()

    def handle_slicer_import(self, sprite_list):
        if not self.spr or not sprite_list:
            return

        count = 0
        try:
   
            last_id = self.spr.sprite_count

            for pil_img in sprite_list:
                new_id = last_id + 1

                self.spr.replace_sprite(new_id, pil_img)
                last_id = new_id
                count += 1

            self.refresh_sprite_list()
            self.status_label.setText(
                f"{count} sprites importadas do Slicer com sucesso."
            )
            self.status_label.setStyleSheet("color: #90ee90;")  # Light green


            self.sprite_page = (self.spr.sprite_count - 1) // self.sprites_per_page
            self.refresh_sprite_list()

        except Exception as e:
            QMessageBox.critical(
                self, "Erro na Importação", f"Falha ao importar sprites: {e}"
            )



    def animate_loop(self):
        if not self.is_animating or not self.current_preview_sprite_list:
            self.is_animating = False
            self.anim_btn.setText("▶")
            self.anim_btn.setStyleSheet("background-color: #444444;")
            return

        group_size = (
            self.current_item_width
            * self.current_item_height
            * self.current_item_layers
        )
        if group_size == 0:
            group_size = 1
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

    def build_texture_bytes(
        self, width, height, layers, px, py, pz, frames, sprite_ids
    ):
        out = bytearray()

        out.extend(struct.pack("<BB", width, height))

        if width > 1 or height > 1:
            out.append(32)

        out.extend(struct.pack("<BBBBB", layers, px, py, pz, frames))

        if frames > 1:
            out.append(0)  
            out.extend(struct.pack("<I", 0)) 
            out.append(0)  
            for _ in range(frames):
                out.extend(struct.pack("<I", 75))

        use_extended = self.editor.extended
        fmt = "<I" if use_extended else "<H"

        for sid in sprite_ids:
            out.extend(struct.pack(fmt, sid))

        return bytes(out)

    def get_current_category_key(self):
        cat_map = {
            "Item": "items",
            "Outfit": "outfits",
            "Effect": "effects",
            "Missile": "missiles",
        }
        return cat_map.get(self.category_combo.currentText(), "items")

    def rebuild_texture_bytes(self, original_bytes, new_sprite_ids):
        if not original_bytes:
            header = b"\x01\x01\x01\x01\x01\x01\x01"
        else:
            offset = 0
            width, height = struct.unpack_from("<BB", original_bytes, offset)
            offset += 2

            if width > 1 or height > 1:
                offset += 1

            layers, px, py, pz, frames = struct.unpack_from(
                "<BBBBB", original_bytes, offset
            )
            offset += 5

            anim_detail_size = 0
            if frames > 1:
                anim_detail_size = 1 + 4 + 1 + (frames * 8)

            offset += anim_detail_size

            header = original_bytes[:offset]

        ids_data = bytearray()

        is_extended = self.editor.extended
        fmt = "<I" if is_extended else "<H"

        for sid in new_sprite_ids:
            ids_data.extend(struct.pack(fmt, int(sid)))

        return header + ids_data

    def show_context_menu(self, event, item_id, context_type):
        self.right_click_target = {"id": item_id, "type": context_type}
        if isinstance(event, QContextMenuEvent):
            self.context_menu.exec(event.globalPos())
        elif hasattr(event, "globalPos"):
            self.context_menu.exec(event.globalPos())
        else:
            self.context_menu.exec(QPoint(event.x(), event.y()))

    def on_context_export(self):
        if not self.current_ids:
            return

        target_id = self.current_ids[0]
        cat_key = self.get_current_category_key()


        ob_type_map = {
            "items": "Item",
            "outfits": "Outfit",
            "effects": "Effect",
            "missiles": "Missile",
        }
        ob_type = ob_type_map.get(cat_key, "Item")

        thing = self.editor.things[cat_key].get(target_id)
        if not thing:
            QMessageBox.warning(self, "Erro", "Item não encontrado.")
            return

        file_path, filter_used = QFileDialog.getSaveFileName(
            self,
            f"Export {ob_type}",
            f"{target_id}",
            "Object Builder (*.obd);;Images (*.png)",
        )

        if not file_path:
            return

        texture_bytes = thing.get("texture_bytes", b"")
        sprite_ids = self.editor.extract_sprite_ids_from_texture_bytes(texture_bytes)

        images = []
        if not sprite_ids:

            print("Aviso: Nenhuma sprite encontrada nos dados do item.")
        else:
            for sid in sprite_ids:
                img = self.spr.get_sprite(sid)
                if img:
                    images.append(img)
                else:

                    images.append(Image.new("RGBA", (32, 32), (0, 0, 0, 0)))


        if filter_used == "Object Builder (*.obd)" or file_path.endswith(".obd"):
            try:

                ObdHandler.save_obd(file_path, thing["props"], images, ob_type)
                QMessageBox.information(
                    self, "Sucesso", f"Exportado {len(images)} sprites para OBD."
                )
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Falha ao salvar OBD: {e}")
        else:

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
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if target_type == "id_list":
            if not self.editor:
                return

            cat_map = {
                "Item": "items",
                "Outfit": "outfits",
                "Effect": "effects",
                "Missile": "missiles",
            }
            current_cat_key = cat_map.get(self.category_combo.currentText(), "items")

            if target_id in self.editor.things[current_cat_key]:
                minimal_texture = b"\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00"

                self.editor.things[current_cat_key][target_id] = {
                    "props": OrderedDict(),
                    "texture_bytes": minimal_texture,
                }

                self.refresh_id_list()
                self.load_single_id(target_id)
                self.status_label.setText(f"ID {target_id} cleared successfully.")
                self.status_label.setStyleSheet("color: green;")

        elif target_type == "sprite_list":
            QMessageBox.information(
                self,
                "Not Implemented",
                "Sprite clearing requires SPR write logic.\nImplement 'replace_sprite' first.",
            )

    def insert_new_id(self):
        if not self.editor:
            return

        cat_key = self.get_current_category_key()
        if not self.editor.things[cat_key]:
            max_id = 99
        else:
            max_id = max(self.editor.things[cat_key].keys())
            
        new_id = max_id + 1

        self.editor.things[cat_key][new_id] = {
            "props": OrderedDict(),
            "texture_bytes": b"\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00"
        }
        self.editor.counts[cat_key] = new_id

        self.refresh_id_list()
        self.load_single_id(new_id)
        self.status_label.setText(f"New ID {new_id} created.")
        self.status_label.setStyleSheet("color: green;")

    def delete_current_id(self):
        if not self.current_ids:
            return
        
        target_id = self.current_ids[0]
        cat_key = self.get_current_category_key()

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to clear/delete ID {target_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if target_id in self.editor.things[cat_key]:
            # Soft delete by clearing data
            minimal_texture = b"\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00"
            self.editor.things[cat_key][target_id] = {
                "props": OrderedDict(),
                "texture_bytes": minimal_texture,
            }
            
            self.refresh_id_list()
            self.load_single_id(target_id)
            self.status_label.setText(f"ID {target_id} cleared.")
            self.status_label.setStyleSheet("color: green;")

    def on_context_import(self):
        if not self.current_ids:
            return
        target_id = self.current_ids[0]
        cat_key = self.get_current_category_key()

        file_path, filter_used = QFileDialog.getOpenFileName(
            self,
            "Import Item",
            "",
            "Supported Files (*.png *.jpg *.obd);;Object Builder (*.obd);;Images (*.png *.jpg)",
        )

        if not file_path:
            return

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
            current_props = self.editor.things[cat_key][target_id]["props"]
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

        self.status_label.setText(
            f"Sprites adicionadas ao SPR. IDs: {new_sprite_ids[0]} - {new_sprite_ids[-1]}"
        )

        is_outfit = cat_key == "outfits"

        width = 1
        height = 1
        layers = 1
        pattern_x = 1
        pattern_y = 1
        pattern_z = 1
        frames = len(new_sprite_ids)

        if is_outfit:

            new_texture_bytes = self.build_outfit_texture_bytes(
                width, height, frames, new_sprite_ids
            )
        else:

            new_texture_bytes = self.build_texture_bytes(
                width, height, 1, 1, 1, 1, frames, new_sprite_ids
            )

        self.editor.things[cat_key][target_id]["texture_bytes"] = new_texture_bytes

        # Navigate to last sprite page to show the newly imported sprite
        self.sprite_page = (self.spr.sprite_count - 1) // self.sprites_per_page
        self.refresh_sprite_list()

        self.on_preview_click()
        QMessageBox.information(self, "Sucesso", "Importado com sucesso!")

    def on_context_replace(self):
        if not self.right_click_target:
            return

        target_id = self.right_click_target["id"]
        target_type = self.right_click_target["type"]

        if target_type != "sprite_list":
            QMessageBox.information(
                self,
                "Info",
                "Replace is currently only supported for Sprite List direct editing.",
            )
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "", "Image Files (*.png *.bmp)"
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

        if self.ids_list_frame.scroll_layout.count() > 0:
            widget = self.ids_list_frame.scroll_layout.itemAt(0).widget()
            if widget:
                widget.hide()

        self.current_ids = []


        self.refresh_id_list()  
        self.refresh_sprite_list() 

        self.clear_preview()

    def insert_ids(self):
        if not self.editor:
            QMessageBox.warning(self, "Warning", "Load a .dat file first.")
            return

        id_string = self.id_operation_entry.text().strip()
        ids_to_insert = []

        if not id_string:
            next_id = self.editor.counts["items"] + 1
            ids_to_insert = [next_id]
        else:
            ids_to_insert = self.parse_ids(id_string)

        if not ids_to_insert:
            QMessageBox.critical(self, "Error", "Invalid ID format.")

            return

        inserted_count = 0
        for new_id in ids_to_insert:
            if new_id in self.editor.things["items"]:
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

            empty_item = {"props": OrderedDict(), "texture_bytes": empty_texture}
            self.editor.things["items"][new_id] = empty_item
            inserted_count += 1

            if new_id > self.editor.counts["items"]:
                self.editor.counts["items"] = new_id

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
                last_id = self.editor.counts["items"]
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
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        ids_to_delete.sort(reverse=True)

        deleted_count = 0
        emptied_count = 0

        last_item_id = self.editor.counts["items"]
        ids_to_delete_set = set(ids_to_delete)

        while last_item_id in ids_to_delete_set:
            if last_item_id in self.editor.things["items"]:
                del self.editor.things["items"][last_item_id]
                ids_to_delete_set.remove(last_item_id)
                deleted_count += 1
            last_item_id -= 1

        self.editor.counts["items"] = last_item_id

        for item_id in ids_to_delete_set:
            if item_id in self.editor.things["items"]:
                minimal_texture = b"\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00"
                self.editor.things["items"][item_id] = {
                    "props": OrderedDict(),
                    "texture_bytes": minimal_texture,
                }
                emptied_count += 1

        status_message = ""
        if emptied_count > 0:
            status_message += f"{emptied_count} IDs were cleared. "
        if deleted_count > 0:
            status_message += (
                f"{deleted_count} IDs at the end of the list were removed."
            )

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
                preview.setStyleSheet(
                    "background-color: black; border: 1px solid gray;"
                )
                return

            idx = int(val)

            if attr_name == "ShowOnMinimap":
                if 0 <= idx <= 215:
                    r, g, b = ob_index_to_rgb(idx)
                    preview.setStyleSheet(
                        f"background-color: rgb({r}, {g}, {b}); border: 1px solid gray;"
                    )
                else:
                    preview.setStyleSheet(
                        "background-color: red; border: 1px solid gray;"
                    )
            elif attr_name == "HasLight_Color":
                if 0 <= idx <= 65535:
                    r, g, b = self.light_color_to_rgb(idx)
                    preview.setStyleSheet(
                        f"background-color: rgb({r}, {g}, {b}); border: 1px solid gray;"
                    )
                else:
                    preview.setStyleSheet(
                        "background-color: red; border: 1px solid gray;"
                    )
        except ValueError:
            preview.setStyleSheet("background-color: gray; border: 1px solid gray;")

    def light_color_to_rgb(self, color_val):
        r = (color_val & 0x1F) << 3
        g = ((color_val >> 5) & 0x1F) << 3
        b = ((color_val >> 10) & 0x1F) << 3
        return r, g, b

    def next_page(self):
        self.current_page += 1
        self.refresh_id_list()

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
        self.refresh_id_list()

    def last_id_page(self):
        if not self.editor:
            return
        cat_key = self.get_current_category_key()
        total_count = self.editor.counts[cat_key]
        start_offset = 100 if cat_key == "items" else 1
        max_page = max(0, (total_count - start_offset) // self.ids_per_page)
        self.current_page = max_page
        self.refresh_id_list()

    def skip_id_page(self):
        """Skip 10 pages forward in item list"""
        if not self.editor:
            return
        cat_key = self.get_current_category_key()
        total_count = self.editor.counts[cat_key]
        start_offset = 100 if cat_key == "items" else 1
        max_page = max(0, (total_count - start_offset) // self.ids_per_page)
        self.current_page = min(self.current_page + 10, max_page)
        self.refresh_id_list()

    def filter_id_list(self, text):
        self.current_page = 0
        self.refresh_id_list()

    def refresh_id_list(self):
        while self.ids_list_frame.scroll_layout.count():
            item = self.ids_list_frame.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.id_buttons.clear()

        if not self.editor:
            return

        self.show_loading("Loading Items...", progress_mode=True)

        cat_map = {
            "Item": "items",
            "Outfit": "outfits",
            "Effect": "effects",
            "Missile": "missiles",
        }
        current_cat_key = cat_map.get(self.category_combo.currentText(), "items")

        start_id_offset = 100 if current_cat_key == "items" else 1

        search_text = self.search_input.text().strip()
        
        end_id = 0
        max_id = 0
        
        if search_text:
            # Search mode: Find matching IDs
            try:
                search_id = int(search_text)
                matching_ids = []
                if search_id in self.editor.things[current_cat_key]:
                    matching_ids.append(search_id)
            except ValueError:
                # Naive text search if we had names, but here we only have IDs mostly.
                # Could search for IDs starting with text?
                matching_ids = []
                # If text is not a number, maybe we shouldn't search or search nothing.
                # But typically users might type "12" and expect "12", "120", "121"...
                # iterating all keys is expensive if logical dict is not sorted strings.
                # For now let's strict match ID or maybe 'contains' string logic on keys?
                # Optimization: iterate once if needed.
                pass
            
            # For this simplified version, let's just try exact ID match or direct lookup if numeric
            # If user wants partial match "12" -> 12, 120.. that requires iteration.
            # Let's assume exact ID for now to be safe on performance, or simple startswith if needed.
            
            # Better approach:
            matching_ids = []
            if search_text.isdigit():
                 exact_id = int(search_text)
                 if exact_id in self.editor.things[current_cat_key]:
                     matching_ids = [exact_id]
            
            # If we want to support partial ID search (e.g. type '34' get '3400', '3456')
            # we need to iterate.
            # let's skip expensive iteration for now unless requested.
            
            # Iterate through matching_ids instead of range
            loop_iterable = matching_ids
        else:
            # Normal pagination
            total_count = self.editor.counts[current_cat_key]
            start_index = self.current_page * self.ids_per_page
            current_start_id = start_index + start_id_offset
            max_id = total_count + 1 # rough upper bound or max key?
            # Actually keys might be sparse? The original code assumed continuous range.
            # Let's stick to original range logic.
            
            end_id = min(current_start_id + self.ids_per_page, self.editor.counts[current_cat_key] + 1000) # Safe upper bound
            # Original code used total_count + 1 as max_id.
            
            loop_iterable = range(current_start_id, end_id)

        total_items = len(list(loop_iterable)) if hasattr(loop_iterable, '__iter__') else end_id - current_start_id
        loop_iterable = list(loop_iterable) if not isinstance(loop_iterable, list) else loop_iterable
        
        for idx, item_id in enumerate(loop_iterable):
            # Update progress every 50 items for faster loading
            if idx % 50 == 0:
                self.update_progress(idx, total_items)
            
            item_frame = QFrame()
            item_frame.setObjectName("itemCard")
            item_frame.setFixedSize(130, 60)
            item_frame.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # Layout Horizontal: [Icon] [ID]
            item_layout = QHBoxLayout(item_frame)
            item_layout.setContentsMargins(5, 5, 5, 5)
            item_layout.setSpacing(10)

            # 1. Thumbnail
            sprite_label = ClickableLabel()
            sprite_label.setFixedSize(50, 50)
            sprite_label.setStyleSheet(
                "background-color: #2a2a3a; border: 1px solid rgba(74, 144, 226, 0.3); border-radius: 4px;"
            )
            sprite_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            if self.spr and item_id in self.editor.things[current_cat_key]:
                item = self.editor.things[current_cat_key][item_id]

                if current_cat_key == "outfits":
                    sprite_ids = DatEditor.extract_sprite_ids_from_outfit_texture(item["texture_bytes"])
                else:
                    sprite_ids = DatEditor.extract_sprite_ids_from_texture_bytes(item["texture_bytes"])

                if sprite_ids and sprite_ids[0] > 0:
                    try:
                        img = self.spr.get_sprite(sprite_ids[0])
                        if img:
                            img_resized = img.resize((48, 48), Image.NEAREST)
                            pixmap = pil_to_qpixmap(img_resized)
                            sprite_label.setPixmap(pixmap)
                    except Exception as e:
                        pass
            
            item_layout.addWidget(sprite_label)

            # 2. Number/ID
            id_lbl = ClickableLabel(str(item_id))
            id_lbl.setStyleSheet("color: #5b9bd5; font-weight: bold; font-size: 12px; border: none; background: transparent;")
            id_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item_layout.addWidget(id_lbl)

            # Signals
            def make_load_handler(iid):
                return lambda: self.load_single_id(iid)
            
            def make_context_handler(iid):
                return lambda pos: self.show_context_menu(pos, iid, "id_list")
            
            # Click events on frame, not just labels?
            # For now keep checking labels + frame if possible, 
            # but since we are using ClickableLabel, propagate events clearly.
            sprite_label.doubleClicked.connect(make_load_handler(item_id))
            id_lbl.doubleClicked.connect(make_load_handler(item_id))
            sprite_label.rightClicked.connect(make_context_handler(item_id))
            id_lbl.rightClicked.connect(make_context_handler(item_id))

            # Store for highlighting
            self.id_buttons[item_id] = item_frame # Mapping ID to Frame now, not Label
            
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

        # Skip button to jump 10 pages
        skip_btn = QPushButton("⏩")
        skip_btn.setMaximumWidth(60)
        skip_btn.setToolTip("Skip 10 pages")
        skip_btn.clicked.connect(self.skip_id_page)
        nav_layout.addWidget(skip_btn)

        # Last button to go to last page
        last_btn = QPushButton("⏭")
        last_btn.setMaximumWidth(60)
        last_btn.clicked.connect(self.last_id_page)
        nav_layout.addWidget(last_btn)

        # Posiciona a navegação abaixo de tudo
        self.ids_list_frame.scroll_layout.addWidget(nav_frame)
        # FlowLayout doesn't have setRowStretch, we rely on the layout itself.
        # self.ids_list_frame.scroll_layout.addStretch() # FlowLayout doesn't usually need explicit stretch for this use case
        self.hide_loading()

    def refresh_sprite_list(self):
        # Clear existing widgets
        while self.sprite_list_frame.scroll_layout.count():
            item = self.sprite_list_frame.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.sprite_thumbs.clear()
        self.visible_sprite_widgets = {}

        if not self.spr:
            return

        self.show_loading("Loading Sprites...", progress_mode=True)

        total = self.spr.sprite_count
        start = self.sprite_page * self.sprites_per_page + 1
        end = min(start + self.sprites_per_page, total + 1)
        
        total_sprites_to_load = end - start
        
        for idx, spr_id in enumerate(range(start, end)):
            # Update progress every 50 sprites for faster loading
            if idx % 50 == 0:
                self.update_progress(idx, total_sprites_to_load)
            
            item_frame = QFrame()
            item_frame.setFrameShape(QFrame.Shape.NoFrame)
            item_layout = QHBoxLayout(item_frame)
            item_layout.setContentsMargins(2, 1, 2, 1)

            is_current = spr_id == self.selected_sprite_id

            bg_color = "#28a745" if is_current else "transparent"
            txt_color = "white" if is_current else "white"

            def make_click_handler(sid):
                return lambda: self.select_sprite(sid, from_preview_click=False)

            img_label = DraggableLabel(sprite_id=spr_id)
            img_label.setMinimumSize(80, 80)
            img_label.setMaximumSize(80, 80)
            img_label.setStyleSheet(
                "background-color: #222121; border: 1px solid gray;"
            )
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            text_label = ClickableLabel(str(spr_id))
            text_label.setMinimumWidth(60)
            text_label.setStyleSheet(
                f"background-color: {bg_color}; color: {txt_color}; padding: 5px;"
            )
            text_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )

            self.visible_sprite_widgets[spr_id] = text_label

            img = self.spr.get_sprite(spr_id)
            if img:
                thumb = img.resize((72, 72), Image.NEAREST)
                pixmap = pil_to_qpixmap(thumb)
                img_label.setPixmap(
                    pixmap.scaled(
                        72,
                        72,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

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

        # Skip button to jump 10 pages
        skip_btn = QPushButton("⏩")
        skip_btn.setMaximumWidth(60)
        skip_btn.setToolTip("Skip 10 pages")
        skip_btn.clicked.connect(self.skip_sprite_page)
        nav_layout.addWidget(skip_btn)

        # Last button to go to last sprite page
        last_btn = QPushButton("⏭")
        last_btn.setMaximumWidth(60)
        last_btn.clicked.connect(self.last_sprite_page)
        nav_layout.addWidget(last_btn)

        self.sprite_list_frame.scroll_layout.addWidget(nav)
        self.sprite_list_frame.scroll_layout.addStretch()
        self.hide_loading()

    def update_list_selection_visuals(self):
        """
        Atualiza apenas as cores dos itens visíveis na lista, sem recarregar imagens.
        """
        if not hasattr(self, "visible_sprite_widgets"):
            return

        for spr_id, label_widget in self.visible_sprite_widgets.items():
            if spr_id == self.selected_sprite_id:
                try:
                    label_widget.setStyleSheet(
                        "background-color: #28a745; color: white; padding: 5px;"
                    )
                except:
                    pass
            else:
                try:
                    label_widget.setStyleSheet(
                        "background-color: transparent; color: white; padding: 5px;"
                    )
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

    def last_sprite_page(self):
        if not self.spr:
            return
        max_page = max(0, (self.spr.sprite_count - 1) // self.sprites_per_page)
        self.sprite_page = max_page
        self.refresh_sprite_list()

    def skip_sprite_page(self):
        """Skip 10 pages forward in sprite list"""
        if not self.spr:
            return
        max_page = max(0, (self.spr.sprite_count - 1) // self.sprites_per_page)
        self.sprite_page = min(self.sprite_page + 10, max_page)
        self.refresh_sprite_list()

    def goto_sprite_id(self):
        """Navigate directly to a specific sprite ID"""
        if not self.spr:
            return
        try:
            sprite_id = int(self.sprite_goto_entry.text().strip())
            if sprite_id < 1 or sprite_id > self.spr.sprite_count:
                self.status_label.setText(f"Sprite ID {sprite_id} out of range (1-{self.spr.sprite_count})")
                self.status_label.setStyleSheet("color: orange;")
                return
            
            # Navigate to the page containing this sprite
            self.sprite_page = (sprite_id - 1) // self.sprites_per_page
            self.refresh_sprite_list()
            
            # Select the sprite
            self.select_sprite(sprite_id, from_preview_click=False)
            
            self.status_label.setText(f"Navigated to sprite {sprite_id}")
            self.status_label.setStyleSheet("color: #90ee90;")
        except ValueError:
            self.status_label.setText("Invalid sprite ID")
            self.status_label.setStyleSheet("color: orange;")

    def change_preview_index(self, delta):
        if not self.current_preview_sprite_list:
            return
        
        count = len(self.current_preview_sprite_list)
        if count <= 1:
            return

        self.current_preview_index = (self.current_preview_index + delta) % count
        self.show_preview_at_index(self.current_preview_index)

    def toggle_animation(self):
        if not self.current_preview_sprite_list or len(self.current_preview_sprite_list) <= 1:
            return

        if self.is_animating:
            self.animation_timer.stop()
            self.is_animating = False
            self.anim_btn.setText("PLAY")
            self.anim_btn.setStyleSheet("font-size: 11px; font-weight: bold; background-color: #4a90e2; color: white; border-radius: 4px;") 
        else:
            self.is_animating = True
            self.anim_btn.setText("STOP")
            self.anim_btn.setStyleSheet("font-size: 11px; font-weight: bold; background-color: #ff5555; color: white; border-radius: 4px;")
            self.animation_timer.start(200) # 200 ms default

    def update_animation_step(self):
        if not self.is_animating:
            return
        self.change_preview_index(1)

    def update_preview_image(self):
        if (
            not self.spr
            or not hasattr(self, "current_preview_sprite_list")
            or not self.current_preview_sprite_list
        ):
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
            self.image_label.setPixmap(
                pixmap.scaled(
                    32,
                    32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._kept_image = pixmap
        else:
            self.image_label.clear()
            self.image_label.setText("Empty/Error")

        total = len(self.current_preview_sprite_list)
        self.prev_index_label.setText(
            f"Sprite {self.current_preview_index + 1} / {total}"
        )
        self.preview_info.setText(f"Sprite ID: {sprite_id}")

    def toggle_animation(self):
        if not self.current_preview_sprite_list:
            return

        if self.is_animating:
            self.animation_timer.stop()
            self.is_animating = False
            self.anim_btn.setText("PLAY")
            self.anim_btn.setStyleSheet("font-size: 11px; font-weight: bold; background-color: #4a90e2; color: white; border-radius: 4px;") 
        else:
            if len(self.current_preview_sprite_list) > 1:
                # Determine initial duration
                duration = 200
                if self.current_ids:
                    cat_key = self.get_current_category_key()
                    item_data = self.editor.things.get(cat_key, {}).get(self.current_ids[0])
                    if item_data:
                        durations = item_data.get("props", {}).get("FrameDurations", [])
                        if durations and len(durations) > self.current_preview_index:
                             # Use min_duration (index 0 of tuple)
                             duration = durations[self.current_preview_index][0]
                
                self.animation_timer.start(duration) 
                self.is_animating = True
                self.anim_btn.setText("STOP")
                self.anim_btn.setStyleSheet("font-size: 11px; font-weight: bold; background-color: #ff5555; color: white; border-radius: 4px;")

    def change_preview_index(self, delta):
        if not hasattr(self, "current_preview_sprite_list") or not self.current_preview_sprite_list:
            return

        if self.current_ids:
            cat_key = self.get_current_category_key()
            item_data = self.editor.things.get(cat_key, {}).get(self.current_ids[0])
            anim_count = item_data.get("props", {}).get("Animation", 1) if item_data else 1
            
            # If explicit animation count is > 1 use it, else generic list wrap
            if anim_count > 1:
                limit = anim_count
            else:
                limit = len(self.current_preview_sprite_list)
        else:
            limit = len(self.current_preview_sprite_list)

        if limit <= 0:
            return
            
        self.current_preview_index = (self.current_preview_index + delta) % limit
        self.update_preview_image()

    def update_animation_step(self):
        if not self.current_preview_sprite_list:
            self.animation_timer.stop()
            self.is_animating = False
            self.anim_btn.setText("Play Animation")
            return

        self.change_preview_index(1) # Next frame
        
        # Reset timer with new duration
        duration = 200
        if self.current_ids:
            cat_key = self.get_current_category_key()
            item_data = self.editor.things.get(cat_key, {}).get(self.current_ids[0])
            if item_data:
                durations = item_data.get("props", {}).get("FrameDurations", [])
                
                # Check bounds for durations
                idx = self.current_preview_index
                # If we are in outfit mode, frame index is separate from loop/direction?
                # Actually show_preview_at_index calculates absolute sprite index, 
                # but we need the 'animation phase' index.
                # Standard animation (items/outfits) has 'Animation' frames.
                
                anim_frames = item_data.get("props", {}).get("Animation", 1)
                
                # We need the relative animation frame index.
                # current_preview_index is effectively our frame index for items.
                # For outfits, it might be more complex if index includes direction?
                # Let's assume current_preview_index maps 1:1 to animation frame for now 
                # or is modulo'd correctly in change_preview_index.
                
                # In change_preview_index: 
                # self.current_preview_index = (self.current_preview_index + delta) % total_frames
                # But for outfits, total_frames in sprite_list != animation frames count.
                # Wait, current_preview_sprite_list for outfits contains ALL sprites?
                # If so, current_preview_index is just an index into that list.
                # We need to map it back to the animation phase index (0..frames-1).
                
                # Simplified approach: Use modulo with actual animation frame count from props
                if anim_frames > 1:
                     frame_idx = self.current_preview_index % anim_frames
                     if durations and len(durations) > frame_idx:
                         raw_dur = durations[frame_idx][0]
                         # Clamp to sensible int32 range (e.g. max 1 hour)
                         duration = max(10, min(int(raw_dur), 2147483647))

        self.animation_timer.start(duration)

    def on_preview_click(self):
        preview_list = getattr(self, "current_preview_sprite_list", [])

        if not preview_list:
            return

        idx = getattr(self, "current_preview_index", 0)
        if idx < 0 or idx >= len(preview_list):
            return

        current_sprite_id = preview_list[idx]

        self.select_sprite(current_sprite_id, from_preview_click=True)

        if hasattr(self, "status_label"):
            self.status_label.setText(
                f"Selected sprite {current_sprite_id} from preview."
            )
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
        if not self.editor:
            return

        cat_map = {
            "Item": "items",
            "Outfit": "outfits",
            "Effect": "effects",
            "Missile": "missiles",
        }
        current_cat_key = cat_map.get(self.category_combo.currentText(), "items")
        
            
        self.current_framegroup_index = 0
        self.outfit_addon1_enabled = False
        self.outfit_addon2_enabled = False
        self.outfit_mount_enabled = False
        self.outfit_mask_enabled = False
        self.outfit_walk_enabled = False

    
        self.current_ids = [item_id]
        self.id_entry.setText(str(item_id))

        self.update_checkboxes_for_ids(current_cat_key)
        self.prepare_preview_for_current_ids(current_cat_key)

        for iid, button in self.id_buttons.items():
            if iid == item_id:
                button.setStyleSheet(
                    "background-color: #28a745; color: white; border: 1px solid #34ce57; padding: 5px;"
                )
            else:
                button.setStyleSheet(
                    "background-color: gray15; color: white; padding: 5px;"
                )

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

    def browse_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select the .dat file", "", "DAT files (*.dat);;All files (*.*)"
        )
        if not filepath:
            return
            
        self.save_settings(filepath)
        self.file_input.setText(filepath)

    def on_load_clicked(self):
        filepath = self.file_input.text()
        if not filepath:
            return
        self.load_dat_file_from_path(filepath)

    def load_dat_file_from_path(self, filepath):
        self.file_input.setText(filepath)

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
                self.show_loading("Found .spr file.\nLoading sprites...", progress_mode=True)

                if hasattr(self, "spr") and self.spr:
                    pass
                self.spr = SprEditor(spr_path, transparency=is_transparency)
                
                def update_spr_progress(current, total):
                    self.update_progress(current, total, message=f"Loading Sprites...\n{current}/{total}")
                    
                self.spr.load(progress_callback=update_spr_progress)

                self.preview_info.setText(
                    f"SPR loaded: {os.path.basename(spr_path)}\nSprites: {self.spr.sprite_count}"
                )
                self.sprite_page = 0

                self.refresh_sprite_list()

            self.refresh_id_list()

        except Exception as e:
            print(e)
            
            # Smart Error Hinting
            hints = []
            if not is_extended:
                hints.append("- Try checking 'Extended' (Client 9.60+).")
            if not is_transparency:
                hints.append("- Try checking 'Transparency' (Client 10.50+).")
            
            hint_msg = ""
            if hints:
                hint_msg = "\n\n💡 Suggestion:\n" + "\n".join(hints)
            
            QMessageBox.critical(
                self, "Load Error", f"Could not load the file.\n\nError: {e}{hint_msg}"
            )
            self.status_label.setText("Failed to load file.")
            self.status_label.setStyleSheet("color: red;")

        finally:
            self.hide_loading()

            spr_count = 0
            if hasattr(self, "spr") and self.spr is not None:
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
        if not id_string:
            return []
        try:
            parts = id_string.split(",")
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                if "-" in part:
                    start, end = map(int, part.split("-"))
                    ids.update(range(start, end + 1))
                else:
                    ids.add(int(part))
            return sorted(list(ids))
        except ValueError:
            self.status_label.setText("Error: Invalid ID format.")
            self.status_label.setStyleSheet("color: orange;")

            return []

    def load_ids_from_entry(self):
        if not self.editor:
            return

        id_string = self.id_entry.text()
        self.current_ids = self.parse_ids(id_string)

        if not self.current_ids:
            if id_string:
                QMessageBox.warning(self, "Invalid IDs", "Incorrect format.")
            for cb in self.checkboxes.values():
                cb.setChecked(False)
            self.clear_preview()
            return
            
            
        self.current_framegroup_index = 0
        self.outfit_addon1_enabled = False
        self.outfit_addon2_enabled = False
        self.outfit_mount_enabled = False
        self.outfit_mask_enabled = False
        self.outfit_walk_enabled = False
            

        cat_map = {
            "Item": "items",
            "Outfit": "outfits",
            "Effect": "effects",
            "Missile": "missiles",
        }
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
                    button.setStyleSheet(
                        "background-color: #28a745; color: white; border: 1px solid #34ce57; padding: 5px;"
                    )
                else:
                    button.setStyleSheet(
                        "background-color: gray15; color: white; padding: 5px;"
                    )

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
        if not self.current_ids:
            return

        things_dict = self.editor.things.get(category, {})

        for attr_name, cb in self.checkboxes.items():
            states = [
                attr_name in things_dict[item_id]["props"]
                for item_id in self.current_ids
                if item_id in things_dict
            ]

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
        if not entry:
            return

        values = []
        things_dict = self.editor.things.get(category, {})

        for item_id in self.current_ids:
            item = things_dict.get(item_id)
            if item and data_key in item["props"]:
                data = item["props"][data_key]

                if isinstance(data, tuple):
                    if len(data) > index:
                        values.append(data[index])
                else:
                    values.append(data)

        if not values:
            entry.clear()
            if entry_key in self.numeric_previews:
                self.numeric_previews[entry_key].setStyleSheet(
                    "background-color: #888888; border: 1px solid gray;"
                )
        elif all(v == values[0] for v in values):
            entry.setText(str(values[0]))
            if entry_key in self.numeric_previews:
                self.update_color_preview(entry_key)
        else:
            entry.clear()
            if entry_key in self.numeric_previews:
                self.numeric_previews[entry_key].setStyleSheet(
                    "background-color: gray; border: 1px solid gray;"
                )

    def apply_changes(self):
        if not self.editor or not self.current_ids:
            QMessageBox.warning(
                self, "No Action", "Load a file and check some IDs first."
            )
            return

        to_set, to_unset = [], []
        original_states = {}

        cat_map = {
            "Item": "items",
            "Outfit": "outfits",
            "Effect": "effects",
            "Missile": "missiles",
        }
        current_cat_key = cat_map.get(self.category_combo.currentText(), "items")

        things_dict = self.editor.things.get(current_cat_key, {})

        for attr_name in self.checkboxes:
            states = [
                attr_name in things_dict[item_id]["props"]
                for item_id in self.current_ids
                if item_id in things_dict
            ]

            if not states:
                original_states[attr_name] = "none"
            elif all(states):
                original_states[attr_name] = "all"
            elif not any(states):
                original_states[attr_name] = "none"
            else:
                original_states[attr_name] = "mixed"

        for attr_name, cb in self.checkboxes.items():
            if cb.isChecked() and original_states[attr_name] != "all":
                to_set.append(attr_name)
            elif not cb.isChecked() and original_states[attr_name] != "none":
                to_unset.append(attr_name)

        changes_applied = False

        changes_applied |= self.apply_numeric_attribute(
            "ShowOnMinimap", "ShowOnMinimap_data", 0, False, category=current_cat_key
        )
        changes_applied |= self.apply_numeric_attribute(
            "HasElevation", "HasElevation_data", 0, False, category=current_cat_key
        )
        changes_applied |= self.apply_numeric_attribute(
            "Ground", "Ground_data", 0, False, category=current_cat_key
        )

        offset_applied = self.apply_offset_attribute(category=current_cat_key)
        changes_applied |= offset_applied

        light_applied = self.apply_light_attribute(category=current_cat_key)
        changes_applied |= light_applied

        if to_set or to_unset:
            self.editor.apply_changes(
                self.current_ids, to_set, to_unset, category=current_cat_key
            )
            changes_applied = True

        if not changes_applied:
            self.status_label.setText("No changes detected.")
            self.status_label.setStyleSheet("color: yellow;")
            return

        self.status_label.setText("Changes applied. Save with 'Compile as...'")
        self.status_label.setStyleSheet("color: green;")

        self.update_checkboxes_for_ids(category=current_cat_key)
        self.prepare_preview_for_current_ids(category=current_cat_key)

    def apply_numeric_attribute(
        self, entry_key, data_key, index, signed, category="items"
    ):
        entry = self.numeric_entries.get(entry_key)
        if not entry:
            return False
        val_str = entry.text().strip()
        if not val_str:
            return False

        try:
            val = int(val_str)

            for item_id in self.current_ids:
                if item_id in self.editor.things[category]:
                    props = self.editor.things[category][item_id]["props"]
                    attr_name = data_key.replace("_data", "")
                    props[attr_name] = True
                    props[data_key] = (val,)
            return True
        except ValueError:
            return False

    def apply_offset_attribute(self, category="items"):
        x_entry = self.numeric_entries.get("HasOffset_X")
        y_entry = self.numeric_entries.get("HasOffset_Y")
        if not x_entry or not y_entry:
            return False

        x_str = x_entry.text().strip()
        y_str = y_entry.text().strip()
        if not x_str and not y_str:
            return False

        try:
            x_val = int(x_str) if x_str else 0
            y_val = int(y_str) if y_str else 0

            for item_id in self.current_ids:
                if item_id in self.editor.things[category]:
                    props = self.editor.things[category][item_id]["props"]
                    props["HasOffset"] = True
                    props["HasOffset_data"] = (x_val, y_val)
            return True
        except ValueError:
            return False

    def apply_light_attribute(self, category="items"):
        level_entry = self.numeric_entries.get("HasLight_Level")
        color_entry = self.numeric_entries.get("HasLight_Color")
        if not level_entry or not color_entry:
            return False

        level_str = level_entry.text().strip()
        color_str = color_entry.text().strip()
        if not level_str and not color_str:
            return False

        try:
            level_val = int(level_str) if level_str else 0
            color_val = int(color_str) if color_str else 0

            for item_id in self.current_ids:
                if item_id in self.editor.things[category]:
                    props = self.editor.things[category][item_id]["props"]
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
            "DAT files (*.dat);;All files (*.*)",
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

            self.status_label.setText(
                f"Saved successfully: {os.path.basename(filepath)}"
            )
            self.status_label.setStyleSheet("color: #90ee90;")  # Light green

            QMessageBox.information(
                self, "Success", f"Files compiled successfully!{msg_extra}"
            )

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
        self.current_item_patx = 1
        self.current_item_paty = 1
        self.current_item_patz = 1        

        # Auto-stop animation when switching items to prevent ghosting, 
        # but we will auto-start later if needed.
        if self.is_animating:
             self.animation_timer.stop()
             self.is_animating = False
             self.anim_btn.setText("PLAY")
             self.anim_btn.setStyleSheet("font-size: 11px; font-weight: bold; background-color: #4a90e2; color: white; border-radius: 4px;") 


        if not self.editor or not self.spr or not self.current_ids:
            self.clear_preview()
            return

        things_dict = self.editor.things.get(category, {})

        for item_id in self.current_ids:
            item = things_dict.get(item_id)
            if not item:
                continue

            props = item.get("props", {})
            item_texture_bytes = item.get("texturebytes", b"")
            self.current_item_width = props.get("Width", 1)
            self.current_item_height = props.get("Height", 1)
            self.current_item_layers = props.get("Layers", 1)
            self.current_item_patx = props.get("PatternX", 1)
            self.current_item_paty = props.get("PatternY", 1)
            self.current_item_patz = props.get("PatternZ", 1)            

            if category == "outfits":
                sprite_ids = DatEditor.extract_outfit_group_sprites(
                    item["texture_bytes"],
                    self.current_framegroup_index, 
                    self.editor.extended                    
                )
            else:
                sprite_ids = DatEditor.extract_sprite_ids_from_texture_bytes(
                    item["texture_bytes"]
                )

            if sprite_ids:
                self.current_preview_sprite_list = sprite_ids
                break

        if not self.current_preview_sprite_list:
            self.clear_preview()
            return

        # Auto-Play Animation check
        anim_count = item.get("props", {}).get("Animation", 1)
        if anim_count > 1:
             if not self.is_animating:
                 self.is_animating = True
                 self.anim_btn.setText("STOP")
                 self.anim_btn.setStyleSheet("font-size: 11px; font-weight: bold; background-color: #ff5555; color: white; border-radius: 4px;")
                 self.animation_timer.start(200)
        
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





    def show_preview_at_index(self, anim_frame_index):
        if not self.current_preview_sprite_list:
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("No Sprite")
            return

        catkey = self.get_current_category_key()
        width = getattr(self, "current_item_width", 1)
        height = getattr(self, "current_item_height", 1)
        layers = getattr(self, "current_item_layers", 1)
        patx = getattr(self, "current_item_patx", 1)
        paty = getattr(self, "current_item_paty", 1)
        patz = getattr(self, "current_item_patz", 1) 
        
        sprites_per_view = width * height * layers
        dir_offset = 0

        if catkey == "outfits":
 
            if self.outfit_addon1_enabled:
                current_paty = 1  
            elif self.outfit_addon2_enabled:
                current_paty = 2  
            else:
                current_paty = 0 
            
            if self.outfit_mount_enabled:
                current_patz = 1  
            else:
                current_patz = 0  
            
            outfit_dir_map = {
                "N": 0, "NW": 0, "NE": 0, "E": 1, "S": 2, "SE": 2, "SW": 2, "W": 3, "C": 2,
            }
            dir_idx = outfit_dir_map.get(self.current_direction_key, 2)
            if dir_idx >= patx:
                dir_idx = 0
            

            sprites_per_direction = sprites_per_view
            sprites_per_paty = sprites_per_direction * patx  
            sprites_per_patz = sprites_per_paty * paty
            sprites_per_frame = sprites_per_patz * patz
            
            base_frame = anim_frame_index * sprites_per_frame
            patz_offset = current_patz * sprites_per_paty * paty
            paty_offset = current_paty * sprites_per_paty
            dir_offset = dir_idx * sprites_per_view
            
            final_start_index = base_frame + patz_offset + paty_offset + dir_offset
            
        elif catkey == "missiles" and patx == 3 and paty == 3:
            missile_map = {"NW": 0, "N": 1, "NE": 2, "W": 3, "C": 4, "E": 5, "SW": 6, "S": 7, "SE": 8}
            dir_idx = missile_map.get(self.current_direction_key, 4)
            sprites_per_frame = sprites_per_view * patx * paty
            base_index = anim_frame_index * sprites_per_frame
            dir_offset = dir_idx * sprites_per_view
            final_start_index = base_index + dir_offset
        else:
            sprites_per_anim_step = sprites_per_view * 1
            final_start_index = anim_frame_index * sprites_per_anim_step

        total_w = width * 32
        total_h = height * 32
        combined_image = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))

     
        if catkey == "outfits":
            if self.outfit_mask_enabled:
                
                layers_to_render = range(layers - 1, layers)  
            else:
       
                if layers > 1:
                    layers_to_render = range(0, layers - 1)  
                else:
                    layers_to_render = range(0, layers) 
        else:
  
            layers_to_render = range(layers)

        try:
            for l in layers_to_render:
 
                layer_offset = l * (width * height)
                
                for y in range(height):
                    for x in range(width):
                
                        idx_in_layer = y * width + x
                        sprite_idx = final_start_index + layer_offset + idx_in_layer
                        
                        if sprite_idx >= len(self.current_preview_sprite_list):
                            break
                            
                        sprite_id = self.current_preview_sprite_list[sprite_idx]
                        
                        if sprite_id > 0 and self.spr:
                            img_data = self.spr.get_sprite(sprite_id)
                            if img_data:
                                px = (width - 1 - x) * 32
                                py = (height - 1 - y) * 32
                                combined_image.paste(img_data, (px, py), img_data)
        except Exception as e:
            print(f"Preview error: {e}")

        qpix = pil_to_qpixmap(combined_image)
        zoom_factor = 2
        qpix = qpix.scaled(
            total_w * zoom_factor,
            total_h * zoom_factor,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )

        if width > 1 or height > 1:
            painter = QPainter(qpix)
            pen = QColor(255, 255, 255, 80)
            painter.setPen(pen)
            sprite_screen_size = 32 * zoom_factor
            for gx in range(width):
                for gy in range(height):
                    x0 = gx * sprite_screen_size
                    y0 = gy * sprite_screen_size
                    painter.drawRect(x0, y0, sprite_screen_size - 1, sprite_screen_size - 1)
            painter.end()

        self.image_label.setPixmap(qpix)
        
        addon_status = ""
        if catkey == "outfits":
            if self.outfit_addon1_enabled:
                addon_status += " | Addon 1"
            elif self.outfit_addon2_enabled:
                addon_status += " | Addon 2"
            if self.outfit_mount_enabled:
                addon_status += " | Mount"
            if self.outfit_mask_enabled:
                addon_status += " | MASK"
        
        self.prev_index_label.setText(
            f"Frame {anim_frame_index} | Dir: {self.current_direction_key}{addon_status}"
        )



    def reconstruct_item_image(self, sprite_ids):
        width = self.current_item_width
        height = self.current_item_height
        layers = self.current_item_layers

        expected_count = width * height * layers
        if len(sprite_ids) < expected_count:
            return None

        canvas_w = width * 32
        canvas_h = height * 32
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

        idx = 0

        for l in range(layers):
            for h in range(height):
                for w in range(width):
                    if idx >= len(sprite_ids):
                        break

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

        overlay_layout = QVBoxLayout(self.loading_overlay)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.loading_label = QLabel("Loading...", self.loading_overlay)
        self.loading_label.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: white; background: transparent;"
        )
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        overlay_layout.addWidget(self.loading_label)

        self.loading_progress = QProgressBar(self.loading_overlay)
        self.loading_progress.setFixedWidth(400)
        self.loading_progress.setFixedHeight(20)
        self.loading_progress.setTextVisible(True)
        self.loading_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #4a90e2;
                border-radius: 10px;
                background-color: #1e1e2e;
                color: white;
                font-weight: bold;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4a90e2, stop:1 #00d2ff);
                border-radius: 8px;
            }
        """)
        overlay_layout.addWidget(self.loading_progress)

    def show_loading(self, message="Loading...", progress_mode=False):
        if hasattr(self, "loading_overlay"):
            self.loading_label.setText(message)
            if hasattr(self, "loading_progress"):
                self.loading_progress.show()
                if progress_mode:
                    self.loading_progress.setRange(0, 100) # Reset to definitive
                    self.loading_progress.setValue(0)
                else:
                    self.loading_progress.setRange(0, 0) # Indeterminate mode

            self.loading_overlay.resize(self.size())
            self.loading_overlay.raise_()
            self.loading_overlay.show()

            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

    def update_progress(self, value, total, message=None):
        if hasattr(self, "loading_progress") and self.loading_overlay.isVisible():
            percentage = 0
            if total > 0:
                percentage = int((value / total) * 100)
            
            self.loading_progress.setValue(percentage)
            
            if message:
                self.loading_label.setText(message)
            
            self.loading_progress.setFormat(f"{percentage}%")

            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

    def hide_loading(self):
        if hasattr(self, "loading_overlay"):
            self.loading_overlay.hide()

    def resizeEvent(self, event):
        if hasattr(self, "loading_overlay") and self.loading_overlay.isVisible():
            self.loading_overlay.resize(self.size())
        super().resizeEvent(event)

    def open_looktype_generator(self):
        try:
            self.looktype_gen_window = LookTypeGeneratorWindow(self)
            self.looktype_gen_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open LookType Generator: {e}")

    def open_monster_generator(self):
        try:
            self.monster_gen_window = MonsterGeneratorWindow(self)
            self.monster_gen_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Monster Generator: {e}")

    def open_spell_maker(self):
        try:
            self.spell_maker_window = SpellMakerWindow(self)
            self.spell_maker_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Spell Maker: {e}")

    def open_shader(self):
        try:
            self.shader_window = ShaderEditor()
            self.shader_window.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Shader Editor: {e}")

    def open_particle(self):
        try:
            self.particle_window = ParticleGenerator()
            self.particle_window.run()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Particle Editor: {e}")

    def open_sprite_editor(self):
        try:
             self.slice_window = SliceWindow(self)
             self.slice_window.show()
        except Exception as e:
             QMessageBox.critical(self, "Error", f"Failed to open Sprite Editor: {e}")

    def open_sprite_optimizer(self):
        try:
             if not self.spr or not self.editor:
                 QMessageBox.warning(self, "Warning", "Please load DAT and SPR files first.")
                 return
             self.optimizer_window = SpriteOptimizerWindow(self.spr, self.editor, self)
             self.optimizer_window.show()
        except Exception as e:
             QMessageBox.critical(self, "Error", f"Failed to open Sprite Optimizer: {e}")
