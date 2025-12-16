import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image
import os

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class ImageResizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Image Resizer")
        self.geometry("600x460")

        self.frame = ctk.CTkFrame(self, corner_radius=15)
        self.frame.pack(padx=10, pady=10, fill="x")

        ctk.CTkLabel(self.frame, text="Select Folder:").pack(pady=5)

        self.path_entry = ctk.CTkEntry(self.frame, placeholder_text="Select Folder...")
        self.path_entry.pack(padx=10, pady=5, fill="x")

        self.browse_btn = ctk.CTkButton(
            self.frame, text="📁 Search", command=self.select_folder
        )
        self.browse_btn.pack(pady=5)

        # 🔽 Seletor de conversão
        ctk.CTkLabel(self.frame, text="Conversion Mode:").pack(pady=(15, 5))

        self.mode_var = ctk.StringVar(value="32to64")

        self.mode_select = ctk.CTkOptionMenu(
            self.frame,
            values=["32x32 → 64x64", "64x64 → 32x32"],
            variable=self.mode_var
        )
        self.mode_select.pack(pady=5)

        self.convert_btn = ctk.CTkButton(
            self, text="Resize", height=40,
            font=("Arial", 16),
            command=self.convert_images
        )
        self.convert_btn.pack(pady=15)

        ctk.CTkLabel(self, text="Log:").pack()
        self.log_box = ctk.CTkTextbox(self, height=140)
        self.log_box.pack(padx=10, pady=5, fill="both")

        self.status = ctk.CTkLabel(self, text="Ready.", text_color="lightgreen")
        self.status.pack(pady=5)

    def log(self, msg):
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)

    def convert_images(self):
        folder = self.path_entry.get().strip()

        if not os.path.isdir(folder):
            messagebox.showerror("Error", "Select a valid folder!")
            return

        mode = self.mode_var.get()

        if mode == "32x32 → 64x64":
            size = (64, 64)
            out_folder = "converted_64x64"
        else:
            size = (32, 32)
            out_folder = "converted_32x32"

        out_path = os.path.join(folder, out_folder)
        os.makedirs(out_path, exist_ok=True)

        self.log_box.delete("1.0", "end")
        count = 0

        for file in os.listdir(folder):
            if file.lower().endswith((".png", ".jpg", ".jpeg")):
                try:
                    img = Image.open(os.path.join(folder, file))
                    img_resized = img.resize(size, Image.NEAREST)
                    img_resized.save(os.path.join(out_path, file))

                    self.log(f"✔ Converted: {file}")
                    count += 1
                except Exception as e:
                    self.log(f"❌ Error in {file}: {e}")

        self.status.configure(
            text=f"Completed! {count} images converted.",
            text_color="lightgreen"
        )
        messagebox.showinfo(
            "Done",
            f"{count} images were successfully converted!"
        )


if __name__ == "__main__":
    ImageResizerApp().mainloop()
