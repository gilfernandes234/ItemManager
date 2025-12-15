
#   ---------- Required: ----------
#  Python 3.10
#  py -m pip install customtkinter
#  py -m pip install pillow
#  py -m pip install torch
#  py -m pip install waifu2x
# py -m nuitka --onefile --windows-disable-console --enable-plugin=tk-inter --include-data-dir=C:\Upscale\data=data C:\Upscale\Converter.py

# py -m nuitka --onefile --windows-console-mode=disable --enable-plugin=tk-inter --windows-icon-from-ico="C:\Upscale\data\upscale.ico" --include-data-dir="C:\Upscale\data=data" C:\Upscale\Converter.py

from PIL import ImageTk
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image
import subprocess
import os
import io
import sys

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

if getattr(sys, 'frozen', False):

    base_path = os.path.dirname(sys.executable)
else:

    base_path = os.path.dirname(os.path.abspath(__file__))

WAIFU_EXE = os.path.join(base_path, "data", "upscale.exe")

class ImageUpscaleApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Upscale Converter")
        self.geometry("1260x920")

        icon_path = os.path.join(base_path, "data", "upscale.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        ctk.CTkLabel(
            self, text="Upscale Converter / Resize",
            font=("Arial", 30, "bold")
        ).pack(pady=15)

        ctk.CTkLabel(
            self, text="Made by Sherrat",
            font=("Arial", 15, "bold")
        ).pack(pady=2)

        self.frame = ctk.CTkFrame(self, corner_radius=10)
        self.frame.pack(padx=10, pady=10, fill="x")
        
        ctk.CTkLabel(self.frame, text="Pasta com imagens:").pack(pady=5)
        self.path_entry = ctk.CTkEntry(self.frame, placeholder_text="Selecione a pasta...")
        self.path_entry.pack(padx=10, pady=5, fill="x")
        ctk.CTkButton(self.frame, text="📁 Procurar", command=self.select_folder).pack(pady=5)

        controls_frame = ctk.CTkFrame(self.frame, corner_radius=10)
        controls_frame.pack(padx=10, pady=10, fill="x")

        # ----- Denoise -----
        controls_frame.grid_columnconfigure(0, weight=1)
        controls_frame.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(controls_frame, text="Denoise").grid(row=0, column=0, padx=10, pady=5, sticky="n")
        self.use_denoise = ctk.CTkSwitch(controls_frame, text="Aplicar Denoise")
        self.use_denoise.grid(row=1, column=0, padx=10, pady=5, sticky="n")
        ctk.CTkLabel(controls_frame, text="Nível:").grid(row=2, column=0, padx=10, pady=2, sticky="n")
        self.denoise_level = ctk.CTkComboBox(controls_frame, values=["0","1","2","3"])
        self.denoise_level.set("1")
        self.denoise_level.grid(row=3, column=0, padx=10, pady=2, sticky="n")

        separator = ctk.CTkFrame(controls_frame, width=2, fg_color="gray")
        separator.grid(row=0, column=1, rowspan=4, padx=5, pady=5, sticky="ns")

        # ----- Upscale -----
        ctk.CTkLabel(controls_frame, text="Upscale").grid(row=0, column=2, padx=10, pady=5, sticky="n")
        self.use_upscale = ctk.CTkSwitch(controls_frame, text="Usar Upscale")
        self.use_upscale.grid(row=1, column=2, padx=10, pady=5, sticky="n")
        ctk.CTkLabel(controls_frame, text="Fator:").grid(row=2, column=2, padx=10, pady=2, sticky="n")
        self.upscale_factor = ctk.CTkComboBox(controls_frame, values=["2","4"])
        self.upscale_factor.set("2")
        self.upscale_factor.grid(row=3, column=2, padx=10, pady=2, sticky="n")


        resize_frame = ctk.CTkFrame(self.frame, corner_radius=10)
        resize_frame.pack(padx=10, pady=10, fill="x")

        resize_frame.grid_columnconfigure(0, weight=1)
        resize_frame.grid_columnconfigure(1, weight=1)

        self.use_resize = ctk.CTkSwitch(resize_frame, text="Redimensionar (Sem Upscale)")
        self.use_resize.grid(row=0, column=0, columnspan=2, padx=10, pady=5, sticky="n")

        ctk.CTkLabel(resize_frame, text="Tamanho final (px):").grid(row=1, column=0, padx=10, pady=5, sticky="e")

        self.resize_output = ctk.CTkComboBox(resize_frame, values=["32","64","128","240","256","512"])
        self.resize_output.set("32")
        self.resize_output.grid(row=1, column=1, padx=10, pady=5, sticky="w")
        

        ctk.CTkButton(
            self,
            text="Converter",
            height=25,
            font=("Arial", 16),
            fg_color="#ff9326",     
            hover_color="#ffa64c",  
            command=self.convert_images
        ).pack(pady=5)


        main_display_frame = ctk.CTkFrame(self, corner_radius=10)
        main_display_frame.pack(padx=10, pady=5, fill="both", expand=True)

        main_display_frame.grid_columnconfigure(0, weight=1)
        main_display_frame.grid_columnconfigure(1, weight=1)
        main_display_frame.grid_columnconfigure(2, weight=1)

        # ----- Log -----
        log_frame = ctk.CTkFrame(main_display_frame, corner_radius=7)
        log_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        ctk.CTkLabel(log_frame, text="Log:").pack()
        self.log_box = ctk.CTkTextbox(log_frame, height=300)
        self.log_box.pack(padx=5, pady=5, fill="both", expand=True)

        # ----- Input Images -----
        input_frame = ctk.CTkFrame(main_display_frame, corner_radius=7)
        input_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        ctk.CTkLabel(input_frame, text="Fotos da pasta:").pack()
        self.input_scroll = ctk.CTkScrollableFrame(input_frame, height=0)
        self.input_scroll.pack(padx=5, pady=5, fill="both", expand=True)

        # ----- Output Images -----
        output_frame = ctk.CTkFrame(main_display_frame, corner_radius=7)
        output_frame.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")
        ctk.CTkLabel(output_frame, text="Fotos Convertidas:").pack()
        self.output_scroll = ctk.CTkScrollableFrame(output_frame, height=0)
        self.output_scroll.pack(padx=5, pady=5, fill="both", expand=True)


        self.status = ctk.CTkLabel(self, text="Pronto", text_color="lightgreen")
        self.status.pack(pady=5)

    def show_images(self, folder):
        # Limpa frames
        for widget in self.input_scroll.winfo_children():
            widget.destroy()
        for widget in self.output_scroll.winfo_children():
            widget.destroy()

        self.input_photos = []
        self.output_photos = []

        for file in os.listdir(folder):
            if file.lower().endswith((".png", ".jpg", ".jpeg")):
                path = os.path.join(folder, file)
                img = Image.open(path)
                img.thumbnail((200,200))
                photo = ImageTk.PhotoImage(img)
                self.input_photos.append(photo)
                label = ctk.CTkLabel(self.input_scroll, image=photo, text="")
                label.pack(pady=5)

        out_folder = os.path.join(folder, "output_processed")
        if os.path.isdir(out_folder):
            for file in os.listdir(out_folder):
                if file.lower().endswith((".png", ".jpg", ".jpeg")):
                    path = os.path.join(out_folder, file)
                    img = Image.open(path)
                    img.thumbnail((50,50))
                    photo = ImageTk.PhotoImage(img)
                    self.output_photos.append(photo)
                    label = ctk.CTkLabel(self.output_scroll, image=photo, text="")
                    label.pack(pady=5)

    def log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)
            self.show_images(folder)
            
            
    def resize_image(self, input_path, output_path, size):
        img = Image.open(input_path)
        img = img.resize((size, size), Image.NEAREST)
        img.save(output_path)

    def convert_images(self):

        folder = self.path_entry.get().strip()
        
        
        if not os.path.isdir(folder):
            messagebox.showerror("Erro", "Selecione uma pasta válida!")
            return

        denoise_enabled = self.use_denoise.get()
        upscale_enabled = self.use_upscale.get()
        resize_enabled = self.use_resize.get()

        denoise_level = self.denoise_level.get()
        upscale_factor = self.upscale_factor.get()
        resize_final = int(self.resize_output.get())
        
        if not denoise_enabled and not upscale_enabled and not resize_enabled:
            messagebox.showerror("Erro", "Selecione pelo menos uma opção!")
            return

        if (denoise_enabled or upscale_enabled) and not os.path.isfile(WAIFU_EXE):
            messagebox.showerror("Erro", f"Arquivo não encontrado:\n{WAIFU_EXE}")
            return

        out_folder = os.path.join(folder, "output_processed")
        os.makedirs(out_folder, exist_ok=True)

        count = 0

        for file in os.listdir(folder):
            if file.lower().endswith((".png", ".jpg", ".jpeg")):

                input_path = os.path.join(folder, file)
                temp_output = os.path.join(out_folder, "temp_" + file)
                final_output = os.path.join(out_folder, file)

                src = input_path
                self.log(f"Processando: {file}")

                if denoise_enabled:
                    cmd = [
                        WAIFU_EXE,
                        "-i", src,
                        "-o", temp_output,
                        "-s", "1",
                        "-m", "noise",
                        "-n", denoise_level,
                        "-p", "cpu"
                    ]
                    subprocess.run(cmd)
                    src = temp_output

                if upscale_enabled:
                    cmd = [
                        WAIFU_EXE,
                        "-i", src,
                        "-o", temp_output,
                        "-s", upscale_factor,
                        "-m", "noise_scale",
                        "-n", denoise_level,
                        "-p", "cpu"
                    ]
                    subprocess.run(cmd)
                    src = temp_output

                if resize_enabled:
                    self.resize_image(src, final_output, resize_final)
                else:
                    if src != final_output:
                        os.replace(src, final_output)

                if os.path.exists(temp_output):
                    os.remove(temp_output)

                count += 1
                self.show_images(folder)


        self.status.configure(text=f"Concluído! {count} imagens processadas.")
        messagebox.showinfo("Pronto", f"{count} imagens foram geradas com sucesso!")


if __name__ == "__main__":
    ImageUpscaleApp().mainloop()