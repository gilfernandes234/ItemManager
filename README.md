#   ---------- ItemManager ----------
Editor spr and dat, upscale images and resizes.

Warning: Project is still EXPERIMENTAL – expect bugs, freezes and occasional crashes.
#   ---------- NEW INTERFACE ----------

<img width="1919" height="1040" alt="Screenshot_2" src="https://github.com/user-attachments/assets/237c2464-cded-4f81-a7e7-6cdae3c6f865" />

<img width="1919" height="1036" alt="Screenshot_4" src="https://github.com/user-attachments/assets/a3398240-bcd3-4648-b1bf-2dcc07fd6b27" />

Features:

- Support
  - Transparency 
  - Extended
  - Extension .obd (Object Builder)
  - Only 1098, it is not recommended for other versions.

- Sprite Editor
  - Upscale: 2, 4, 8
  - Denoise Level: 1, 2, 3 
  - Resize Image
  - Custom Size
  - Image Edit
    - Mirror Vertical
    - Mirror Horizontal
    - Color Adjust
    - Rotation
    - Color/Background Remove
    - Paint Brush
    - Slicer Png
    - Eraser Tools
    - Selection tools
    - Outline/Adjust

- Layers Panel
- Export Project
 
- Spr/Dat Editor (EXPERIMENTAL)
  - Edit Item/Outfit/Missile/Effects
  - Flags Adjust
  - Mass Edit/Delete
  - Slicer (Obd Style)
  - Sprite Optmizer (Obd Style)
  - Import
  - Export
  
- OTB Reload (Dont Work)
  - Flags Reload/Sync


#   ---------- Required ----------

  - Resolution: 1920x1080
  - 8gb Ram
  - Processor Dual Core
  - Hd: 4gb

```bash
# Instalar dependências
- Python 3.10+

py -m pip install -r requirements.txt

# Executar 
py itemManager.py
```


#   ---------- Server-Side/Client-Side ----------

Tibia.dat/spr download:
https://downloads.ots.me/data/tibia-clients/dat_and_spr/1098.zip

- Client-side:

Otclient Redemption:
https://github.com/mehah/otclient/releases

Otclient V8:
https://github.com/OTCv8/otclientv8


- Server-side:

Black-Tek:
https://github.com/Black-Tek/BlackTek-Server/releases

The Forgotten Server 1.42:
https://github.com/otland/forgottenserver/releases/tag/v1.4.2
