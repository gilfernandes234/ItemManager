import struct
import io
import os

# Constants
NODE_START = 0xFE
NODE_END = 0xFF
ESCAPE = 0xFD

# Root Attributes
ROOT_ATTR_VERSION = 0x01

# Item Attributes (Server Side, 8.60+)
ITEM_ATTR_SERVER_ID = 16
ITEM_ATTR_CLIENT_ID = 17
ITEM_ATTR_NAME = 18
ITEM_ATTR_DESCR = 19
ITEM_ATTR_SPEED = 20
ITEM_ATTR_SLOT = 21
ITEM_ATTR_MAXITEMS = 22
ITEM_ATTR_WEIGHT = 23
ITEM_ATTR_WEAPON = 24
ITEM_ATTR_AMMUNITION = 25
ITEM_ATTR_ARMOR = 26
ITEM_ATTR_MAGICLEVEL = 27
ITEM_ATTR_MAGICFIELD = 28
ITEM_ATTR_WRITABLE = 29
ITEM_ATTR_ROTATETO = 30
ITEM_ATTR_DECAY = 31
ITEM_ATTR_SPRITEHASH = 32
ITEM_ATTR_MINIMAPCOLOR = 33
ITEM_ATTR_07 = 34
ITEM_ATTR_08 = 35
ITEM_ATTR_LIGHT = 42 # Corrected 0x2A
ITEM_ATTR_DECAY2 = 37
ITEM_ATTR_WEAPON2 = 38
ITEM_ATTR_AMMUNITION2 = 39
ITEM_ATTR_ARMOR2 = 40
ITEM_ATTR_WRITABLE2 = 41
ITEM_ATTR_LIGHT2 = 36
ITEM_ATTR_TOPORDER = 43
ITEM_ATTR_WRITABLE3 = 44
ITEM_ATTR_WAREID = 45 # TradeAs
ITEM_ATTR_UPGRADE_CLASSIFICATION = 53
ITEM_ATTR_WEAROUT = 54
ITEM_ATTR_CLOCKEXPIRE = 55
ITEM_ATTR_EXPIRE = 56
ITEM_ATTR_EXPIRESTOP = 57
ITEM_ATTR_CORPSE = 58
ITEM_ATTR_PLAYERCORPSE = 59
ITEM_ATTR_AMMO = 60
ITEM_ATTR_SHOWOFFSOCKET = 61
ITEM_ATTR_REPORTABLE = 62
ITEM_ATTR_CHANGEDTOEXPIRE = 63
ITEM_ATTR_CYCLOPEDIAITEM = 64

# Virtuals
ITEM_ATTR_ATTACK = 999 
ITEM_ATTR_DEFENSE = 998 

# OTB Tile Flags Header (Not attribute anymore)
OTBM_ATTR_TILE_FLAGS = 3

FLAG_BLOCK_SOLID = 1
FLAG_BLOCK_PROJECTILE = 2
FLAG_BLOCK_PATHFIND = 4
FLAG_HAS_HEIGHT = 8
FLAG_USEABLE = 16
FLAG_PICKUPABLE = 32
FLAG_MOVEABLE = 64
FLAG_STACKABLE = 128
FLAG_FLOORCHANGE_DOWN = 256
FLAG_FLOORCHANGE_NORTH = 512
FLAG_FLOORCHANGE_EAST = 1024
FLAG_FLOORCHANGE_SOUTH = 2048
FLAG_FLOORCHANGE_WEST = 4096
FLAG_ALWAYS_ON_TOP = 8192
FLAG_READABLE = 16384
FLAG_ROTATABLE = 32768
FLAG_HANGABLE = 65536
FLAG_VERTICAL = 131072
FLAG_HORIZONTAL = 262144
FLAG_CANNOT_DECAY = 524288
FLAG_ALLOW_DISTREAD = 1048576
FLAG_UNUSED = 2097152
FLAG_CLIENT_CHARGES = 4194304
FLAG_IGNORE_LOOK = 8388608
FLAG_IS_ANIMATION = 16777216
FLAG_FULL_GROUND = 33554432
FLAG_FORCE_USE = 67108864

class OTBNode:
    def __init__(self, type_byte=0):
        self.type = type_byte
        self.children = []
        self.props = b''
        self.attribs = {}
        self.raw_props = {}

    def add_child(self, child):
        self.children.append(child)

class OTBHandler:
    @staticmethod
    def load(filepath):
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            
            f = io.BytesIO(data)
            
            # Check for 4 bytes signature (usually 0)
            sig = f.read(4)
            if len(sig) < 4: return None
            
            # Start root
            start = f.read(1)
            if not start or start[0] != NODE_START:
                print("Invalid OTB start")
                return None
            
            root = OTBNode()
            root.header = sig # Store original header
            OTBHandler._parse_node_contents(f, root)
            return root
            
        except Exception as e:
            print(f"Error loading OTB: {e}")
            return None

    @staticmethod
    def save(node, filepath):
        try:
            with open(filepath, 'wb') as f:
                # Write signature 4 bytes
                header = getattr(node, 'header', bytes([0, 0, 0, 0]))
                print(f"[OTB Save] Using Header: {header.hex()}")
                f.write(header)
                OTBHandler._write_node(f, node)
        except Exception as e:
            print(f"Error saving OTB: {e}")

    @staticmethod
    def _write_node(f, node):
        f.write(bytes([NODE_START]))
        f.write(bytes([node.type]))
        
        # Write Flags Header (4 bytes)
        flags = node.attribs.get('flags', 0)
        f.write(struct.pack('<I', flags))

        # Re-serialize props
        OTBHandler._serialize_props(node)
        OTBHandler._write_escaped(f, node.props)
        
        for child in node.children:
            OTBHandler._write_node(f, child)
            
        f.write(bytes([NODE_END]))

    @staticmethod
    def _write_escaped(f, data):
        for b in data:
            if b == NODE_START or b == NODE_END or b == ESCAPE:
                f.write(bytes([ESCAPE]))
                f.write(bytes([b]))
            else:
                f.write(bytes([b]))

    @staticmethod
    def _parse_node_contents(f, node):
        # Read type
        type_byte = f.read(1)
        if not type_byte: return
        node.type = type_byte[0]
        
        # KEY FIX: Read FLAGS (4 bytes) immediately after Type
        flags_bytes = f.read(4)
        if len(flags_bytes) < 4:
            node.attribs['flags'] = 0
        else:
            node.attribs['flags'] = struct.unpack('<I', flags_bytes)[0]
        
        buffer = bytearray()
        
        while True:
            byte = f.read(1)
            if not byte: break
            val = byte[0]
            
            if val == NODE_START:
                child = OTBNode()
                node.add_child(child)
                OTBHandler._parse_node_contents(f, child)
            elif val == NODE_END:
                break
            elif val == ESCAPE:
                next_b = f.read(1)
                if next_b:
                    buffer.append(next_b[0])
            else:
                buffer.append(val)
        
        node.props = bytes(buffer)
        OTBHandler._parse_props(node)

    @staticmethod
    def _parse_props(node):
        node.raw_props = {}
        p = io.BytesIO(node.props)
        while True:
            attr_byte = p.read(1)
            if not attr_byte: break
            attr = attr_byte[0]
            
            size_b = p.read(2)
            if len(size_b) < 2: break
            size = struct.unpack('<H', size_b)[0]
            
            data = p.read(size)
            if len(data) < size: break
            
            node.raw_props[attr] = data
            
            try:
                if attr == ITEM_ATTR_SERVER_ID:
                    if len(data) >= 2: node.attribs['serverId'] = struct.unpack('<H', data[:2])[0]
                elif attr == ITEM_ATTR_CLIENT_ID:
                    if len(data) >= 2: node.attribs['clientId'] = struct.unpack('<H', data[:2])[0]
                elif attr == ITEM_ATTR_NAME:
                    node.attribs['name'] = data.decode('latin1', errors='ignore')
                elif attr == ITEM_ATTR_SPEED:
                    if len(data) >= 2: node.attribs['speed'] = struct.unpack('<H', data[:2])[0]
                elif attr == ITEM_ATTR_WEIGHT:
                    if len(data) >= 4: node.attribs['weight'] = struct.unpack('<I', data[:4])[0]
                    elif len(data) >= 2: node.attribs['weight'] = struct.unpack('<H', data[:2])[0]
                elif attr == ITEM_ATTR_ARMOR:
                    if len(data) >= 2: node.attribs['armor'] = struct.unpack('<H', data[:2])[0]
                elif attr == ITEM_ATTR_WEAPON: # Logic for weapon/attack/def
                    if len(data) >= 4: 
                        node.attribs['attack'] = struct.unpack('<H', data[:2])[0]
                        node.attribs['defense'] = struct.unpack('<H', data[2:4])[0]
                elif attr == ITEM_ATTR_DECAY:
                    if len(data) >= 4:
                        node.attribs['decayTo'] = struct.unpack('<H', data[:2])[0]
                        node.attribs['decayTime'] = struct.unpack('<H', data[2:4])[0]
                elif attr == ITEM_ATTR_LIGHT:
                    if len(data) >= 4:
                        node.attribs['lightLevel'] = struct.unpack('<H', data[:2])[0]
                        node.attribs['lightColor'] = struct.unpack('<H', data[2:4])[0]
                elif attr == ITEM_ATTR_MINIMAPCOLOR:
                    if len(data) >= 2: node.attribs['minimapColor'] = struct.unpack('<H', data[:2])[0]
                elif attr == ITEM_ATTR_WAREID:
                    if len(data) >= 2: node.attribs['wareId'] = struct.unpack('<H', data[:2])[0]
                elif attr == ITEM_ATTR_UPGRADE_CLASSIFICATION:
                    if len(data) >= 1: node.attribs['upgradeClassification'] = data[0]
                
                # 13+ Attributes
                elif attr == ITEM_ATTR_WEAROUT: node.attribs['wearout'] = True
                elif attr == ITEM_ATTR_CLOCKEXPIRE: node.attribs['clockExpire'] = True
                elif attr == ITEM_ATTR_EXPIRE: node.attribs['expire'] = True
                elif attr == ITEM_ATTR_EXPIRESTOP: node.attribs['expireStop'] = True
                elif attr == ITEM_ATTR_CORPSE: node.attribs['corpse'] = True
                elif attr == ITEM_ATTR_PLAYERCORPSE: node.attribs['playerCorpse'] = True
                elif attr == ITEM_ATTR_AMMO: node.attribs['ammo'] = True
                elif attr == ITEM_ATTR_SHOWOFFSOCKET: node.attribs['showOffSocket'] = True
                elif attr == ITEM_ATTR_REPORTABLE: node.attribs['reportable'] = True
                
                elif attr == ITEM_ATTR_CHANGEDTOEXPIRE:
                     if len(data) >= 2: node.attribs['changedToExpire'] = struct.unpack('<H', data[:2])[0]
                elif attr == ITEM_ATTR_CYCLOPEDIAITEM:
                     if len(data) >= 2: node.attribs['cyclopediaItem'] = struct.unpack('<H', data[:2])[0]
                
                elif attr == ROOT_ATTR_VERSION:
                    if len(data) >= 4: node.attribs['majorVersion'] = struct.unpack('<I', data[0:4])[0]
                    if len(data) >= 8: node.attribs['minorVersion'] = struct.unpack('<I', data[4:8])[0]
                    if len(data) >= 12: node.attribs['buildNumber'] = struct.unpack('<I', data[8:12])[0]
                    if len(data) >= 140: node.attribs['csdVersion'] = data[12:140]
                    print(f"[OTB Load] Found Version: {node.attribs.get('majorVersion')}.{node.attribs.get('minorVersion')}.{node.attribs.get('buildNumber')}")
            except: pass

    @staticmethod
    def _serialize_props(node):
        b = bytearray()
        def add_prop(attr, d):
            b.append(attr)
            b.extend(struct.pack('<H', len(d)))
            b.extend(d)

        # 1. Server ID
        if 'serverId' in node.attribs: add_prop(ITEM_ATTR_SERVER_ID, struct.pack('<H', node.attribs['serverId']))
        elif ITEM_ATTR_SERVER_ID in node.raw_props: add_prop(ITEM_ATTR_SERVER_ID, node.raw_props[ITEM_ATTR_SERVER_ID])
        
        # 2. Client ID
        if 'clientId' in node.attribs: add_prop(ITEM_ATTR_CLIENT_ID, struct.pack('<H', node.attribs['clientId']))
        elif ITEM_ATTR_CLIENT_ID in node.raw_props: add_prop(ITEM_ATTR_CLIENT_ID, node.raw_props[ITEM_ATTR_CLIENT_ID])
        
        # 3. Name
        if 'name' in node.attribs: 
            try: add_prop(ITEM_ATTR_NAME, node.attribs['name'].encode('latin1'))
            except: pass
        elif ITEM_ATTR_NAME in node.raw_props: add_prop(ITEM_ATTR_NAME, node.raw_props[ITEM_ATTR_NAME])
        
        # 4. Weight
        if 'weight' in node.attribs: add_prop(ITEM_ATTR_WEIGHT, struct.pack('<I', node.attribs['weight']))
        elif ITEM_ATTR_WEIGHT in node.raw_props: add_prop(ITEM_ATTR_WEIGHT, node.raw_props[ITEM_ATTR_WEIGHT])
        
        # 5. Speed
        if 'speed' in node.attribs: add_prop(ITEM_ATTR_SPEED, struct.pack('<H', node.attribs['speed']))
        elif ITEM_ATTR_SPEED in node.raw_props: add_prop(ITEM_ATTR_SPEED, node.raw_props[ITEM_ATTR_SPEED])
        
        # 6. Armor
        if 'armor' in node.attribs: add_prop(ITEM_ATTR_ARMOR, struct.pack('<H', node.attribs['armor']))
        elif ITEM_ATTR_ARMOR in node.raw_props: add_prop(ITEM_ATTR_ARMOR, node.raw_props[ITEM_ATTR_ARMOR])
        
        # 7. Weapon
        if 'attack' in node.attribs or 'defense' in node.attribs:
            att = node.attribs.get('attack', 0)
            defn = node.attribs.get('defense', 0)
            add_prop(ITEM_ATTR_WEAPON, struct.pack('<HH', att, defn))
        elif ITEM_ATTR_WEAPON in node.raw_props: add_prop(ITEM_ATTR_WEAPON, node.raw_props[ITEM_ATTR_WEAPON])
        
        # 8. Light
        if 'lightLevel' in node.attribs and 'lightColor' in node.attribs:
             add_prop(ITEM_ATTR_LIGHT, struct.pack('<HH', node.attribs['lightLevel'], node.attribs['lightColor']))
        elif ITEM_ATTR_LIGHT in node.raw_props: add_prop(ITEM_ATTR_LIGHT, node.raw_props[ITEM_ATTR_LIGHT])
        
        # 9. Minimap
        if 'minimapColor' in node.attribs: add_prop(ITEM_ATTR_MINIMAPCOLOR, struct.pack('<H', node.attribs['minimapColor']))
        elif ITEM_ATTR_MINIMAPCOLOR in node.raw_props: add_prop(ITEM_ATTR_MINIMAPCOLOR, node.raw_props[ITEM_ATTR_MINIMAPCOLOR])
        
        # 10. Ware ID
        if 'wareId' in node.attribs: add_prop(ITEM_ATTR_WAREID, struct.pack('<H', node.attribs['wareId']))
        elif ITEM_ATTR_WAREID in node.raw_props: add_prop(ITEM_ATTR_WAREID, node.raw_props[ITEM_ATTR_WAREID])
        
        # 11. Upgrade Classification
        if 'upgradeClassification' in node.attribs: add_prop(ITEM_ATTR_UPGRADE_CLASSIFICATION, bytes([node.attribs['upgradeClassification']]))
        elif ITEM_ATTR_UPGRADE_CLASSIFICATION in node.raw_props: add_prop(ITEM_ATTR_UPGRADE_CLASSIFICATION, node.raw_props[ITEM_ATTR_UPGRADE_CLASSIFICATION])
        
        # 13. New 13+ Attributes
        if node.attribs.get('wearout'): add_prop(ITEM_ATTR_WEAROUT, b'')
        if node.attribs.get('clockExpire'): add_prop(ITEM_ATTR_CLOCKEXPIRE, b'')
        if node.attribs.get('expire'): add_prop(ITEM_ATTR_EXPIRE, b'')
        if node.attribs.get('expireStop'): add_prop(ITEM_ATTR_EXPIRESTOP, b'')
        if node.attribs.get('corpse'): add_prop(ITEM_ATTR_CORPSE, b'')
        if node.attribs.get('playerCorpse'): add_prop(ITEM_ATTR_PLAYERCORPSE, b'')
        if node.attribs.get('ammo'): add_prop(ITEM_ATTR_AMMO, b'')
        if node.attribs.get('showOffSocket'): add_prop(ITEM_ATTR_SHOWOFFSOCKET, b'')
        if node.attribs.get('reportable'): add_prop(ITEM_ATTR_REPORTABLE, b'')
        
        if 'changedToExpire' in node.attribs: add_prop(ITEM_ATTR_CHANGEDTOEXPIRE, struct.pack('<H', node.attribs['changedToExpire']))
        if 'cyclopediaItem' in node.attribs: add_prop(ITEM_ATTR_CYCLOPEDIAITEM, struct.pack('<H', node.attribs['cyclopediaItem']))
        
        # 12. Version
        if 'majorVersion' in node.attribs:
            maj = node.attribs.get('majorVersion', 3)
            min_ = node.attribs.get('minorVersion', 0)
            bld = node.attribs.get('buildNumber', 0)
            print(f"[OTB Save] Writing Version: {maj}.{min_}.{bld}")
            
            # Reconstruct standard 140-byte version struct (12 bytes ver + 128 bytes CSD string)
            # Try to retrieve original CSD data if available
            csd = b'\x00' * 128
            if 'csdVersion' in node.attribs:
                csd = node.attribs['csdVersion']
                if len(csd) < 128: csd = csd + b'\x00' * (128 - len(csd))
                elif len(csd) > 128: csd = csd[:128]
            
            # Fallback: check raw_props for CSD tail (offset 12)
            elif ROOT_ATTR_VERSION in node.raw_props and len(node.raw_props[ROOT_ATTR_VERSION]) >= 140:
                csd = node.raw_props[ROOT_ATTR_VERSION][12:140]
            
            b_ver = struct.pack('<III', maj, min_, bld) + csd
            add_prop(ROOT_ATTR_VERSION, b_ver)
            
        elif ROOT_ATTR_VERSION in node.raw_props: 
            print(f"[OTB Save] Preserving Raw Version Attribute")
            add_prop(ROOT_ATTR_VERSION, node.raw_props[ROOT_ATTR_VERSION])
        else:
             # Fallback if this is the Root Node specifically?
             # We can't easily tell if this is root node here without context, 
             # but usually only Root has versions. 
             # Use a heuristic: If it has children and no other attributes?
             pass

        # Others
        handled = [ITEM_ATTR_SERVER_ID, ITEM_ATTR_CLIENT_ID, ITEM_ATTR_NAME, ITEM_ATTR_WEIGHT, 
                   ITEM_ATTR_SPEED, ITEM_ATTR_ARMOR, ITEM_ATTR_WEAPON, ITEM_ATTR_LIGHT, 
                   ITEM_ATTR_MINIMAPCOLOR, ITEM_ATTR_WAREID, ITEM_ATTR_UPGRADE_CLASSIFICATION, ROOT_ATTR_VERSION]
        
        for k, v in node.raw_props.items():
            if k not in handled and k != OTBM_ATTR_TILE_FLAGS: # Flags header handled separately
                add_prop(k, v)
                
        node.props = bytes(b)
