"""
Assets Editor (Tibia 12+) - Module for ItemManager
Supports: catalog-content.json, appearances.dat (protobuf), LZMA sprite sheets
Based on: https://github.com/Arch-Mina/Assets-Editor
"""

import io
import json
import lzma
import os
import re
import struct
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False
    
try:
    import lxml.etree as ET
except ImportError:
    import xml.etree.ElementTree as ET
    
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from PIL import Image
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog,
    QGridLayout, QListWidget, QListWidgetItem, QScrollArea, QGroupBox,
    QTextEdit, QLineEdit, QCheckBox, QSpinBox, QTabWidget, QMessageBox,
    QProgressBar, QSplitter, QFrame, QComboBox, QDoubleSpinBox
)

# Try to import protobuf-generated classes, fall back to manual parsing
try:
    from google.protobuf import json_format
    from google.protobuf.message import DecodeError
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False

# Import or define appearance structures
try:
    import appearances_pb2
    PROTO_CLASSES_AVAILABLE = True
except ImportError:
    PROTO_CLASSES_AVAILABLE = False


# ==================== DATA STRUCTURES ====================

@dataclass
class CatalogEntry:
    """Represents an entry in catalog-content.json"""
    file: str
    type: str  # 'appearances' or 'sprite'
    sprite_type: int = 0
    first_sprite_id: int = 0
    last_sprite_id: int = 0
    area: int = 0
    version: int = 0


@dataclass
class AppearanceData:
    """Simplified appearance data for UI display"""
    id: int
    name: str = ""
    description: str = ""
    category: str = "object"  # object, outfit, effect, missile
    sprite_ids: List[int] = field(default_factory=list)
    flags: Dict = field(default_factory=dict)
    frame_groups: List = field(default_factory=list)


# ==================== LZMA HANDLER ====================

class LZMAHandler:
    """Handles LZMA decompression for Tibia sprite sheets"""
    
    @staticmethod
    def decompress_tibia_lzma(file_path: str) -> Optional[Image.Image]:
        """
        Decompress a Tibia LZMA sprite sheet file.
        
        Tibia uses a custom 32-byte header before the LZMA data:
        - Padding with NULL bytes
        - Magic sequence: 70 0A FA 80 24
        - LZMA file size as 7-bit encoded integer
        - Standard LZMA properties (5 bytes)
        - Decompressed size (8 bytes, but Tibia writes compressed size)
        """
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            # Implementation based on LZMA.cs:
            # 1. Skip variable number of NULL bytes at start
            # 2. Skip magic sequence: 70 0A FA 80 24
            # 3. Skip LZMA file size encoded as 7-bit integer
            # 4. Read Decoder Properties (5 bytes)
            # 5. Skip Decompressed Size (8 bytes) - often wrong in CIP files
            # 6. Decompress remaining data
            
            pos = 0
            
            # 1. Skip NULL bytes
            while pos < len(data) and data[pos] == 0:
                pos += 1
            
            # 2. Skip Magic used by Tibia (5 bytes)
            # "70 0A FA 80 24"
            if pos + 5 < len(data): # check expected magic just in case, or just skip
                pos += 5 
            
            # 3. Skip 7-bit encoded size
            # Loop until MSB is 0 (end of 7-bit int)
            while pos < len(data):
                byte = data[pos]
                pos += 1
                if (byte & 0x80) == 0:
                    break
            
            # 4. Read Properties (5 bytes)
            if pos + 5 > len(data):
                return None
            properties = data[pos:pos+5]
            pos += 5
            
            # 5. Skip 8 bytes (decompressed size)
            pos += 8
            
            # 6. Decompress remaining data using lzma with raw format + properties
            compressed_data = data[pos:]
            
            # Prepare data with standard LZMA header for Python module if possible
            # Python's lzma module supports RAW format with filters
            
            # Create LZMA filters
            # Standard LZMA (lzma1) with properties from file
            # Properties format: lc (v%9), lp, pb...
            # We can use FORMAT_RAW with filters
            
            # Extract lzma properties to construct filter
            # prop byte = (pb * 5 + lp) * 9 + lc
            prop = properties[0]
            if prop >= (9 * 5 * 5):
                prop //= 9
                
            lc = prop % 9
            prop //= 9
            lp = prop % 5
            pb = prop // 5
            
            dic_size = struct.unpack('<I', properties[1:5])[0]
            
            filters = [
                {
                    "id": lzma.FILTER_LZMA1,
                    "dict_size": dic_size,
                    "lc": lc,
                    "lp": lp,
                    "pb": pb,
                }
            ]
            
            try:
                decompressed = lzma.decompress(
                    compressed_data, 
                    format=lzma.FORMAT_RAW, 
                    filters=filters
                )
            except lzma.LZMAError:
                 # Fallback: Just try auto decoding entire blob stripping header manually
                 # Some variations exist.
                 # Let's try FORMAT_ALONE if we prepend a standard header?
                 try:
                     # 13 bytes header: 5 bytes props + 8 bytes size (-1 if unknown)
                     header = properties + (0xFFFFFFFFFFFFFFFF).to_bytes(8, 'little')
                     decompressed = lzma.decompress(header + compressed_data, format=lzma.FORMAT_ALONE)
                 except:
                     return None
            
            # Convert to PIL Image (it's a BMP)
            img = Image.open(io.BytesIO(decompressed))
            return img.convert('RGBA')
            
        except Exception as e:
            print(f"LZMA decompression error for {os.path.basename(file_path)}: {e}")
            return None
    
    @staticmethod
    def decompress_raw_lzma(data: bytes) -> Optional[bytes]:
        """Decompress raw LZMA data without Tibia header"""
        try:
            return lzma.decompress(data, format=lzma.FORMAT_ALONE)
        except lzma.LZMAError:
            try:
                return lzma.decompress(data, format=lzma.FORMAT_AUTO)
            except:
                return None


# ==================== PROTOBUF PARSER ====================

class AppearancesParser:
    """Parse appearances.dat protobuf binary"""
    
    def __init__(self):
        self.objects: List[AppearanceData] = []
        self.outfits: List[AppearanceData] = []
        self.effects: List[AppearanceData] = []
        self.missiles: List[AppearanceData] = []
    
    def parse(self, file_path: str) -> bool:
        """Parse appearances.dat file"""
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
            
            return self._parse_protobuf(data)
        except Exception as e:
            print(f"Parse error: {e}")
            return False
    
    def _parse_protobuf(self, data: bytes) -> bool:
        """Parse protobuf binary data"""
        try:
            pos = 0
            while pos < len(data):
                # Read field tag
                if pos >= len(data):
                    break
                    
                tag_byte = data[pos]
                pos += 1
                
                field_number = tag_byte >> 3
                wire_type = tag_byte & 0x07
                
                if wire_type == 2:  # Length-delimited
                    # Read varint length
                    length, bytes_read = self._read_varint(data, pos)
                    pos += bytes_read
                    
                    if pos + length > len(data):
                        break
                    
                    field_data = data[pos:pos + length]
                    pos += length
                    
                    # Field 1 = objects, 2 = outfits, 3 = effects, 4 = missiles
                    if field_number == 1:
                        app = self._parse_appearance(field_data, "object")
                        if app:
                            self.objects.append(app)
                    elif field_number == 2:
                        app = self._parse_appearance(field_data, "outfit")
                        if app:
                            self.outfits.append(app)
                    elif field_number == 3:
                        app = self._parse_appearance(field_data, "effect")
                        if app:
                            self.effects.append(app)
                    elif field_number == 4:
                        app = self._parse_appearance(field_data, "missile")
                        if app:
                            self.missiles.append(app)
                else:
                    # Skip other wire types
                    if wire_type == 0:  # Varint
                        _, bytes_read = self._read_varint(data, pos)
                        pos += bytes_read
                    elif wire_type == 1:  # 64-bit
                        pos += 8
                    elif wire_type == 5:  # 32-bit
                        pos += 4
                    else:
                        break
            
            return True
            
        except Exception as e:
            print(f"Protobuf parse error: {e}")
            return False
    
    def _parse_appearance(self, data: bytes, category: str) -> Optional[AppearanceData]:
        """Parse a single appearance message"""
        try:
            app = AppearanceData(id=0, category=category)
            pos = 0
            
            while pos < len(data):
                if pos >= len(data):
                    break
                
                tag_byte = data[pos]
                pos += 1
                
                field_number = tag_byte >> 3
                wire_type = tag_byte & 0x07
                
                if wire_type == 0:  # Varint
                    value, bytes_read = self._read_varint(data, pos)
                    pos += bytes_read
                    
                    if field_number == 1:  # id
                        app.id = value
                        
                elif wire_type == 2:  # Length-delimited
                    length, bytes_read = self._read_varint(data, pos)
                    pos += bytes_read
                    
                    if pos + length > len(data):
                        break
                    
                    field_data = data[pos:pos + length]
                    pos += length
                    
                    if field_number == 2:  # frame_group
                        sprite_ids = self._parse_frame_group(field_data)
                        app.sprite_ids.extend(sprite_ids)
                    elif field_number == 3:  # flags
                        app.flags = self._parse_flags(field_data)
                    elif field_number == 4:  # name
                        app.name = field_data.decode('utf-8', errors='ignore')
                    elif field_number == 5:  # description  
                        app.description = field_data.decode('utf-8', errors='ignore')
                else:
                    # Skip other wire types
                    if wire_type == 1:
                        pos += 8
                    elif wire_type == 5:
                        pos += 4
                    else:
                        break
            
            return app
            
        except Exception as e:
            return None
    
    def _parse_frame_group(self, data: bytes) -> List[int]:
        """Parse frame group to extract sprite IDs"""
        sprite_ids = []
        pos = 0
        
        try:
            while pos < len(data):
                if pos >= len(data):
                    break
                
                tag_byte = data[pos]
                pos += 1
                
                field_number = tag_byte >> 3
                wire_type = tag_byte & 0x07
                
                if wire_type == 0:  # Varint
                    value, bytes_read = self._read_varint(data, pos)
                    pos += bytes_read
                elif wire_type == 2:  # Length-delimited
                    length, bytes_read = self._read_varint(data, pos)
                    pos += bytes_read
                    
                    if pos + length > len(data):
                        break
                    
                    field_data = data[pos:pos + length]
                    pos += length
                    
                    if field_number == 3:  # sprite_info
                        ids = self._parse_sprite_info(field_data)
                        sprite_ids.extend(ids)
                else:
                    if wire_type == 1:
                        pos += 8
                    elif wire_type == 5:
                        pos += 4
                    else:
                        break
        except:
            pass
        
        return sprite_ids
    
    def _parse_sprite_info(self, data: bytes) -> List[int]:
        """Parse sprite info to get sprite IDs"""
        sprite_ids = []
        pos = 0
        
        try:
            while pos < len(data):
                if pos >= len(data):
                    break
                
                tag_byte = data[pos]
                pos += 1
                
                field_number = tag_byte >> 3
                wire_type = tag_byte & 0x07
                
                if wire_type == 0:  # Varint
                    value, bytes_read = self._read_varint(data, pos)
                    pos += bytes_read
                    
                    if field_number == 5:  # sprite_id (repeated)
                        sprite_ids.append(value)
                        
                elif wire_type == 2:  # Length-delimited (packed repeated)
                    length, bytes_read = self._read_varint(data, pos)
                    pos += bytes_read
                    
                    if pos + length > len(data):
                        break
                    
                    field_data = data[pos:pos + length]
                    pos += length
                    
                    if field_number == 5:  # packed sprite_ids
                        inner_pos = 0
                        while inner_pos < len(field_data):
                            val, br = self._read_varint(field_data, inner_pos)
                            inner_pos += br
                            sprite_ids.append(val)
                else:
                    if wire_type == 1:
                        pos += 8
                    elif wire_type == 5:
                        pos += 4
                    else:
                        break
        except:
            pass
        
        return sprite_ids
    
    def _parse_flags(self, data: bytes) -> Dict:
        """Parse appearance flags"""
        flags = {}
        pos = 0
        
        flag_names = {
            1: 'bank', 2: 'clip', 3: 'bottom', 4: 'top', 5: 'container',
            6: 'cumulative', 7: 'usable', 8: 'forceuse', 9: 'multiuse',
            10: 'write', 11: 'write_once', 12: 'liquidpool', 13: 'unpass',
            14: 'unmove', 15: 'unsight', 16: 'avoid', 17: 'no_movement_animation',
            18: 'take', 19: 'liquidcontainer', 20: 'hang', 21: 'hook',
            22: 'rotate', 23: 'light', 24: 'dont_hide', 25: 'translucent',
            26: 'shift', 27: 'height', 28: 'lying_object', 29: 'animate_always',
            30: 'automap', 31: 'lenshelp', 32: 'fullbank', 33: 'ignore_look',
            34: 'clothes', 35: 'default_action', 36: 'market', 37: 'wrap',
            38: 'unwrap', 39: 'topeffect', 42: 'corpse', 43: 'player_corpse',
            44: 'cyclopediaitem', 45: 'ammo', 46: 'show_off_socket',
            47: 'reportable', 48: 'upgradeclassification'
        }
        
        try:
            while pos < len(data):
                if pos >= len(data):
                    break
                
                tag_byte = data[pos]
                pos += 1
                
                field_number = tag_byte >> 3
                wire_type = tag_byte & 0x07
                
                flag_name = flag_names.get(field_number, f'flag_{field_number}')
                
                if wire_type == 0:  # Varint (bool or enum)
                    value, bytes_read = self._read_varint(data, pos)
                    pos += bytes_read
                    flags[flag_name] = bool(value) if value in (0, 1) else value
                    
                elif wire_type == 2:  # Length-delimited (sub-message)
                    length, bytes_read = self._read_varint(data, pos)
                    pos += bytes_read
                    
                    if pos + length > len(data):
                        break
                    
                    field_data = data[pos:pos + length]
                    pos += length
                    
                    # Parse sub-message for complex flags
                    flags[flag_name] = self._parse_flag_submessage(field_data, flag_name)
                else:
                    if wire_type == 1:
                        pos += 8
                    elif wire_type == 5:
                        pos += 4
                    else:
                        break
        except:
            pass
        
        return flags
    
    def _parse_flag_submessage(self, data: bytes, flag_name: str) -> Dict:
        """Parse a flag sub-message (like light, market, etc.)"""
        result = {}
        pos = 0
        
        try:
            while pos < len(data):
                if pos >= len(data):
                    break
                
                tag_byte = data[pos]
                pos += 1
                
                field_number = tag_byte >> 3
                wire_type = tag_byte & 0x07
                
                value = None
                str_value = None
                
                if wire_type == 0:
                    value, bytes_read = self._read_varint(data, pos)
                    pos += bytes_read
                elif wire_type == 2:
                    length, bytes_read = self._read_varint(data, pos)
                    pos += bytes_read
                    if pos + length <= len(data):
                        str_value = data[pos:pos+length].decode('utf-8', errors='ignore')
                    pos += length
                elif wire_type == 1:
                    pos += 8
                elif wire_type == 5:
                    pos += 4
                    
                # Store with meaningful names if possible
                key = f'field_{field_number}'
                
                if flag_name == 'light':
                    if field_number == 1: key = 'brightness'
                    elif field_number == 2: key = 'color'
                elif flag_name == 'market':
                    if field_number == 1: key = 'category'
                    elif field_number == 2: key = 'trade_as_object_id'
                    elif field_number == 3: key = 'show_as_object_id'
                    elif field_number == 4: key = 'name'
                    elif field_number == 5: key = 'restrict_to_vocation'
                    elif field_number == 6: key = 'minimum_level'
                elif flag_name == 'upgradeclassification':
                    if field_number == 1: key = 'upgrade_classification'
                
                if str_value is not None:
                    result[key] = str_value
                elif value is not None:
                    result[key] = value
                    
        except:
            pass
        
        return result
    
    def _read_varint(self, data: bytes, pos: int) -> Tuple[int, int]:
        """Read a varint and return (value, bytes_read)"""
        result = 0
        shift = 0
        bytes_read = 0
        
        while pos + bytes_read < len(data):
            byte = data[pos + bytes_read]
            result |= (byte & 0x7F) << shift
            bytes_read += 1
            
            if (byte & 0x80) == 0:
                break
            shift += 7
        
        return result, bytes_read


# ==================== WIKI IMPORTER ====================

class WikiImporter(QThread):
    """Background thread for importing data from TibiaWiki"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)
    
    def __init__(self, url: str):
        super().__init__()
        self.url = url
    
    def run(self):
        try:
            import requests
            from bs4 import BeautifulSoup
            
            self.log_signal.emit(f"🌐 Accessing {self.url}...")
            
            if CLOUDSCRAPER_AVAILABLE:
                self.log_signal.emit("🛡️ Using CloudScraper to bypass protection...")
                scraper = cloudscraper.create_scraper()
                response = scraper.get(self.url)
            else:
                # Use more robust headers to avoid 403 Forbidden
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Referer': 'https://www.google.com/',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'cross-site',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                }
                
                session = requests.Session()
                response = session.get(self.url, headers=headers, timeout=30)
            
            if response.status_code == 403:
                self.log_signal.emit("⚠️ 403 Forbidden received. Trying alternative method...")
                # Fallback handled by cloudscraper usually, but if requests failed:
                if not CLOUDSCRAPER_AVAILABLE:
                     self.error_signal.emit("Error 403: Cloudflare prevented access. Please install cloudscraper.")
                     return
                pass
                
            response.raise_for_status()
            
            self.log_signal.emit("📄 Parsing HTML...")
            soup = BeautifulSoup(response.content, 'html.parser')
            
            items = []
            
            # Find tables with item data
            tables = soup.find_all('table', {'class': ['wikitable', 'sortable']})
            
            total_tables = len(tables)
            for idx, table in enumerate(tables):
                self.progress_signal.emit(int((idx / max(total_tables, 1)) * 100))
                
                # Check table headers to identify content type
                headers_row = table.find('tr')
                if not headers_row:
                    continue
                    
                headers_text = ' '.join([th.get_text(strip=True).lower() for th in headers_row.find_all(['th', 'td'])])
                
                # Skip Creature tables
                if any(x in headers_text for x in ['hitpoints', 'hp', 'experience', 'summon', 'abilities', 'bestiary']):
                    self.log_signal.emit(f"  ⏭️ Skipping Creature table...")
                    continue
                    
                # Skip Spell tables
                if any(x in headers_text for x in ['mana', 'spell', 'vocation', 'group', 'cooldown']):
                    # Check if it's really a spell table (some items might mention vocation)
                    # Spell tables usually have "Mana" and "Spell" or "Group"
                    if 'mana' in headers_text or 'spell' in headers_text:
                         self.log_signal.emit(f"  ⏭️ Skipping Spell table...")
                         continue

                # Skip NPC/Mount/Outfit tables if they lack item stats
                # (Optional: refine this if user wants outfits?) 
                # User asked for ITEMS. Outfits usually don't have weight/arm/def.
                
                rows = table.find_all('tr')[1:]  # Skip header
                
                for row in rows:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) < 2:
                        continue
                    
                    item = self._extract_item_from_row(cols)
                    if item and item.get('name'):
                        items.append(item)
                        self.log_signal.emit(f"  ✓ {item['name']}")
            
            self.progress_signal.emit(100)
            self.log_signal.emit(f"\n✅ Extracted {len(items)} items")
            self.finished_signal.emit(items)
            
        except ImportError as e:
            self.error_signal.emit(f"Missing dependency: {e}\nRun: pip install requests beautifulsoup4")
        except Exception as e:
            self.error_signal.emit(f"Error: {e}")
    
    def _extract_item_from_row(self, cols) -> Optional[Dict]:
        """Extract item data from a table row"""
        try:
            item = {}
            
            # First column usually has item name (possibly with link)
            name_col = cols[0]
            link = name_col.find('a')
            if link:
                item['name'] = link.get_text(strip=True)
            else:
                item['name'] = name_col.get_text(strip=True)
            
            # Skip empty names
            if not item['name'] or item['name'] in ['?', '-', '']:
                return None
            
            # --- FILTERING LOGIC ---
            # User wants ITEMS only, not Monsters or Spells.
            
            # 1. Check for Monster attributes (HP, Exp)
            # Monsters tables usually have columns for Hitpoints, Experience, etc.
            # If the row text contains "Exp:" or "Hitpoints", likely a monster.
            full_text = ' '.join([c.get_text() for c in cols]).lower()
            
            if "hitpoints" in full_text or "experience" in full_text or "summon cost" in full_text:
                return None
            
            # 2. Check for Spell attributes (Mana, Level, Group)
            # Spells on update pages usually appear in separate tables, but if mixed:
            # Check for "Mana:" or check if it lacks "oz" (weight). Most items have weight.
            # However some items don't have weight listed in summary tables.
            # Let's rely on positive identification of Item attributes.
            
            # Exclude known non-item keywords
            if "creature" in full_text or "spell" in full_text:
                 # Be careful, "Spellbook" is an item.
                 if "spell" in full_text and "spellbook" not in item['name'].lower():
                     return None

            # 3. Ensure it looks like an item
            # Items usually have weight ("oz"), or slot type, or specific stats.
            # We can check if we successfully parsed ANY item stat.
            has_item_stats = False
            
            # Try to extract weight from text
            # Weight pattern: "X.XX oz" or "X oz"
            weight_match = re.search(r'(\d+\.?\d*)\s*oz', full_text, re.IGNORECASE)
            if weight_match:
                item['weight'] = weight_match.group(1)
                has_item_stats = True
            
            # Level requirement pattern: "Level X" or "Lvl. X"
            level_match = re.search(r'(?:level|lvl\.?)\s*(\d+)', full_text, re.IGNORECASE)
            if level_match:
                item['level'] = level_match.group(1)
            
            # Armor/Defense pattern
            armor_match = re.search(r'Arm[:\s]*(\d+)', full_text, re.IGNORECASE)
            if armor_match:
                item['armor'] = armor_match.group(1)
            
            defense_match = re.search(r'Def[:\s]*(\d+)', full_text, re.IGNORECASE)
            if defense_match:
                item['defense'] = defense_match.group(1)
            
            attack_match = re.search(r'Atk[:\s]*(\d+)', full_text, re.IGNORECASE)
            if attack_match:
                item['attack'] = attack_match.group(1)
                
            # Tier / Classification
            # Matches "Tier: 4" or just column "Tier" with value "4"
            tier_match = re.search(r'Tier[:\s]*(\d+)', full_text, re.IGNORECASE)
            if tier_match:
                item['upgradeClassification'] = tier_match.group(1)
            else:
                 # Try matching just digit if column header was checked?
                 # Since we look at full_text, headers matter.
                 pass

            # Imbuements / Slots
            slots_match = re.search(r'(?:Slots|Imbuements?)[:\s]*(\d+)', full_text, re.IGNORECASE)
            if slots_match:
                item['imbuementSlots'] = slots_match.group(1)
            
            return item
            
        except Exception:
            return None


# ==================== MAIN WIDGET ====================

class AssetsEditorTab(QWidget):
    """Main Assets Editor tab for ItemManager"""
    
    def __init__(self):
        super().__init__()
        
        self.assets_path = ""
        self.catalog: List[CatalogEntry] = []
        self.parser = AppearancesParser()
        self.sprite_cache: Dict[str, Image.Image] = {}  # Cache for sprite sheets
        self.xml_items: Dict[int, Dict[str, Any]] = {}  # Storage for items.xml data
        self.current_item: Optional[AppearanceData] = None
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Header
        header = QLabel("🎮 Assets Editor (Tibia 12+)")
        header.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #4a90e2;
            padding: 5px;
        """)
        main_layout.addWidget(header)
        
        # Create splitter for main content
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # === LEFT PANEL: Load & Lists ===
        left_panel = QFrame()
        left_panel.setStyleSheet("""
            QFrame {
                background: rgba(22, 33, 62, 0.6);
                border: 1px solid rgba(74, 144, 226, 0.2);
                border-radius: 8px;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        
        # Load Assets Section
        load_group = QGroupBox("📁 Load Assets")
        load_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                color: #4a90e2;
                border: 1px solid rgba(74, 144, 226, 0.3);
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        load_layout = QVBoxLayout(load_group)
        
        self.path_label = QLabel("No folder selected")
        self.path_label.setStyleSheet("color: #888; font-size: 11px;")
        self.path_label.setWordWrap(True)
        load_layout.addWidget(self.path_label)
        
        btn_select = QPushButton("📂 Select Assets Folder")
        btn_select.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a7bc8;
            }
        """)
        btn_select.clicked.connect(self.select_assets_folder)
        load_layout.addWidget(btn_select)
        
        # Stats display
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #28a745; font-size: 11px;")
        load_layout.addWidget(self.stats_label)
        
        left_layout.addWidget(load_group)
        
        # Category Tabs
        self.category_tabs = QTabWidget()
        self.category_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid rgba(74, 144, 226, 0.3);
                border-radius: 4px;
            }
            QTabBar::tab {
                background: rgba(74, 144, 226, 0.1);
                color: #ccc;
                padding: 6px 12px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: rgba(74, 144, 226, 0.3);
                color: white;
            }
        """)
        
        # Create list widgets for each category
        self.objects_list = QListWidget()
        self.outfits_list = QListWidget()
        self.effects_list = QListWidget()
        self.missiles_list = QListWidget()
        
        for lst in [self.objects_list, self.outfits_list, self.effects_list, self.missiles_list]:
            lst.setStyleSheet("""
                QListWidget {
                    background: rgba(0, 0, 0, 0.3);
                    border: none;
                    color: white;
                }
                QListWidget::item:selected {
                    background: rgba(74, 144, 226, 0.4);
                }
                QListWidget::item:hover {
                    background: rgba(74, 144, 226, 0.2);
                }
            """)
            lst.itemClicked.connect(self.on_item_selected)
        
        self.category_tabs.addTab(self.objects_list, f"📦 Objects (0)")
        self.category_tabs.addTab(self.outfits_list, f"👤 Outfits (0)")
        self.category_tabs.addTab(self.effects_list, f"✨ Effects (0)")
        self.category_tabs.addTab(self.missiles_list, f"🎯 Missiles (0)")
        
        left_layout.addWidget(self.category_tabs)
        
        # Search box
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search by ID or name...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(74, 144, 226, 0.3);
                border-radius: 4px;
                color: white;
                padding: 6px;
            }
        """)
        self.search_input.textChanged.connect(self.filter_items)
        search_layout.addWidget(self.search_input)
        left_layout.addLayout(search_layout)
        
        splitter.addWidget(left_panel)
        
        # === RIGHT PANEL: Preview & Properties ===
        right_panel = QFrame()
        right_panel.setStyleSheet("""
            QFrame {
                background: rgba(22, 33, 62, 0.6);
                border: 1px solid rgba(74, 144, 226, 0.2);
                border-radius: 8px;
            }
        """)
        right_layout = QVBoxLayout(right_panel)
        
        # Preview Section
        preview_group = QGroupBox("🖼️ Preview")
        preview_group.setStyleSheet(load_group.styleSheet())
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(128, 128)
        self.preview_label.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.5);
                border: 2px solid rgba(74, 144, 226, 0.3);
                border-radius: 8px;
            }
        """)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.preview_label, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.item_info_label = QLabel("Select an item")
        self.item_info_label.setStyleSheet("color: #888; font-size: 12px;")
        self.item_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.item_info_label)
        
        right_layout.addWidget(preview_group)
        
        # Properties Section
        props_group = QGroupBox("⚙️ Properties")
        props_group.setStyleSheet(load_group.styleSheet())
        props_scroll = QScrollArea()
        props_scroll.setWidgetResizable(True)
        props_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.props_widget = QWidget()
        self.props_layout = QVBoxLayout(self.props_widget)
        self.props_layout.setSpacing(4)
        props_scroll.setWidget(self.props_widget)
        
        props_main_layout = QVBoxLayout(props_group)
        props_main_layout.addWidget(props_scroll)
        
        right_layout.addWidget(props_group)
        
        splitter.addWidget(right_panel)
        
        # Set splitter proportions
        splitter.setSizes([350, 450])
        main_layout.addWidget(splitter)
        
        # === BOTTOM: Wiki Importer ===
        wiki_group = QGroupBox("🌐 Wiki Importer - Generate items.xml")
        wiki_group.setStyleSheet(load_group.styleSheet())
        wiki_layout = QVBoxLayout(wiki_group)
        
        wiki_url_layout = QHBoxLayout()
        wiki_url_layout.addWidget(QLabel("URL:"))
        self.wiki_url_input = QLineEdit()
        self.wiki_url_input.setPlaceholderText("https://tibia.fandom.com/wiki/Updates/...")
        self.wiki_url_input.setStyleSheet(self.search_input.styleSheet())
        wiki_url_layout.addWidget(self.wiki_url_input)
        
        btn_extract = QPushButton("🔄 Extract & Generate")
        btn_extract.setStyleSheet(btn_select.styleSheet())
        btn_extract.clicked.connect(self.extract_from_wiki)
        wiki_url_layout.addWidget(btn_extract)
        
        wiki_layout.addLayout(wiki_url_layout)
        
        self.wiki_progress = QProgressBar()
        self.wiki_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(74, 144, 226, 0.3);
                border-radius: 4px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background: #4a90e2;
            }
        """)
        self.wiki_progress.setVisible(False)
        wiki_layout.addWidget(self.wiki_progress)
        
        self.wiki_log = QTextEdit()
        self.wiki_log.setReadOnly(True)
        self.wiki_log.setMaximumHeight(120)
        self.wiki_log.setStyleSheet("""
            QTextEdit {
                background: rgba(0, 0, 0, 0.3);
                border: 1px solid rgba(74, 144, 226, 0.2);
                border-radius: 4px;
                color: #ccc;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
        """)
        wiki_layout.addWidget(self.wiki_log)
        
        main_layout.addWidget(wiki_group)
    
    def select_assets_folder(self):
        """Open folder dialog to select assets folder"""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Tibia Assets Folder",
            options=QFileDialog.Option.ShowDirsOnly
        )
        
        if not folder:
            return
        
        self.assets_path = folder
        self.path_label.setText(folder)
        
        # Check for catalog-content.json
        catalog_path = os.path.join(folder, "catalog-content.json")
        has_catalog = os.path.exists(catalog_path)
        
        # Check for appearances.dat directly (fallback if catalog missing)
        appearances_file = os.path.join(folder, "appearances.dat")
        has_appearances = os.path.exists(appearances_file)
        
        if not has_catalog and not has_appearances:
            QMessageBox.critical(
                self, "Error",
                "Neither catalog-content.json nor appearances.dat found!\n\n"
                "Please select a valid Tibia 12+ assets folder."
            )
            return
            
        success = False
        
        if has_catalog:
            # Load catalog
            if self.load_catalog(catalog_path):
                # Find and load appearances.dat via catalog
                for entry in self.catalog:
                    if entry.type == 'appearances':
                        appearances_file = os.path.join(folder, entry.file)
                        break
                
                if appearances_file and os.path.exists(appearances_file):
                    if self.parser.parse(appearances_file):
                        success = True
        elif has_appearances:
             # Fallback: Load appearances directly without catalog
             # We won't have sprite sheet mapping from catalog, but we can load sprites if they follow standard naming
             # or just show appearances data
             if self.parser.parse(appearances_file):
                 success = True
                 self.catalog = [] # No catalog available
                 # Try to infer sprite sheets? Tibia 12 uses hashed names. 
                 # Without catalog, we might not find sprites easily.
        
        if success:
            self.populate_lists()
            
            # Load items.xml if available
            self.load_items_xml(folder)
            
            self.stats_label.setText(
                f"✓ Objects: {len(self.parser.objects)} | "
                f"Outfits: {len(self.parser.outfits)} | "
                f"Effects: {len(self.parser.effects)} | "
                f"Missiles: {len(self.parser.missiles)}"
            )
            
            msg = f"Assets loaded successfully!\n\n" \
                  f"Objects: {len(self.parser.objects)}\n" \
                  f"Outfits: {len(self.parser.outfits)}\n" \
                  f"Effects: {len(self.parser.effects)}\n" \
                  f"Missiles: {len(self.parser.missiles)}"
            
            if self.xml_items:
                msg += f"\n\nLoaded {len(self.xml_items)} items from items.xml"
                
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.critical(self, "Error", "Failed to parse appearances.dat!")
    
    def load_items_xml(self, folder: str):
        """Try to load items.xml from the assets folder"""
        self.xml_items = {}
        xml_path = os.path.join(folder, "items.xml")
        
        if not os.path.exists(xml_path):
            # Try items.otb? No, OTB is binary. items.xml is standard.
            return
            
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            for item_node in root.findall('item'):
                try:
                    # Get ID
                    id_attr = item_node.get('id')
                    from_id = item_node.get('fromid')
                    to_id = item_node.get('toid')
                    
                    ids = []
                    if id_attr:
                        ids.append(int(id_attr))
                    elif from_id and to_id:
                        ids.extend(range(int(from_id), int(to_id) + 1))
                    
                    # Get attributes
                    attrs = {}
                    for attr_node in item_node.findall('attribute'):
                        key = attr_node.get('key')
                        val = attr_node.get('value')
                        if key:
                            attrs[key] = val
                    
                    # Store
                    name = item_node.get('name')
                    
                    for item_id in ids:
                        self.xml_items[item_id] = {
                            'name': name,
                            'attributes': attrs
                        }
                        
                except (ValueError, TypeError):
                    continue
                    
        except Exception as e:
            print(f"Error loading items.xml: {e}")
    
    def load_catalog(self, path: str) -> bool:
        """Load catalog-content.json"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.catalog = []
            for entry in data:
                cat = CatalogEntry(
                    file=entry.get('file', ''),
                    type=entry.get('type', ''),
                    sprite_type=entry.get('spritetype', 0),
                    first_sprite_id=entry.get('firstspriteid', 0),
                    last_sprite_id=entry.get('lastspriteid', 0),
                    area=entry.get('area', 0),
                    version=entry.get('version', 0)
                )
                self.catalog.append(cat)
            
            return True
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load catalog:\n{e}")
            return False
    
    def populate_lists(self):
        """Populate list widgets with parsed appearances"""
        self.objects_list.clear()
        self.outfits_list.clear()
        self.effects_list.clear()
        self.missiles_list.clear()
        
        for obj in self.parser.objects:
            name = obj.name if obj.name else f"Object {obj.id}"
            item = QListWidgetItem(f"[{obj.id}] {name}")
            item.setData(Qt.ItemDataRole.UserRole, obj)
            self.objects_list.addItem(item)
        
        for outfit in self.parser.outfits:
            name = outfit.name if outfit.name else f"Outfit {outfit.id}"
            item = QListWidgetItem(f"[{outfit.id}] {name}")
            item.setData(Qt.ItemDataRole.UserRole, outfit)
            self.outfits_list.addItem(item)
        
        for effect in self.parser.effects:
            name = effect.name if effect.name else f"Effect {effect.id}"
            item = QListWidgetItem(f"[{effect.id}] {name}")
            item.setData(Qt.ItemDataRole.UserRole, effect)
            self.effects_list.addItem(item)
        
        for missile in self.parser.missiles:
            name = missile.name if missile.name else f"Missile {missile.id}"
            item = QListWidgetItem(f"[{missile.id}] {name}")
            item.setData(Qt.ItemDataRole.UserRole, missile)
            self.missiles_list.addItem(item)
        
        # Update tab titles
        self.category_tabs.setTabText(0, f"📦 Objects ({len(self.parser.objects)})")
        self.category_tabs.setTabText(1, f"👤 Outfits ({len(self.parser.outfits)})")
        self.category_tabs.setTabText(2, f"✨ Effects ({len(self.parser.effects)})")
        self.category_tabs.setTabText(3, f"🎯 Missiles ({len(self.parser.missiles)})")
    
    def filter_items(self, text: str):
        """Filter items in current list by search text"""
        text = text.lower()
        current_list = self._get_current_list()
        
        for i in range(current_list.count()):
            item = current_list.item(i)
            app_data = item.data(Qt.ItemDataRole.UserRole)
            
            # Match by ID or name
            matches = (
                text in str(app_data.id) or
                text in app_data.name.lower()
            )
            item.setHidden(not matches)
    
    def _get_current_list(self) -> QListWidget:
        """Get the currently active list widget"""
        idx = self.category_tabs.currentIndex()
        return [self.objects_list, self.outfits_list, self.effects_list, self.missiles_list][idx]
    
    def on_item_selected(self, item: QListWidgetItem):
        """Handle item selection"""
        app_data = item.data(Qt.ItemDataRole.UserRole)
        if not app_data:
            return
        
        self.current_item = app_data
        
        # Update info label
        self.item_info_label.setText(
            f"ID: {app_data.id}\n"
            f"Name: {app_data.name or 'N/A'}\n"
            f"Sprites: {len(app_data.sprite_ids)}"
        )
        
        # Try to load and display sprite
        if app_data.sprite_ids:
            self.display_sprite(app_data.sprite_ids[0])
        
        # Update properties panel
        self.update_properties_panel(app_data)
    
    def display_sprite(self, sprite_id: int):
        """Display a sprite by its ID"""
        # Find the sprite sheet containing this sprite
        for entry in self.catalog:
            if entry.type == 'sprite':
                if entry.first_sprite_id <= sprite_id <= entry.last_sprite_id:
                    sprite = self.get_sprite_from_sheet(entry, sprite_id)
                    if sprite:
                        # Convert PIL Image to QPixmap
                        self.show_pil_image(sprite)
                    return
        
        self.preview_label.setText("Sprite\nNot Found")
    
    def get_sprite_from_sheet(self, entry: CatalogEntry, sprite_id: int) -> Optional[Image.Image]:
        """Extract a sprite from a sprite sheet"""
        sheet_path = os.path.join(self.assets_path, entry.file)
        
        if sheet_path not in self.sprite_cache:
            # Decompress and cache the sheet
            sheet = LZMAHandler.decompress_tibia_lzma(sheet_path)
            if sheet:
                self.sprite_cache[sheet_path] = sheet
            else:
                return None
        
        sheet = self.sprite_cache.get(sheet_path)
        if not sheet:
            return None
        
        # Calculate sprite position
        sprite_index = sprite_id - entry.first_sprite_id
        cols = sheet.width // 32
        
        if cols == 0:
            return None
        
        x = (sprite_index % cols) * 32
        y = (sprite_index // cols) * 32
        
        # Crop sprite
        try:
            sprite = sheet.crop((x, y, x + 32, y + 32))
            return sprite
        except:
            return None
    
    def show_pil_image(self, img: Image.Image):
        """Convert PIL Image to QPixmap and display"""
        try:
            # Resize for better visibility
            display_size = 96
            img_resized = img.resize((display_size, display_size), Image.Resampling.NEAREST)
            
            # Convert to QImage
            if img_resized.mode == 'RGBA':
                data = img_resized.tobytes('raw', 'RGBA')
                qimg = QImage(data, display_size, display_size, QImage.Format.Format_RGBA8888)
            else:
                img_resized = img_resized.convert('RGBA')
                data = img_resized.tobytes('raw', 'RGBA')
                qimg = QImage(data, display_size, display_size, QImage.Format.Format_RGBA8888)
            
            pixmap = QPixmap.fromImage(qimg)
            self.preview_label.setPixmap(pixmap)
            
        except Exception as e:
            self.preview_label.setText(f"Error:\n{e}")
    
    def update_properties_panel(self, app_data: AppearanceData):
        """Update the properties panel with item flags"""
        # Clear existing properties
        while self.props_layout.count():
            child = self.props_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        if not app_data.flags and (not self.xml_items or app_data.id not in self.xml_items):
            self.props_layout.addWidget(QLabel("No properties available"))
            return
        
        # Display XML items attributes first if available
        if self.xml_items and app_data.id in self.xml_items:
            xml_data = self.xml_items[app_data.id]
            
            lbl = QLabel("📜 items.xml Data:")
            lbl.setStyleSheet("color: #F39C12; font-weight: bold; margin-top: 5px;")
            self.props_layout.addWidget(lbl)
            
            if xml_data.get('name'):
                 self.props_layout.addWidget(QLabel(f"Name: {xml_data.get('name')}"))
            
            if xml_data.get('attributes'):
                for key, val in xml_data['attributes'].items():
                    self.props_layout.addWidget(QLabel(f"• {key}: {val}"))
            
            self.props_layout.addWidget(QLabel("")) # Spacer
            
            lbl2 = QLabel("🚩 Appearance Flags:")
            lbl2.setStyleSheet("color: #4a90e2; font-weight: bold; margin-top: 5px;")
            self.props_layout.addWidget(lbl2)
        
        # Add flag checkboxes
        for flag_name, flag_value in app_data.flags.items():
            if isinstance(flag_value, bool):
                cb = QCheckBox(flag_name.replace('_', ' ').title())
                cb.setChecked(flag_value)
                cb.setEnabled(False)  # Read-only for now
                cb.setStyleSheet("color: white;")
                self.props_layout.addWidget(cb)
            elif isinstance(flag_value, dict):
                # Complex flag with sub-properties
                label = QLabel(f"• {flag_name.replace('_', ' ').title()}:")
                label.setStyleSheet("color: #4a90e2; font-weight: bold;")
                self.props_layout.addWidget(label)
                
                for sub_key, sub_val in flag_value.items():
                    sub_label = QLabel(f"    {sub_key}: {sub_val}")
                    sub_label.setStyleSheet("color: #ccc;")
                    self.props_layout.addWidget(sub_label)
            else:
                label = QLabel(f"• {flag_name}: {flag_value}")
                label.setStyleSheet("color: white;")
                self.props_layout.addWidget(label)
        
        self.props_layout.addStretch()
    
    def extract_from_wiki(self):
        """Start wiki extraction in background thread"""
        url = self.wiki_url_input.text().strip()
        
        if not url:
            QMessageBox.warning(self, "Warning", "Please enter a valid Wiki URL!")
            return
        
        self.wiki_log.clear()
        self.wiki_progress.setVisible(True)
        self.wiki_progress.setValue(0)
        
        self.wiki_importer = WikiImporter(url)
        self.wiki_importer.log_signal.connect(self._wiki_log)
        self.wiki_importer.progress_signal.connect(self.wiki_progress.setValue)
        self.wiki_importer.finished_signal.connect(self._wiki_finished)
        self.wiki_importer.error_signal.connect(self._wiki_error)
        self.wiki_importer.start()
    
    def _wiki_log(self, msg: str):
        self.wiki_log.append(msg)
    
    def _wiki_error(self, msg: str):
        self.wiki_progress.setVisible(False)
        self.wiki_log.append(f"\n❌ {msg}")
        QMessageBox.critical(self, "Error", msg)
    
    def _wiki_finished(self, items: List[Dict]):
        """Handle wiki import completion"""
        self.wiki_progress.setVisible(False)
        
        if not items:
            self.wiki_log.append("No items found to export.")
            return
        
        # Generate items.xml
        self.generate_items_xml(items)
    
    def generate_items_xml(self, items: List[Dict]):
        """Generate items.xml from extracted wiki data"""
        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save items.xml",
            "items.xml", "XML Files (*.xml)"
        )
        
        if not output_path:
            return
        
        try:
            lines = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<items>'
            ]
            
            for item_data in items:
                # Try to find matching item ID in appearances
                item_id = self.find_item_id_by_name(item_data.get('name', ''))
                
                if not item_id:
                    self.wiki_log.append(f"⚠️ No ID found for: {item_data.get('name')}")
                    continue
                
                name = item_data.get('name', '').replace('"', '&quot;')
                lines.append(f'  <item id="{item_id}" name="{name}">')
                
                # Add attributes
                # Dictionary to store attributes (prioritize wiki data, fill missing from xml)
                attributes = {}
                
                # Pre-fill from existing XML if available and we want to preserve unknown attrs
                if self.xml_items and item_id in self.xml_items:
                    attributes.update(self.xml_items[item_id].get('attributes', {}))
                
                # Update/Overwrite with Wiki data
                if item_data.get('weight'):
                    attributes['weight'] = str(int(float(item_data['weight']) * 100))
                
                if item_data.get('armor'):
                    attributes['armor'] = str(item_data['armor'])
                
                if item_data.get('defense'):
                    attributes['defense'] = str(item_data['defense'])
                
                if item_data.get('attack'):
                    attributes['attack'] = str(item_data['attack'])
                
                if item_data.get('level'):
                    attributes['levelRequirement'] = str(item_data['level'])
                
                if item_data.get('upgradeClassification'):
                    attributes['upgradeClassification'] = str(item_data['upgradeClassification'])
                
                if item_data.get('imbuementSlots'):
                    attributes['imbuementSlots'] = str(item_data['imbuementSlots'])
                
                # Map appearance flags to attributes (don't overwrite if likely static, but flags are ground truth for behavior)
                app = self.get_appearance_by_id(item_id)
                if app and app.flags:
                    flag_attrs_list = self.map_flags_to_attributes(app.flags)
                    # Convert list of XML strings back to dict for merging? 
                    # Actually map_flags_to_attributes returns list of strings.
                    # We should append them? Or parsing them?
                    # Let's just append flag attributes at the end, but avoid duplicates of keys we processed?
                    # Flags usually map to specific keys like 'pickupable', 'rotatable'. Wiki maps to 'armor', 'attack'.
                    # Overlap is rare (maybe weight?). 
                    # Let's stick to appending flag attributes directly as they are generated from proto (binary truth).
                    pass

                # Write standard attributes
                for key, val in attributes.items():
                    lines.append(f'    <attribute key="{key}" value="{val}" />')

                # Append flag-derived attributes
                if app and app.flags:
                    flag_attrs = self.map_flags_to_attributes(app.flags)
                    lines.extend(flag_attrs)
                
                lines.append('  </item>')
            
            lines.append('</items>')
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            self.wiki_log.append(f"\n✅ Generated: {output_path}")
            QMessageBox.information(self, "Success", f"items.xml generated!\n\n{output_path}")
            
        except Exception as e:
            self.wiki_log.append(f"\n❌ Error generating XML: {e}")
            QMessageBox.critical(self, "Error", f"Failed to generate items.xml:\n{e}")
    
    def find_item_id_by_name(self, name: str) -> Optional[int]:
        """Find item ID by name in parsed appearances"""
        name_lower = name.lower()
        
        for obj in self.parser.objects:
            if obj.name and obj.name.lower() == name_lower:
                return obj.id
        
        # Fuzzy match
        for obj in self.parser.objects:
            if obj.name and name_lower in obj.name.lower():
                return obj.id
        
        return None
    
    def get_appearance_by_id(self, item_id: int) -> Optional[AppearanceData]:
        """Get appearance data by ID"""
        for obj in self.parser.objects:
            if obj.id == item_id:
                return obj
        return None
    
    def map_flags_to_attributes(self, flags: Dict) -> List[str]:
        """Map appearance flags to items.xml attributes"""
        attrs = []
        
        if flags.get('container'):
            attrs.append('    <attribute key="containerSize" value="8" />')
        
        if flags.get('cumulative'):
            attrs.append('    <attribute key="stackable" value="1" />')
        
        if flags.get('take'):
            attrs.append('    <attribute key="pickupable" value="1" />')
        
        if flags.get('unpass'):
            attrs.append('    <attribute key="blockSolid" value="1" />')
        
        if flags.get('unmove'):
            attrs.append('    <attribute key="moveable" value="0" />')
        
        if flags.get('hang'):
            attrs.append('    <attribute key="hangable" value="1" />')
        
        if flags.get('rotate'):
            attrs.append('    <attribute key="rotatable" value="1" />')
        
        if flags.get('expiration'):
             attrs.append('    <attribute key="expire" value="1" />')
             
        if flags.get('wearout'):
             attrs.append('    <attribute key="showcharges" value="1" />')
             
        # Handle Upgrade Classification
        upgrade = flags.get('upgradeclassification')
        if isinstance(upgrade, dict):
            val = upgrade.get('upgrade_classification') or upgrade.get('field_1')
            if val:
                attrs.append(f'    <attribute key="upgradeClassification" value="{val}" />')
        
        # Handle Market
        market = flags.get('market')
        if isinstance(market, dict):
             category = market.get('category') or market.get('field_1')
             if category:
                 attrs.append(f'    <attribute key="marketCategory" value="{category}" />')
                 
             trade_id = market.get('trade_as_object_id') or market.get('field_2')
             if trade_id:
                  attrs.append(f'    <attribute key="tradeAs" value="{trade_id}" />')
                  
             show_id = market.get('show_as_object_id') or market.get('field_3')
             if show_id:
                  attrs.append(f'    <attribute key="showAs" value="{show_id}" />')
                  
             name = market.get('name') or market.get('field_4')
             if name:
                  attrs.append(f'    <attribute key="marketName" value="{name}" />')
        
        light = flags.get('light')
        if isinstance(light, dict):
            brightness = light.get('brightness') or light.get('field_1', 0)
            color = light.get('color') or light.get('field_2', 0)
            if brightness:
                attrs.append(f'    <attribute key="lightLevel" value="{brightness}" />')
            if color:
                attrs.append(f'    <attribute key="lightColor" value="{color}" />')
        
        return attrs
