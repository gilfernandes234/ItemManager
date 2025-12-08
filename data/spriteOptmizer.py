import sys
import struct
import hashlib
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QProgressBar, QTextEdit, QMessageBox, QGroupBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

class OptimizerWorker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished_scan = pyqtSignal(dict, int, int)

    def __init__(self, spr_editor, dat_editor, clean_empty=True):
        super().__init__()
        self.spr = spr_editor
        self.dat = dat_editor
        self.clean_empty = clean_empty
        self.mode = "SCAN"
        self.remap_table = {}
        self.empty_ids = [] 

    def run(self):
        if self.mode == "SCAN":
            self.scan_sprites()
        elif self.mode == "APPLY":
            self.apply_optimization()

    def is_visually_empty(self, data):
        if not data or len(data) == 0:
            return True

        if len(data) < 10:

            return True

        try:

            offset = 0
            if len(data) > 64: 
                return False

            return False
        except:
            return False

    def scan_sprites(self):
        self.log.emit("Starting scan...")
        
        hashes = {}
        remap = {}
        
        duplicates_count = 0
        empty_found_count = 0
        
        master_empty_id = None 
        
        total_sprites = self.spr.sprite_count
        
        for sprite_id in range(1, total_sprites + 1):
            if sprite_id % 2000 == 0:
                self.progress.emit(int((sprite_id / total_sprites) * 100))
            
            data = self.spr.sprites_data.get(sprite_id, b'')
            
            if len(data) == 0:
                if master_empty_id is None:
                    master_empty_id = sprite_id
                  
                else:

                    remap[sprite_id] = master_empty_id
                    self.empty_ids.append(sprite_id)
                    empty_found_count += 1
                continue

            md5 = hashlib.md5(data).hexdigest()

            if md5 in hashes:

                original_id = hashes[md5]
                remap[sprite_id] = original_id
                
                self.empty_ids.append(sprite_id) 
                duplicates_count += 1
            else:
                hashes[md5] = sprite_id

        self.log.emit("-" * 30)
        self.log.emit("-" * 30)
        self.log.emit("Scan completed.")
        self.log.emit(f"Total sprites: {total_sprites}")
        self.log.emit(f"Empty merged: {empty_found_count}")
        self.log.emit(f"Visual duplicates: {duplicates_count}")
        self.log.emit(f"Total to optimize: {len(remap)}")

        self.progress.emit(100)
        self.finished_scan.emit(remap, duplicates_count, empty_found_count)

    def apply_optimization(self):
        if not self.remap_table:
            self.log.emit("Nothing to do.")
            return

        self.log.emit("Updating references in the DAT...")

        categories = ['items', 'outfits', 'effects', 'missiles']
        updated_things = 0
        total_steps = sum(len(self.dat.things[cat]) for cat in categories)
        current_step = 0

        for cat in categories:
            for thing_id, thing in self.dat.things[cat].items():
                current_step += 1
                if current_step % 1000 == 0:
                     self.progress.emit(int((current_step / total_steps) * 90))

                texture_bytes = thing.get('texture_bytes', b'')
                if not texture_bytes: continue

                new_bytes, changed = self.replace_sprites_in_texture(texture_bytes, self.remap_table)
                if changed:
                    thing['texture_bytes'] = new_bytes
                    updated_things += 1

        self.log.emit(f"Updated references: {updated_things}")

        if self.clean_empty and self.empty_ids:
            self.log.emit(f"Cleaning data of {len(self.empty_ids)} sprites in the SPR...")
            for spr_id in self.empty_ids:
                self.spr.sprites_data[spr_id] = b''
            
            self.spr.modified = True

        self.log.emit("Optimization Complete! Save the DAT and SPR.")
        self.progress.emit(100)

    def replace_sprites_in_texture(self, texture_bytes, remap_table):
        """Mesma lógica de byte-patching anterior"""
        try:
            if not texture_bytes or len(texture_bytes) < 2: return texture_bytes, False
            offset = 0
            width, height = struct.unpack_from('<BB', texture_bytes, offset)
            offset += 2
            if width > 1 or height > 1: offset += 1 
            if offset + 5 > len(texture_bytes): return texture_bytes, False
            layers, px, py, pz, frames = struct.unpack_from('<BBBBB', texture_bytes, offset)
            offset += 5
            if frames > 1:
                anim_size = 1 + 4 + 1 + (frames * 8)
                offset += anim_size

            total_sprites = width * height * px * py * pz * layers * frames
            remaining_bytes = len(texture_bytes) - offset
            if total_sprites == 0: return texture_bytes, False
            sprite_id_size = remaining_bytes // total_sprites
            if sprite_id_size not in (2, 4): return texture_bytes, False

            fmt = '<I' if sprite_id_size == 4 else '<H'
            
            current_ids = []
            read_offset = offset
            for _ in range(total_sprites):
                val = struct.unpack_from(fmt, texture_bytes, read_offset)[0]
                current_ids.append(val)
                read_offset += sprite_id_size

            has_changes = False
            new_ids = []
            for sid in current_ids:
                if sid in remap_table:
                    new_ids.append(remap_table[sid])
                    has_changes = True
                else:
                    new_ids.append(sid)

            if not has_changes: return texture_bytes, False

            header_part = texture_bytes[:offset]
            ids_part = bytearray()
            for nid in new_ids:
                ids_part.extend(struct.pack(fmt, nid))

            return header_part + ids_part, True
        except:
            return texture_bytes, False

class SpriteOptimizerWindow(QDialog):
    def __init__(self, spr_editor, dat_editor, parent=None):
        super().__init__(parent)
        self.spr = spr_editor
        self.dat = dat_editor
        self.remap_table = {}
        
        self.setWindowTitle("Sprite Optimizer & Cleaner")
        self.resize(500, 450)
        self.setStyleSheet("background-color: #494949; color: white;")
        
        self.init_ui()
        
        self.worker = OptimizerWorker(spr_editor, dat_editor)
        self.worker.progress.connect(self.update_progress)
        self.worker.log.connect(self.add_log)
        self.worker.finished_scan.connect(self.on_scan_finished)

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        info_group = QGroupBox("Info")
        info_layout = QVBoxLayout()
        info_lbl = QLabel(
            "1. Identifies duplicate sprites (same hash).\n"
            "2. Identifies empty sprites.\n"
            "3. Redirects references in the DAT to save IDs.\n"
            "4. Clears the content of unused sprites in the SPR."
        )

        info_lbl.setWordWrap(True)
        info_layout.addWidget(info_lbl)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        opt_group = QGroupBox("Options")
        opt_layout = QHBoxLayout()
        self.chk_clean = QCheckBox("Wipe optimized sprites data (Save space)")
        self.chk_clean.setChecked(True)
        #self.chk_clean.setToolTip("Substitui o conteúdo das sprites duplicadas por vazio (b'').")
        opt_layout.addWidget(self.chk_clean)
        opt_group.setLayout(opt_layout)
        layout.addWidget(opt_group)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("background-color: #333; color: #00ff00; font-family: Consolas; font-size: 11px;")
        layout.addWidget(self.log_area)

        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("QProgressBar { text-align: center; }")
        layout.addWidget(self.progress_bar)

        btn_layout = QHBoxLayout()
        self.btn_scan = QPushButton("1. Scan")
        self.btn_scan.setFixedHeight(40)
        self.btn_scan.setStyleSheet("background-color: #007acc; font-weight: bold;")
        self.btn_scan.clicked.connect(self.start_scan)
        btn_layout.addWidget(self.btn_scan)

        self.btn_apply = QPushButton("2. Optimize & Clean")
        self.btn_apply.setFixedHeight(40)
        self.btn_apply.setStyleSheet("background-color: #28a745; font-weight: bold;")
        self.btn_apply.clicked.connect(self.start_apply)
        self.btn_apply.setEnabled(False)
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)

    def add_log(self, message):
        self.log_area.append(message)
        # Rola para o fim
        sb = self.log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def update_progress(self, val):
        self.progress_bar.setValue(val)

    def start_scan(self):
        self.btn_scan.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.log_area.clear()
        self.progress_bar.setValue(0)
        self.worker.mode = "SCAN"
        self.worker.start()

    def on_scan_finished(self, remap_dict, dup_count, empty_count):
        self.remap_table = remap_dict
        self.btn_scan.setEnabled(True)
        
        total = dup_count + empty_count
        if total > 0:
            self.btn_apply.setEnabled(True)
            self.add_log(f"\n--- RESULT ---")
            self.add_log(f"Potential savings: {total} sprites.")
            self.add_log("Click 'Optimize' to apply.")
        else:
            self.add_log("\nNo optimization needed.")


    def start_apply(self):
        self.worker.clean_empty = self.chk_clean.isChecked()
        self.worker.remap_table = self.remap_table
        self.worker.mode = "APPLY"
        
        self.btn_scan.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.worker.start()
