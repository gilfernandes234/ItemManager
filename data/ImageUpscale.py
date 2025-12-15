import os
import shutil
import subprocess
import numpy as np
from PIL import Image, ImageEnhance
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFrame, QSlider, 
                             QCheckBox, QComboBox, QTextEdit, QScrollArea, 
                             QFileDialog, QMessageBox, QGroupBox, QGridLayout)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap

# --- CLASSE WORKER (Mantida igual) ---
class ProcessingWorker(QThread):
    log_signal = pyqtSignal(str)      
    finished_signal = pyqtSignal()    
    error_signal = pyqtSignal(str)    

    def __init__(self, params):
        super().__init__()
        self.params = params
        self.stop_requested = False

    def run(self):
        folder = self.params['folder']
        out_folder = os.path.join(folder, "output_processed")
        os.makedirs(out_folder, exist_ok=True)
        
        files_to_process = [f for f in os.listdir(folder) if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))]
        count = 0

        waifu_exe = self.params['waifu_exe']
        
        for file in files_to_process:
            if self.stop_requested: break

            input_path = os.path.join(folder, file)
            temp_output = os.path.join(out_folder, "temp_" + file)
            final_output = os.path.join(out_folder, file)
            src = input_path

            self.log_signal.emit(f"Processing: {file}")

            # 1. Waifu2x Denoise
            if self.params['denoise_enabled']:
                cmd = [
                    waifu_exe, "-i", src, "-o", temp_output,
                    "-s", "1", "-m", "noise", "-n", self.params['denoise_level'], "-p", "cpu"
                ]
                subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                src = temp_output

            # 2. Waifu2x Upscale
            if self.params['upscale_enabled']:
                cmd = [
                    waifu_exe, "-i", src, "-o", temp_output,
                    "-s", self.params['upscale_factor'], "-m", "noise_scale", 
                    "-n", self.params['denoise_level'], "-p", "cpu"
                ]
                subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                src = temp_output

            # 3. Pillow Processing
            try:
                img = Image.open(src)
                
                if self.params['custom_resize_enabled']:
                    img = img.resize((self.params['custom_w'], self.params['custom_h']), Image.NEAREST)
                elif self.params['resize_enabled']:
                    size = self.params['resize_final']
                    img = img.resize((size, size), Image.NEAREST)

                img = self.apply_pillow_adjustments(img)
                img.save(final_output)
                count += 1

            except Exception as e:
                self.log_signal.emit(f"Error processing {file}: {str(e)}")

            if os.path.exists(temp_output):
                os.remove(temp_output)

        self.log_signal.emit(f"Completed! {count} images processed.")
        self.finished_signal.emit()

    def apply_pillow_adjustments(self, img):
        p = self.params
        img = ImageEnhance.Brightness(img).enhance(p['brightness'])
        img = ImageEnhance.Contrast(img).enhance(p['contrast'])
        img = ImageEnhance.Color(img).enhance(p['saturation'])

        img_np = np.array(img).astype(np.float32)

        img_np[..., 0] = np.clip(img_np[..., 0] * p['red'], 0, 255)
        img_np[..., 1] = np.clip(img_np[..., 1] * p['green'], 0, 255)
        img_np[..., 2] = np.clip(img_np[..., 2] * p['blue'], 0, 255)

        img = Image.fromarray(img_np.astype(np.uint8))

        if p['rotation'] != 0:
            img = img.rotate(p['rotation'], expand=True)
        if p['flip_h']:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        if p['flip_v']:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
            
        return img


# --- CLASSE PRINCIPAL ---
class ImageUpscaleTab(QWidget):
    def __init__(self, parent_widget_ignored, base_path, dat_tab=None): 
        super().__init__()
        self.base_path = base_path
        self.dat_tab = dat_tab 
        
        # Variável para controlar se estamos processando o SPR inteiro
        self.is_full_spr_mode = False 
        self.temp_spr_folder = os.path.join(base_path, "temp_spr_extract")

        self.waifu_exe = os.path.join(base_path, "waifu2x-caffe", "waifu2x-caffe-cui.exe")
        
        self.layout_main = QVBoxLayout(self)
        self.build_ui()
        self.build_loading_overlay()

    def build_ui(self):
        # Path
        path_frame = QFrame()
        path_layout = QHBoxLayout(path_frame)
        path_layout.setContentsMargins(0,0,0,0)
        self.path_entry = QLineEdit()
        self.path_entry.setPlaceholderText("Choose a folder...")
        btn_search = QPushButton("Search Folder")
        btn_search.clicked.connect(self.select_folder)
        path_layout.addWidget(QLabel("Path:"))
        path_layout.addWidget(self.path_entry)
        path_layout.addWidget(btn_search)
        self.layout_main.addWidget(path_frame)

        # Controls
        self.create_advanced_adjustments()
        self.create_denoise_upscale_controls()
        
        # Checkbox Auto Import (Normal Mode)
        self.chk_auto_import = QCheckBox("Auto-Import to Sprite List (Path Mode)")
        self.chk_auto_import.setStyleSheet("font-weight: bold; color: cyan;")
        self.chk_auto_import.setChecked(True)
        h_imp = QHBoxLayout()
        h_imp.addWidget(self.chk_auto_import)
        h_imp.addStretch()
        self.layout_main.addLayout(h_imp)

        # Buttons Layout
        btn_layout = QHBoxLayout()
        
        # 1. Apply Normal (Folder)
        self.btn_apply = QPushButton("Apply (Selected Folder)")
        self.btn_apply.setFixedHeight(40)
        self.btn_apply.setStyleSheet("background-color: #ff9326; color: black; font-weight: bold; border-radius: 5px;")
        self.btn_apply.clicked.connect(lambda: self.start_processing(mode='FOLDER'))
        btn_layout.addWidget(self.btn_apply)

        # 2. Process Full SPR (NOVO)
        self.btn_full_spr = QPushButton("Process Full Loaded SPR (Not Recommended)")
        self.btn_full_spr.setFixedHeight(40)
        self.btn_full_spr.setStyleSheet("background-color: #d11e4f; color: white; font-weight: bold; border-radius: 5px;")
        self.btn_full_spr.setToolTip("Extracts all sprites from SPR, processes them and replaces in place.")
        self.btn_full_spr.clicked.connect(self.prepare_full_spr_processing)
        btn_layout.addWidget(self.btn_full_spr)

        self.layout_main.addLayout(btn_layout)       
        

        # Import Helper
        self.btn_import = QPushButton("Import Output to SPR (Only 32x32)")
        self.btn_import.setFixedHeight(40)

        self.btn_import.clicked.connect(self.manual_import_output) 
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(self.btn_import)
        self.layout_main.addLayout(h)

        self.create_display_frames()

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: lightgreen; font-weight: bold;")
        self.layout_main.addWidget(self.status_label)

    def create_advanced_adjustments(self):
        group = QGroupBox("Advanced Adjustments")
        layout = QGridLayout(group)
        def create_slider(label_text, min_v, max_v, default_v, scale_factor=100):
            lbl = QLabel(label_text)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(int(min_v * scale_factor), int(max_v * scale_factor))
            slider.setValue(int(default_v * scale_factor))
            return lbl, slider

        l_br, self.slider_brightness = create_slider("Brightness", 0, 2, 1)
        l_ct, self.slider_contrast = create_slider("Contrast", 0, 2, 1)
        l_sat, self.slider_saturation = create_slider("Saturation", 0, 2, 1)
        layout.addWidget(l_br, 0, 0); layout.addWidget(self.slider_brightness, 0, 1)
        layout.addWidget(l_ct, 1, 0); layout.addWidget(self.slider_contrast, 1, 1)
        layout.addWidget(l_sat, 2, 0); layout.addWidget(self.slider_saturation, 2, 1)
        
        l_r, self.slider_red = create_slider("Red", 0, 2, 1)       
        l_g, self.slider_green = create_slider("Green", 0, 2, 1)
        l_b, self.slider_blue = create_slider("Blue", 0, 2, 1)
        layout.addWidget(l_r, 0, 2); layout.addWidget(self.slider_red, 0, 3)      
        layout.addWidget(l_g, 1, 2); layout.addWidget(self.slider_green, 1, 3)
        layout.addWidget(l_b, 2, 2); layout.addWidget(self.slider_blue, 2, 3)

        l_rot, self.slider_rotate = create_slider("Rotation", 0, 360, 0, scale_factor=1)
        self.chk_flip_h = QCheckBox("Mirror Horizontal")
        self.chk_flip_v = QCheckBox("Mirror Vertical")
        layout.addWidget(l_rot, 3, 0); layout.addWidget(self.slider_rotate, 3, 1)
        layout.addWidget(self.chk_flip_h, 3, 2); layout.addWidget(self.chk_flip_v, 3, 3)
        self.layout_main.addWidget(group)

    def create_denoise_upscale_controls(self):
        frame = QFrame(); layout = QHBoxLayout(frame)
        self.chk_denoise = QCheckBox("Denoise"); self.combo_denoise = QComboBox(); self.combo_denoise.addItems(["0", "1", "2", "3"]); self.combo_denoise.setCurrentText("1")
        layout.addWidget(self.chk_denoise); layout.addWidget(self.combo_denoise)
        line1 = QFrame(); line1.setFrameShape(QFrame.Shape.VLine); layout.addWidget(line1)
        self.chk_upscale = QCheckBox("Upscale"); self.combo_upscale = QComboBox(); self.combo_upscale.addItems(["2", "4", "8"])
        layout.addWidget(self.chk_upscale); layout.addWidget(self.combo_upscale)
        line2 = QFrame(); line2.setFrameShape(QFrame.Shape.VLine); layout.addWidget(line2)
        self.chk_resize = QCheckBox("Resize"); self.combo_resize = QComboBox(); self.combo_resize.addItems(["32", "64", "128", "240", "256", "512"]); self.combo_resize.setEditable(True) 
        layout.addWidget(self.chk_resize); layout.addWidget(self.combo_resize)
        line3 = QFrame(); line3.setFrameShape(QFrame.Shape.VLine); layout.addWidget(line3)
        self.chk_custom_resize = QCheckBox("Custom Size"); self.entry_w = QLineEdit(); self.entry_w.setPlaceholderText("W"); self.entry_w.setFixedWidth(50)
        self.entry_h = QLineEdit(); self.entry_h.setPlaceholderText("H"); self.entry_h.setFixedWidth(50)
        layout.addWidget(self.chk_custom_resize); layout.addWidget(self.entry_w); layout.addWidget(self.entry_h)
        self.layout_main.addWidget(frame)

    def create_display_frames(self):
        display_container = QWidget(); layout = QHBoxLayout(display_container)
        log_group = QGroupBox("Log"); log_layout = QVBoxLayout(log_group); self.log_box = QTextEdit(); self.log_box.setReadOnly(True); log_layout.addWidget(self.log_box)
        input_group = QGroupBox("Main Folder"); input_layout = QVBoxLayout(input_group); self.scroll_input = QScrollArea(); self.scroll_input.setWidgetResizable(True); self.input_content = QWidget(); self.input_content_layout = QVBoxLayout(self.input_content); self.scroll_input.setWidget(self.input_content); input_layout.addWidget(self.scroll_input)
        output_group = QGroupBox("Output"); output_layout = QVBoxLayout(output_group); self.scroll_output = QScrollArea(); self.scroll_output.setWidgetResizable(True); self.output_content = QWidget(); self.output_content_layout = QVBoxLayout(self.output_content); self.scroll_output.setWidget(self.output_content); output_layout.addWidget(self.scroll_output)
        layout.addWidget(log_group, 1); layout.addWidget(input_group, 1); layout.addWidget(output_group, 1)
        self.layout_main.addWidget(display_container)

    def build_loading_overlay(self):
        self.overlay = QFrame(self)
        self.overlay.setStyleSheet("background-color: rgba(0, 0, 0, 180);")
        self.overlay.hide()
        self.lbl_loading = QLabel("Processing...\nPlease Wait", self.overlay)
        self.lbl_loading.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
        self.lbl_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def resizeEvent(self, event):
        if hasattr(self, 'overlay') and self.overlay:
            self.overlay.resize(self.size())
            if hasattr(self, 'lbl_loading'): self.lbl_loading.resize(self.size())
        super().resizeEvent(event)

    def show_loading(self, show=True, text="Processing..."):
        if show:
            self.lbl_loading.setText(text)
            self.overlay.raise_()
            self.overlay.show()
            self.btn_apply.setEnabled(False)
            self.btn_full_spr.setEnabled(False)
        else:
            self.overlay.hide()
            self.btn_apply.setEnabled(True)
            self.btn_full_spr.setEnabled(True)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.path_entry.setText(folder)
            self.load_images_to_scroll(folder, self.input_content_layout, is_input=True)

    def load_images_to_scroll(self, folder, layout, is_input=True):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget: widget.deleteLater()
        
        if not os.path.exists(folder): return
        files = sorted([f for f in os.listdir(folder) if f.lower().endswith((".png", ".jpg", ".bmp"))])
        limit = 50 
        for i, file in enumerate(files):
            if i >= limit:
                layout.addWidget(QLabel(f"... {len(files)-limit} more")); break
            path = os.path.join(folder, file)
            try:
                pix = QPixmap(path)
                if not pix.isNull():
                    pix = pix.scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatio)
                    lbl = QLabel(); lbl.setPixmap(pix); lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(lbl)
            except: pass
        layout.addStretch()

    def log(self, message):
        self.log_box.append(message)

    def prepare_full_spr_processing(self):
        if not self.dat_tab or not self.dat_tab.spr:
            QMessageBox.critical(self, "Error", "No SPR loaded in Editor tab!")
            return
            
        count = self.dat_tab.spr.sprite_count
        if count == 0:
            QMessageBox.warning(self, "Warning", "SPR is empty.")
            return

        reply = QMessageBox.question(
            self, "Confirm Full Processing",
            (
                f"You are about to extract and process {count} sprites.\n\n"
                "⚠️ WARNING:\n"
                " - Using Upscale/Denoise on a full SPR can take HOURS.\n"
                " - Applying color changes may affect outfit masks, missiles, and effects.\n"
                " - Poor adjustments can damage your image.\n"
                " - If you only want color adjustments, disable Denoise/Upscale.\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.No:
            return

        self.show_loading(True, "Extracting Sprites...")
        if os.path.exists(self.temp_spr_folder):
            shutil.rmtree(self.temp_spr_folder)
        os.makedirs(self.temp_spr_folder)
       
        
        try:
            exported = 0
            for i in range(1, count + 1):
                img = self.dat_tab.spr.get_sprite(i)
                if img:

                    img.save(os.path.join(self.temp_spr_folder, f"{i}.png"))
                    exported += 1
                
                if i % 500 == 0:
                    self.lbl_loading.setText(f"Extracting...\n{i}/{count}")
                    QApplication.processEvents() 
            
            self.log(f"Extracted {exported} sprites from SPR.")
            
            # 5. Configurar UI para apontar para a pasta temp
            self.path_entry.setText(self.temp_spr_folder)
            self.load_images_to_scroll(self.temp_spr_folder, self.input_content_layout, is_input=True)
            
            # 6. Iniciar Processamento
            self.start_processing(mode='FULL_SPR')

        except Exception as e:
            self.show_loading(False)
            QMessageBox.critical(self, "Error", f"Failed to extract sprites: {e}")

    def start_processing(self, mode='FOLDER'):
        folder = self.path_entry.text().strip()
        if not os.path.isdir(folder):
            QMessageBox.critical(self, "Error", "Invalid Folder!")
            return
            
        self.is_full_spr_mode = (mode == 'FULL_SPR')

        # Coletar parâmetros
        params = {
            'folder': folder,
            'waifu_exe': self.waifu_exe,
            'denoise_enabled': self.chk_denoise.isChecked(),
            'denoise_level': self.combo_denoise.currentText(),
            'upscale_enabled': self.chk_upscale.isChecked(),
            'upscale_factor': self.combo_upscale.currentText(),
            'resize_enabled': self.chk_resize.isChecked(),
            'resize_final': int(self.combo_resize.currentText()) if self.combo_resize.currentText().isdigit() else 32,
            'custom_resize_enabled': self.chk_custom_resize.isChecked(),
            'custom_w': 0, 'custom_h': 0,
            'brightness': self.slider_brightness.value() / 100.0,
            'contrast': self.slider_contrast.value() / 100.0,
            'saturation': self.slider_saturation.value() / 100.0,
            'red': self.slider_red.value() / 100.0,
            'green': self.slider_green.value() / 100.0,
            'blue': self.slider_blue.value() / 100.0,
            'rotation': self.slider_rotate.value(),
            'flip_h': self.chk_flip_h.isChecked(),
            'flip_v': self.chk_flip_v.isChecked()
        }

        if params['custom_resize_enabled']:
            try:
                params['custom_w'] = int(self.entry_w.text())
                params['custom_h'] = int(self.entry_h.text())
            except ValueError:
                QMessageBox.critical(self, "Error", "Invalid Custom Size")
                return

        if not (params['denoise_enabled'] or params['upscale_enabled'] or params['resize_enabled'] or params['custom_resize_enabled']):
             QMessageBox.warning(self, "Warning", "Select at least one action.")
             return
             
        if (params['denoise_enabled'] or params['upscale_enabled']) and not os.path.isfile(self.waifu_exe):
             QMessageBox.critical(self, "Error", f"Waifu2x exe not found at:\n{self.waifu_exe}")
             return

        self.show_loading(True, "Processing Images...")
        self.log_box.clear()
        
        self.worker = ProcessingWorker(params)
        self.worker.log_signal.connect(self.log)
        self.worker.finished_signal.connect(self.on_processing_finished)
        self.worker.start()
        
        
    def manual_import_output(self):
        if not self.dat_tab or not hasattr(self.dat_tab, 'handle_slicer_import'):
            QMessageBox.warning(self, "Error", "Editor tab integration not found.")
            return

        folder = self.path_entry.text().strip()
        out_folder = os.path.join(folder, "output_processed")
        
        if not os.path.exists(out_folder):
            QMessageBox.warning(self, "Error", "Output folder does not exist. Run processing first.")
            return

        processed_files = sorted([f for f in os.listdir(out_folder) if f.lower().endswith((".png", ".jpg", ".bmp"))])
        
        if not processed_files:
            QMessageBox.information(self, "Info", "No images found in output folder.")
            return

        pil_images = []
        skipped_count = 0
        for f in processed_files:
            try:
                full_path = os.path.join(out_folder, f)
                img = Image.open(full_path).convert("RGBA")
                
                if img.width == 32 and img.height == 32:
                    pil_images.append(img)
                else:
                    skipped_count += 1
            except Exception:
                pass

        if pil_images:

            self.dat_tab.handle_slicer_import(pil_images)
            
            msg = f"Successfully imported {len(pil_images)} sprites (32x32)."
            if skipped_count > 0:
                msg += f"\nSkipped {skipped_count} images with invalid size."
            
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.warning(self, "Warning", "No valid 32x32 images found in output folder.")
        

    def on_processing_finished(self):
        folder = self.path_entry.text()
        out_folder = os.path.join(folder, "output_processed")
        self.load_images_to_scroll(out_folder, self.output_content_layout, is_input=False)
        
        if self.is_full_spr_mode:
            self.lbl_loading.setText("Updating SPR...")
            QApplication.processEvents()
            
            try:
                processed_files = sorted(os.listdir(out_folder))
                replaced_count = 0
                
                for f in processed_files:
                    if f.lower().endswith((".png", ".jpg")):

                        try:
                            sprite_id = int(os.path.splitext(f)[0])
                            full_path = os.path.join(out_folder, f)
                            
                            img = Image.open(full_path).convert("RGBA")
                            
                            self.dat_tab.spr.replace_sprite(sprite_id, img)
                            replaced_count += 1
                        except ValueError:
                            pass # Arquivo com nome estranho, ignora
                
                # Atualiza a UI do Editor (lista de sprites e preview)
                self.dat_tab.reload_current_view() # Função hipotética de refresh, ou apenas update_lists
                self.dat_tab.update_sprite_list()
                
                self.show_loading(False)
                QMessageBox.information(self, "Success", f"Finished! {replaced_count} sprites replaced in SPR.")

                # shutil.rmtree(self.temp_spr_folder)

            except Exception as e:
                self.show_loading(False)
                QMessageBox.critical(self, "Error", f"Failed to update SPR: {e}")
            
            self.is_full_spr_mode = False # Reseta flag

        elif self.chk_auto_import.isChecked():
            # (Código anterior de Auto-Import Append)
            self.show_loading(False)
            if not self.dat_tab or not self.dat_tab.spr:
                QMessageBox.warning(self, "Integration Error", "No SPR loaded.")
                return

            try:
                processed_files = sorted([f for f in os.listdir(out_folder) if f.lower().endswith((".png", ".jpg"))])
                pil_images = []
                for f in processed_files:
                    try:
                        img = Image.open(os.path.join(out_folder, f)).convert("RGBA")
                        pil_images.append(img)
                    except: pass

                if pil_images:
                    self.dat_tab.handle_slicer_import(pil_images)
                    QMessageBox.information(self, "Success", f"Imported {len(pil_images)} new sprites.")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
        else:
            self.show_loading(False)
            QMessageBox.information(self, "Success", "Processing Finished.")

# Necessário importar QApplication no topo se não tiver:
from PyQt6.QtWidgets import QApplication
