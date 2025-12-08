import zipfile
import xml.etree.ElementTree as ET
import io
import os
from PIL import Image

# Mapeamento de Flags
OBD_MAP = {
    "Ground": ("Ground", int),
    "GroundBorder": ("GroundBorder", bool),
    "OnBottom": ("OnBottom", bool),
    "OnTop": ("OnTop", bool),
    "Container": ("Container", bool),
    "Stackable": ("Stackable", bool),
    "ForceUse": ("ForceUse", bool),
    "MultiUse": ("MultiUse", bool),
    "Writable": ("Writable", int),
    "WritableOnce": ("WritableOnce", int),
    "FluidContainer": ("FluidContainer", bool),
    "IsFluid": ("IsFluid", bool),
    "Unpassable": ("Unpassable", bool),
    "Unmoveable": ("Unmoveable", bool),
    "BlockMissile": ("BlockMissile", bool),
    "BlockPathfind": ("BlockPathfind", bool),
    "NoMoveAnimation": ("NoMoveAnimation", bool),
    "Pickupable": ("Pickupable", bool),
    "Hangable": ("Hangable", bool),
    "HookVertical": ("HookVertical", bool),
    "HookHorizontal": ("HookHorizontal", bool),
    "Rotatable": ("Rotatable", bool),
    "Light": ("HasLight", "light"), 
    "DontHide": ("DontHide", bool),
    "Translucent": ("Translucent", bool),
    "Offset": ("HasOffset", "offset"),
    "Elevation": ("HasElevation", int),
    "LyingObject": ("LyingObject", bool),
    "AnimateAlways": ("AnimateAlways", bool),
    "MinimapColor": ("ShowOnMinimap", int),
    "LensHelp": ("LensHelp", int),
    "FullGround": ("FullGround", bool),
    "IgnoreLook": ("IgnoreLook", bool),
    "Cloth": ("IsCloth", int),
    "Market": ("MarketItem", "market"),
    "DefaultAction": ("DefaultAction", int),
    "Wrappable": ("Wrappable", bool),
    "Unwrappable": ("Unwrappable", bool),
    "TopEffect": ("TopEffect", bool),
}

class ObdHandler:
    @staticmethod
    def load_obd(filepath):
        properties = {}
        images = []
        
        try:
            if not zipfile.is_zipfile(filepath):
                return {}, []

            with zipfile.ZipFile(filepath, 'r') as z:
                # 1. XML
                xml_content = None
                for name in z.namelist():
                    if name.endswith('.xml'):
                        xml_content = z.read(name)
                        break
                
                if xml_content:
                    root = ET.fromstring(xml_content)
                    for attr in root.findall('Attribute'):
                        key = attr.get('key')
                        value = attr.get('value')
                        
                        if key in OBD_MAP:
                            flag_name, flag_type = OBD_MAP[key]
                            if flag_type == bool:
                                properties[flag_name] = True
                            elif flag_type == int:
                                try:
                                    properties[flag_name] = True
                                    properties[flag_name + '_data'] = (int(value),)
                                except: pass
                            elif flag_type == "light" or flag_type == "offset":
                                try:
                                    parts = value.split(',')
                                    properties[flag_name] = True
                                    properties[flag_name + '_data'] = (int(parts[0]), int(parts[1]))
                                except: pass

                # 2. Imagens
                # Filtra apenas PNGs e ordena numericamente (0.png, 1.png, 10.png...)
                # O sort padrão do python ("10.png" < "2.png") causaria erro na ordem da animação
                png_files = [n for n in z.namelist() if n.lower().endswith('.png')]
                
                def get_num(filename):
                    try:
                        name = os.path.basename(filename)
                        return int(os.path.splitext(name)[0])
                    except:
                        return 9999

                png_files.sort(key=get_num)
                
                for img_name in png_files:
                    try:
                        img_data = z.read(img_name)
                        pil_img = Image.open(io.BytesIO(img_data)).convert("RGBA")
                        images.append(pil_img)
                    except Exception as img_err:
                        print(f"Erro lendo imagem {img_name}: {img_err}")
                    
        except Exception as e:
            print(f"Erro fatal load_obd: {e}")
            return {}, []

        return properties, images

    @staticmethod
    def save_obd(filepath, thing_props, images, ob_type="Item"):
        """
        ob_type: "Item", "Outfit", "Effect", "Missile"
        """
        try:
            with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as z:
                # 1. XML
                root = ET.Element("Object")
                root.set("type", ob_type) 
                
                REVERSE_MAP = {v[0]: (k, v[1]) for k, v in OBD_MAP.items()}
                
                for flag, val in thing_props.items():
                    if val is True and flag in REVERSE_MAP:
                        xml_key, type_def = REVERSE_MAP[flag]
                        xml_val = ""
                        
                        data = thing_props.get(flag + '_data', (0,0))
                        # Garante que data é tupla/lista acessível
                        if not isinstance(data, (list, tuple)):
                            data = (data,)

                        if type_def == int:
                            xml_val = str(data[0])
                        elif type_def == "light" or type_def == "offset":
                            if len(data) >= 2:
                                xml_val = f"{data[0]},{data[1]}"
                            else:
                                xml_val = "0,0"
                        
                        attr_elem = ET.SubElement(root, "Attribute")
                        attr_elem.set("key", xml_key)
                        if xml_val:
                            attr_elem.set("value", xml_val)

                xml_str = ET.tostring(root, encoding='utf-8', method='xml')
                z.writestr("data.xml", xml_str)
                
                if not images:
                    img = Image.new("RGBA", (32, 32), (0,0,0,0))
                    images = [img]

                for i, img in enumerate(images):
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='PNG')
                    z.writestr(f"{i}.png", img_byte_arr.getvalue())
                    
        except Exception as e:
            print(f"Erro save_obd: {e}")
            raise e
