#   ---------- ItemManager ----------
Editor spr and dat, upscale images and resizes.

Warning: Project is still EXPERIMENTAL – expect bugs, freezes and occasional crashes.


<img width="1919" height="1040" alt="Screenshot_11" src="https://github.com/user-attachments/assets/f2f14cd6-196b-44ef-bef2-51e7f0d3095a" />


<img width="1919" height="1039" alt="Screenshot_10" src="https://github.com/user-attachments/assets/566dd54e-46e1-4204-859f-ad835cc3e5ef" />


<img width="1919" height="1042" alt="Screenshot_12" src="https://github.com/user-attachments/assets/2a1dbad9-e7e6-4903-8e52-68f564acfa5f" />

Features:

- Image Enhancer
  - Upscale: 2, 4, 8
  - Denoise Level: 1, 2, 3 
  - Resize: 32x32, 64x64, 128x128, 512x512
  - Custom Size
  - Image Edit
    - Mirror Vertical
    - Mirror Horizontal
    - Color Adjust
    - Rotation
 
- Spr/Dat Editor (EXPERIMENTAL)
  - Edit Id
  - Flags Adjust
  - Mass Edit/Delete
  
- OTB Reload (EXPERIMENTAL)
  - Flags Reload/Sync
  
Manipulating the dat and spr files is only 
possible for versions 10.98; 
it is not recommended for other versions.

#   ---------- Required ----------

- Python 3.10+
  - py -m pip install pillow customtkinter numpy nuitka
  - https://github.com/lltcggie/waifu2x-caffe/releases/tag/1.2.0.4

  
#   ---------- Structure ----------

Put waifu2x-caffe release on ItemManager/waifu2x-caffe


<img width="186" height="228" alt="Screenshot_2" src="https://github.com/user-attachments/assets/5c937b6d-0882-4a1e-bc10-008980205237" />




<img width="651" height="157" alt="Screenshot_1" src="https://github.com/user-attachments/assets/ebc5c328-0520-4f92-b08c-3f8133d47e31" />



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
