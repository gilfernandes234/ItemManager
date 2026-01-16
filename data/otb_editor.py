from PyQt6.QtGui import QIcon, QPixmap, QImage, QColor, QAction, QClipboard
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, 
                             QTreeWidget, QTreeWidgetItem, QGroupBox, QFormLayout, QSpinBox, 
                             QLineEdit, QSplitter, QMessageBox, QLabel, QCheckBox, QScrollArea,
                             QGridLayout, QFrame, QComboBox, QPlainTextEdit, QMenuBar, QMenu,
                             QInputDialog, QTreeWidgetItemIterator, QProgressDialog, QProgressBar, QApplication,
                             QStyle, QProxyStyle)
from PyQt6.QtCore import Qt, QSize, QSettings
from otb_handler import * 
import sys
from PIL import Image

def pil_to_qpixmap(pil_image):
    if pil_image is None:
        return QPixmap()
    
    if pil_image.mode == "RGB":
        r, g, b = pil_image.split()
        pil_image = Image.merge("RGB", (b, g, r))
    elif pil_image.mode == "RGBA":
        r, g, b, a = pil_image.split()
        pil_image = Image.merge("RGBA", (b, g, r, a))
    elif pil_image.mode == "L":
        pil_image = pil_image.convert("RGBA")
        
    im2 = pil_image.convert("RGBA")
    data = im2.tobytes("raw", "BGRA")
    qim = QImage(data, im2.width, im2.height, QImage.Format.Format_ARGB32)
    return QPixmap.fromImage(qim)


    qim = QImage(data, im2.width, im2.height, QImage.Format.Format_ARGB32)
    return QPixmap.fromImage(qim)


class FastTooltipStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return 50  # 50ms delay (almost instant)
        return super().styleHint(hint, option, widget, returnData)


class DarkLoadingDialog(QProgressDialog):
    def __init__(self, title, label_text, parent=None):
        super().__init__(label_text, None, 0, 100, parent) # No cancel button for now
        self.setWindowTitle(title)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumDuration(0)
        self.setMinimumWidth(400)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        self.setAutoClose(True)
        self.setAutoReset(True)
        
        # Style matching the user request
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
                font-family: "Segoe UI", sans-serif;
                font-size: 14px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            QProgressBar {
                border: 1px solid #333;
                border-radius: 6px;
                text-align: center;
                background-color: #1e1e1e;
                color: #eee;
            }
            QProgressBar::chunk {
                background-color: #0d47a1;
                border-radius: 5px;
            }
        """)

class ExtendedAttributesDialog(QWidget):
    def __init__(self, attribs, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.attribs = attribs
        self.setWindowTitle("Extended Attributes (13+)")
        self.setFixedSize(500, 450)
        self.init_ui()
        self.apply_styles()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Group similar to the main interface Attributes
        grp = QGroupBox("13+ Features")
        grp_layout = QGridLayout(grp)
        
        # 1. Attributes with Values
        # Upgrade Classification
        self.chk_upgrade = QCheckBox("Upgrade Classification")
        self.chk_upgrade.stateChanged.connect(lambda s: self.inp_upgrade.setEnabled(s == 2))
        self.chk_upgrade.setToolTip("ID 53: Classificação de Upgrade (0-255)")
        self.inp_upgrade = QSpinBox()
        self.inp_upgrade.setRange(0, 255)
        self.inp_upgrade.setFixedWidth(80)
        self.inp_upgrade.setEnabled(False)
        
        # Changed To Expire (Item ID)
        self.chk_changedtoexpire = QCheckBox("Changed To Expire")
        self.chk_changedtoexpire.stateChanged.connect(lambda s: self.inp_changedtoexpire.setEnabled(s == 2))
        self.chk_changedtoexpire.setToolTip("ID 63: ID do item que se transformará ao expirar (Uint16)")
        self.inp_changedtoexpire = QSpinBox()
        self.inp_changedtoexpire.setRange(0, 65535)
        self.inp_changedtoexpire.setFixedWidth(80)
        self.inp_changedtoexpire.setEnabled(False)

        # Cyclopedia Item (Type)
        self.chk_cyclopedia = QCheckBox("Cyclopedia Item")
        self.chk_cyclopedia.stateChanged.connect(lambda s: self.inp_cyclopedia.setEnabled(s == 2))
        self.chk_cyclopedia.setToolTip("ID 64: Tipo do item na Cyclopedia (Uint16)")
        self.inp_cyclopedia = QSpinBox()
        self.inp_cyclopedia.setRange(0, 65535)
        self.inp_cyclopedia.setFixedWidth(80)
        self.inp_cyclopedia.setEnabled(False)

        grp_layout.addWidget(self.chk_upgrade, 0, 0)
        grp_layout.addWidget(self.inp_upgrade, 0, 1)
        grp_layout.addWidget(self.chk_changedtoexpire, 1, 0)
        grp_layout.addWidget(self.inp_changedtoexpire, 1, 1)
        grp_layout.addWidget(self.chk_cyclopedia, 2, 0)
        grp_layout.addWidget(self.inp_cyclopedia, 2, 1)

        # 2. Boolean Flags (Grid)
        flags_widget = QWidget()
        flags_layout = QGridLayout(flags_widget)
        flags_layout.setContentsMargins(0, 10, 0, 0)
        
        self.flags_chks = {}
        flags_list = [
            ("Wearout", "wearout", "ID 54"),
            ("Clock Expire", "clockExpire", "ID 55"),
            ("Expire", "expire", "ID 56"),
            ("Expire Stop", "expireStop", "ID 57"),
            ("Corpse", "corpse", "ID 58"),
            ("Player Corpse", "playerCorpse", "ID 59"),
            ("Ammo", "ammo", "ID 60"),
            ("ShowOff Socket", "showOffSocket", "ID 61"),
            ("Reportable", "reportable", "ID 62")
        ]
        
        row, col = 0, 0
        for label, key, tip in flags_list:
            chk = QCheckBox(label)
            chk.setToolTip(tip)
            self.flags_chks[key] = chk
            flags_layout.addWidget(chk, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1
        
        grp_layout.addWidget(flags_widget, 3, 0, 1, 2)
        layout.addWidget(grp)
        
        # Load initial values
        self._load_values()

        # Warning Label
        lbl_warning = QLabel("⚠️ <b>ATENÇÃO:</b> Estas flags funcionam apenas em <b>Clientes 13+</b>.<br>Ativar sem suporte pode causar <b>Debug/Crash</b>.")
        lbl_warning.setWordWrap(True)
        lbl_warning.setStyleSheet("color: #ffeb3b; font-size: 11px; margin-top: 5px;")
        layout.addWidget(lbl_warning)
        
        layout.addStretch()
        
        btn_box = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self.save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.close)
        
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

    def _load_values(self):
        # Upgrade
        if 'upgradeClassification' in self.attribs:
            self.chk_upgrade.setChecked(True)
            self.inp_upgrade.setValue(self.attribs['upgradeClassification'])
            self.inp_upgrade.setEnabled(True)
            
        # ChangedToExpire
        if 'changedToExpire' in self.attribs:
            self.chk_changedtoexpire.setChecked(True)
            self.inp_changedtoexpire.setValue(self.attribs['changedToExpire'])
            self.inp_changedtoexpire.setEnabled(True)
            
        # Cyclopedia
        if 'cyclopediaItem' in self.attribs:
            self.chk_cyclopedia.setChecked(True)
            self.inp_cyclopedia.setValue(self.attribs['cyclopediaItem'])
            self.inp_cyclopedia.setEnabled(True)
            
        # Booleans
        for key, chk in self.flags_chks.items():
            if self.attribs.get(key, False):
                chk.setChecked(True)

    def save(self):
        # Upgrade
        if self.chk_upgrade.isChecked(): self.attribs['upgradeClassification'] = self.inp_upgrade.value()
        elif 'upgradeClassification' in self.attribs: del self.attribs['upgradeClassification']
            
        # ChangedToExpire
        if self.chk_changedtoexpire.isChecked(): self.attribs['changedToExpire'] = self.inp_changedtoexpire.value()
        elif 'changedToExpire' in self.attribs: del self.attribs['changedToExpire']
            
        # Cyclopedia
        if self.chk_cyclopedia.isChecked(): self.attribs['cyclopediaItem'] = self.inp_cyclopedia.value()
        elif 'cyclopediaItem' in self.attribs: del self.attribs['cyclopediaItem']
        
        # Booleans
        for key, chk in self.flags_chks.items():
            if chk.isChecked():
                self.attribs[key] = True
            elif key in self.attribs:
                del self.attribs[key]
                
        self.close()

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget { background-color: #121212; color: #e0e0e0; font-family: "Segoe UI"; }
            QGroupBox { border: 1px solid #333; border-radius: 6px; margin-top: 24px; background-color: #1a1a1a; font-weight: bold; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 4px 10px; background-color: #0d47a1; color: white; border-radius: 6px; }
            QCheckBox { spacing: 8px; color: #ccc; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #555; border-radius: 3px; background: #252525; }
            QCheckBox::indicator:checked { background-color: #0d47a1; border-color: #0d47a1; }
            QSpinBox { background-color: #252525; border: 1px solid #3d3d3d; border-radius: 4px; padding: 4px; color: #fff; }
            QSpinBox:disabled { color: #555; border-color: #222; }
            QPushButton { background-color: #252525; border: 1px solid #333; color: #e0e0e0; padding: 6px; border-radius: 4px; font-weight: 600; }
            QPushButton:hover { background-color: #333; }
            QPushButton:pressed { background-color: #0d47a1; }
        """)


class OtbEditorTab(QWidget):
    def __init__(self, datspr_module=None):
        super().__init__()
        self.datspr_module = datspr_module
        self.otb_root = None
        self.current_node = None
        self.item_nodes = [] 
        self.item_nodes = [] 
        
        # Settings
        self.settings = QSettings("TibiaItemManager", "OtbEditor")

        # Apply Fast Tooltips
        QApplication.setStyle(FastTooltipStyle(QApplication.style()))
        
        self.init_ui()
        self.create_menu_bar()

    def create_menu_bar(self):
        # Create Menu Bar
        self.menu_bar = QMenuBar(self)
        self.layout().setMenuBar(self.menu_bar)

        # File Menu
        file_menu = self.menu_bar.addMenu("File")
        
        load_action = QAction("Open...", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self.load_otb)
        file_menu.addAction(load_action)

        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_otb)
        file_menu.addAction(save_action)
        
        # Edit Menu
        edit_menu = self.menu_bar.addMenu("Edit")
        
        create_action = QAction("Create Item", self)
        create_action.setShortcut("Ctrl+I")
        create_action.triggered.connect(self.create_item)
        edit_menu.addAction(create_action)
        
        dup_action = QAction("Duplicate Item", self)
        dup_action.setShortcut("Ctrl+D")
        dup_action.triggered.connect(self.duplicate_item)
        edit_menu.addAction(dup_action)
        
        reload_action = QAction("Reload Item", self)
        reload_action.setShortcut("Ctrl+R")
        reload_action.triggered.connect(self.reload_current_item)
        edit_menu.addAction(reload_action)
        
        edit_menu.addSeparator()
        
        missing_action = QAction("Create Missing Items", self)
        missing_action.triggered.connect(self.create_missing_items)
        edit_menu.addAction(missing_action)
        
        find_action = QAction("Find Item", self)
        find_action.setShortcut("Ctrl+F")
        find_action.triggered.connect(self.open_find_dialog)
        edit_menu.addAction(find_action)

        # View Menu
        view_menu = self.menu_bar.addMenu("View")
        # Placeholders for now
        view_menu.addAction("Show Mismatched Items (TODO)")
        view_menu.addAction("Show Deprecated Items (TODO)")
        
        # Tools Menu
        tools_menu = self.menu_bar.addMenu("Tools")
        
        reload_attrs = QAction("Reload Item Attributes", self)
        reload_attrs.triggered.connect(self.reload_all_attributes)
        tools_menu.addAction(reload_attrs)

        # Help Menu
        help_menu = self.menu_bar.addMenu("Help")
        about_action = QAction("About ItemEditor", self)
        about_action.triggered.connect(lambda: QMessageBox.information(self, "About", "ItemManager OTB Editor\nBased on ItemEditor 0.5"))
        help_menu.addAction(about_action)

    def init_ui(self):
        self.apply_styles()
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        main_layout.addWidget(splitter)
        
        # ... (rest of init_ui stays logic wise, but let's refresh the whole start) ...

    def apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a2e;
                color: #e0e0e0;
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
            }
            
            QToolTip {
                background-color: #2a2a3e;
                color: #ffffff;
                border: 1px solid #4a90e2;
                padding: 4px;
                border-radius: 4px;
            }
            
            /* GroupBox */
            QGroupBox {
                border: 1px solid rgba(74, 144, 226, 0.3);
                border-radius: 8px;
                margin-top: 24px;
                background-color: rgba(30, 30, 46, 0.8);
                font-weight: bold;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 4px 12px;
                background-color: #4a90e2;
                color: white;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                border: 1px solid #4a90e2;
            }
            
            /* Inputs */
            QLineEdit, QSpinBox, QComboBox {
                background-color: #16213e;
                border: 1px solid rgba(74, 144, 226, 0.3);
                border-radius: 6px;
                padding: 6px 10px;
                color: #fff;
                selection-background-color: #4a90e2;
            }
            QLineEdit:hover, QSpinBox:hover, QComboBox:hover {
                border-color: #4a90e2;
                background-color: #1e2a4a;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border: 2px solid #4a90e2;
                background-color: #16213e;
            }
            
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #4a90e2;
            }
            
            /* Checkbox */
            QCheckBox {
                spacing: 8px;
                color: #ccc;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #4a90e2;
                border-radius: 4px;
                background: #16213e;
            }
            QCheckBox::indicator:unchecked:hover {
                border-color: #5ba0f2;
                background: #1e2a4a;
            }
            QCheckBox::indicator:checked {
                background-color: #4a90e2;
                border-color: #4a90e2;
            }
            
            /* Tree Widget */
            QTreeWidget {
                background-color: #16213e;
                border: 1px solid rgba(74, 144, 226, 0.3);
                border-radius: 8px;
                alternate-background-color: #1a2540;
                padding: 5px;
            }
            QTreeWidget::item {
                padding: 5px;
                border-radius: 4px;
            }
            QTreeWidget::item:hover {
                background-color: rgba(74, 144, 226, 0.2);
            }
            QTreeWidget::item:selected {
                background-color: #4a90e2;
                color: white;
            }
            
            /* Splitter */
            QSplitter::handle {
                background-color: rgba(74, 144, 226, 0.3);
            }
            QSplitter::handle:hover {
                background-color: #4a90e2;
            }
            
            /* Scrollbars */
            QScrollBar:vertical {
                border: none;
                background: #1a1a2e;
                width: 10px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(74, 144, 226, 0.5);
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #4a90e2;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            
            /* Buttons */
            QPushButton {
                background-color: #16213e;
                border: 1px solid rgba(74, 144, 226, 0.3);
                color: #e0e0e0;
                padding: 8px 18px;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: rgba(74, 144, 226, 0.3);
                border-color: #4a90e2;
            }
            QPushButton:pressed {
                background-color: #4a90e2;
                border-color: #4a90e2;
            }
            
            /* Menu Bar */
            QMenuBar {
                background-color: #16213e;
                color: #e0e0e0;
                border-bottom: 1px solid rgba(74, 144, 226, 0.3);
            }
            QMenuBar::item:selected {
                background-color: #4a90e2;
            }
            QMenu {
                background-color: #1a1a2e;
                border: 1px solid rgba(74, 144, 226, 0.3);
            }
            QMenu::item:selected {
                background-color: #4a90e2;
            }
            
            /* PlainTextEdit (Console) */
            QPlainTextEdit {
                background-color: #0d1117;
                color: #00ff00;
                font-family: Consolas, monospace;
                border: 1px solid rgba(74, 144, 226, 0.3);
                border-radius: 6px;
            }
        """)

    def init_ui(self):
        self.apply_styles()
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        main_layout.addWidget(splitter)
        
        # --- LEFT PANEL: Item List ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.search_inp = QLineEdit()
        self.search_inp.setPlaceholderText("Search Item...")
        self.search_inp.textChanged.connect(self.filter_tree)
        left_layout.addWidget(self.search_inp)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(10)
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.open_context_menu)
        left_layout.addWidget(self.tree)
        
        splitter.addWidget(left_widget)
        
        # --- RIGHT PANEL: Content Area ---
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        # Upper Section: Appearance | Attributes (Flags + Props)
        upper_widget = QWidget()
        upper_layout = QHBoxLayout(upper_widget)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. Appearance Column (Fixed Width)
        app_grp = QGroupBox("Appearance")
        app_grp.setFixedWidth(180)
        app_layout = QVBoxLayout(app_grp)
        
        # Previous
        app_layout.addWidget(QLabel("Previous:"))
        self.lbl_prev_sprite = QLabel()
        self.lbl_prev_sprite.setFixedSize(64, 64)
        self.lbl_prev_sprite.setStyleSheet("border: 1px solid #444; background: #222;")
        self.lbl_prev_sprite.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_layout.addWidget(self.lbl_prev_sprite)
        
        # Current
        app_layout.addWidget(QLabel("Current:"))
        self.lbl_preview = QLabel()
        self.lbl_preview.setFixedSize(64, 64)
        self.lbl_preview.setStyleSheet("border: 1px solid #444; background: #222;")
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_layout.addWidget(self.lbl_preview)
        
        app_layout.addSpacing(10)
        
        # IDs
        app_layout.addWidget(QLabel("Server ID:"))
        self.inp_server_id = QSpinBox(); self.inp_server_id.setRange(0, 65535)
        self.inp_server_id.valueChanged.connect(self.on_prop_change)
        app_layout.addWidget(self.inp_server_id)
        
        app_layout.addWidget(QLabel("Client ID:"))
        self.inp_client_id = QSpinBox(); self.inp_client_id.setRange(0, 65535)
        self.inp_client_id.valueChanged.connect(self.on_client_id_change)
        app_layout.addWidget(self.inp_client_id)
        
        app_layout.addStretch()
        upper_layout.addWidget(app_grp)
        
        # 2. Attributes & Properties (Main Area)
        data_grp = QGroupBox("Attributes & Properties")
        data_layout = QHBoxLayout(data_grp) # Horizontal: Flags | Props
        
        # A) Flags (Checkboxes)
        flags_widget = QWidget()
        flags_grid = QGridLayout(flags_widget)
        flags_grid.setVerticalSpacing(5)
        self.flags_mapping = []
        
        flag_names = [
            ("Unpassable", FLAG_BLOCK_SOLID), ("Block Missiles", FLAG_BLOCK_PROJECTILE),
            ("Block Path", FLAG_BLOCK_PATHFIND), ("Has Height", FLAG_HAS_HEIGHT),
            ("Useable", FLAG_USEABLE), ("Pickupable", FLAG_PICKUPABLE),
            ("Movable", FLAG_MOVEABLE), ("Stackable", FLAG_STACKABLE),
            ("FloorChange Down", FLAG_FLOORCHANGE_DOWN), ("FloorChange North", FLAG_FLOORCHANGE_NORTH),
            ("FloorChange East", FLAG_FLOORCHANGE_EAST), ("FloorChange South", FLAG_FLOORCHANGE_SOUTH),
            ("FloorChange West", FLAG_FLOORCHANGE_WEST), ("Always Top", FLAG_ALWAYS_ON_TOP),
            ("Readable", FLAG_READABLE), ("Rotatable", FLAG_ROTATABLE),
            ("Hangable", FLAG_HANGABLE), ("Vertical", FLAG_VERTICAL),
            ("Horizontal", FLAG_HORIZONTAL), ("Cannot Decay", FLAG_CANNOT_DECAY),
            ("Allow DistRead", FLAG_ALLOW_DISTREAD), ("Client Charges", FLAG_CLIENT_CHARGES),
            ("Ignore Look", FLAG_IGNORE_LOOK), ("Animation", FLAG_IS_ANIMATION),
            ("Full Ground", FLAG_FULL_GROUND), ("Force Use", FLAG_FORCE_USE)
        ]
        
        # 2 Columns of flags
        r, c = 0, 0
        for name, val in flag_names:
            chk = QCheckBox(name)
            chk.stateChanged.connect(self.on_flag_change)
            chk.setStyleSheet("QCheckBox::indicator:checked { background-color: #d32f2f; border: 1px solid #b71c1c; }")
            flags_grid.addWidget(chk, r, c)
            self.flags_mapping.append((chk, val))
            r += 1
            if r > 12: # Break to next col
                r = 0
                c += 1
        
        data_layout.addWidget(flags_widget)
        
        # B) Properties (Inputs)
        props_widget = QWidget()
        props_form = QFormLayout(props_widget)
        props_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.inp_name = QLineEdit()
        self.inp_name.textChanged.connect(self.on_prop_change)
        props_form.addRow("Name:", self.inp_name)
        
        self.inp_type = QComboBox() 
        self.inp_type.addItems(["None", "Ground", "Container", "Weapon", "Ammunition", "Armor", "Charges", "Teleport", "MagicField", "Writeable", "Key", "Splash", "Fluid", "Door", "Deprecated", "Depot"])
        self.inp_type.currentIndexChanged.connect(self.on_prop_change)
        props_form.addRow("Type:", self.inp_type)

        self.inp_stack_order = QComboBox(); self.inp_stack_order.addItems(["None", "Border", "Bottom", "Top"])
        self.inp_stack_order.currentIndexChanged.connect(self.on_prop_change)
        props_form.addRow("Stack Order:", self.inp_stack_order)

        self.inp_weight = QSpinBox(); self.inp_weight.setRange(0, 999999)
        self.inp_weight.valueChanged.connect(self.on_prop_change)
        props_form.addRow("Weight:", self.inp_weight)
        
        self.inp_wareid = QSpinBox(); self.inp_wareid.setRange(0, 65535)
        self.inp_wareid.valueChanged.connect(self.on_prop_change)
        props_form.addRow("Ware ID:", self.inp_wareid)

        self.inp_armor = QSpinBox(); self.inp_armor.setRange(0, 999999)
        self.inp_armor.valueChanged.connect(self.on_prop_change)
        props_form.addRow("Armor:", self.inp_armor)
        
        self.inp_defense = QSpinBox(); self.inp_defense.setRange(0, 999999)
        self.inp_defense.valueChanged.connect(self.on_prop_change)
        props_form.addRow("Defense:", self.inp_defense)
        
        self.inp_attack = QSpinBox(); self.inp_attack.setRange(0, 999999)
        self.inp_attack.valueChanged.connect(self.on_prop_change)
        props_form.addRow("Attack:", self.inp_attack)

        self.inp_speed = QSpinBox(); self.inp_speed.setRange(0, 999999)
        self.inp_speed.valueChanged.connect(self.on_prop_change)
        props_form.addRow("Speed:", self.inp_speed)
        
        self.inp_light_level = QSpinBox(); self.inp_light_level.setRange(0, 255)
        self.inp_light_level.valueChanged.connect(self.on_prop_change)
        props_form.addRow("Light Level:", self.inp_light_level)

        self.inp_light_color = QSpinBox(); self.inp_light_color.setRange(0, 255)
        self.inp_light_color.valueChanged.connect(self.on_prop_change)
        props_form.addRow("Light Color:", self.inp_light_color)

        self.inp_minimap_color = QSpinBox(); self.inp_minimap_color.setRange(0, 65535)
        self.inp_minimap_color.valueChanged.connect(self.on_prop_change)
        props_form.addRow("Minimap Color:", self.inp_minimap_color)
        
        # Extended Attributes Button
        btn_extended = QPushButton("Extended Attributes (13+)")
        btn_extended.clicked.connect(self.open_extended_attributes)
        btn_extended.setStyleSheet("background-color: #004d40; border-color: #00695c;") # Teal accent
        props_form.addRow(btn_extended)
        
        data_layout.addWidget(props_widget)
        
        # Add Data Group to Upper Layout
        upper_layout.addWidget(data_grp)
        
        # Add Upper Section to Right Layout
        right_layout.addWidget(upper_widget)
        
        # Console Log (Bottom of Right Panel)
        self.console_log = QPlainTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setMaximumHeight(150)
        self.console_log.setPlaceholderText(">> System Log...")
        
        right_layout.addWidget(QLabel("Console Output:"))
        right_layout.addWidget(self.console_log)

        # Tools Buttons
        tools_layout = QHBoxLayout()
        btn_scan = QPushButton("Scan All (Log)")
        btn_scan.clicked.connect(self.scan_otb)
        btn_debug = QPushButton("Debug Node")
        btn_debug.clicked.connect(self.debug_current_node)
        tools_layout.addWidget(btn_scan)
        tools_layout.addWidget(btn_debug)
        right_layout.addLayout(tools_layout)
        
        splitter.addWidget(right_container)
        splitter.setSizes([250, 750])

    def log(self, text):
        self.console_log.appendPlainText(f">> {text}")

    # --- Feature Implementations ---

    def create_item(self):
        if not self.otb_root: return
        
        # Find max Server ID
        max_sid = 0
        for node in self.item_nodes:
            sid = node.attribs.get('serverId', 0)
            if sid > max_sid: max_sid = sid
            
        new_sid = max_sid + 1
        
        # Create new node
        new_node = OTBNode()
        new_node.type = 0 # ItemGroup None? Or normal item type? 
        # Usually type denotes group (Container, etc). Default to None (0) or Item
        
        new_node.attribs['serverId'] = new_sid
        new_node.attribs['clientId'] = 0 # Default
        
        self.otb_root.add_child(new_node)
        self.item_nodes.append(new_node)
        
        # Add to Tree
        root = self.tree.invisibleRootItem()
        self.add_tree_item(new_node, root)
        
        self.log(f"Created Item {new_sid}")

    def duplicate_item(self):
        if not self.current_node: return
        
        # Find max Server ID
        max_sid = 0
        for node in self.item_nodes:
            sid = node.attribs.get('serverId', 0)
            if sid > max_sid: max_sid = sid
            
        new_sid = max_sid + 1
        
        # Deep copy node logic (manual copy of attributes)
        import copy
        new_node = OTBNode()
        new_node.type = self.current_node.type
        new_node.attribs = copy.deepcopy(self.current_node.attribs)
        new_node.attribs['serverId'] = new_sid
        
        # Copy raw props? 
        # Ideally we re-serialize attribs, so raw_props might be stale.
        # But let's copy them just in case
        new_node.raw_props = copy.deepcopy(self.current_node.raw_props)
        if 16 in new_node.raw_props: del new_node.raw_props[16] # Remove old ID from raw
        
        self.otb_root.add_child(new_node)
        self.item_nodes.append(new_node)
        
        root = self.tree.invisibleRootItem()
        self.add_tree_item(new_node, root)
        
        self.log(f"Duplicated Item {self.current_node.attribs.get('serverId')} to {new_sid}")

    def create_missing_items(self):
        if not self.datspr_module or not self.datspr_module.editor:
            QMessageBox.warning(self, "Error", "Load Tibia.dat first!")
            return
            
        items_map = self.datspr_module.editor.things.get("items", {})
        if not items_map: return
        
        max_cid_dat = max(items_map.keys()) if items_map else 0
        
        # Find existing Client IDs in OTB
        existing_cids = set()
        max_sid = 0
        for node in self.item_nodes:
            cid = node.attribs.get('clientId', 0)
            sid = node.attribs.get('serverId', 0)
            existing_cids.add(cid)
            if sid > max_sid: max_sid = sid
            
        created_count = 0
        # Start from 100 usually
        for cid in range(100, max_cid_dat + 1):
            if cid not in existing_cids:
                # Create it
                new_node = OTBNode()
                new_node.type = 0 # Default type
                
                max_sid += 1
                new_node.attribs['serverId'] = max_sid
                new_node.attribs['clientId'] = cid
                
                # Try to sync basic attributes from DAT?
                # For now just create blank link
                
                self.otb_root.add_child(new_node)
                self.item_nodes.append(new_node)
                
                root = self.tree.invisibleRootItem()
                self.add_tree_item(new_node, root)
                created_count += 1
                
        self.log(f"Created {created_count} missing items.")

    def open_find_dialog(self):
        text, ok = QInputDialog.getText(self, "Find Item", "Enter Item ID (Server) or Name:")
        if ok and text:
            # Search
            search_term = text.lower()
            found_items = []
            
            # Simple linear search
            iterator = QTreeWidgetItemIterator(self.tree)
            while iterator.value():
                item = iterator.value()
                node = item.data(0, Qt.ItemDataRole.UserRole)
                if node:
                    sid = str(node.attribs.get('serverId', 0))
                    name = node.attribs.get('name', '').lower()
                    
                    if search_term == sid or search_term in name:
                        self.tree.setCurrentItem(item)
                        self.tree.scrollToItem(item)
                        self.on_item_clicked(item, 0)
                        return # Stop at first match or implementation next button?
                iterator += 1
            
            QMessageBox.information(self, "Find", "Item not found.")

    def reload_current_item(self):
        pass # Placeholder for "Sync with DAT" logic
    
    def reload_all_attributes(self):
        # Placeholder for future implementation
        self.log("Reloading all attributes... (Not implemented yet)")

    def log(self, message):
        self.console_log.appendPlainText(f">> {message}")

    def load_otb(self):
        if not self.datspr_module or not self.datspr_module.editor or not self.datspr_module.spr:
            QMessageBox.warning(self, "Requirement", "Please load Tibia.dat and Tibia.spr first!")
            return



        last_path = self.settings.value("last_otb_path", "")
        start_dir = os.path.dirname(last_path) if last_path else ""

        path, _ = QFileDialog.getOpenFileName(self, "Load OTB", start_dir, "OTB Files (*.otb);;All Files (*)")
        if not path: return
        
        self.settings.setValue("last_otb_path", path)
        
        self.log(f"Loading {path}...")
        
        # 1. Parse Phase (Indeterminate)
        progress = DarkLoadingDialog("Load OTB", "Parsing OTB structure...", self)
        progress.setRange(0, 0) # Indeterminate
        progress.show()
        QApplication.processEvents()
        
        try:
            self.otb_root = OTBHandler.load(path)
            
            if self.otb_root:
                # 2. Populate Phase (Determinant)
                self.populate_tree(progress)
                self.log("OTB Loaded successfully.")
            else:
                progress.close()
                self.log("Failed to parse OTB.")
        except Exception as e:
            progress.close()
            self.log(f"Error: {e}")

    def populate_tree(self, progress_dialog=None):
        self.tree.clear()
        if not self.otb_root: return
        
        if progress_dialog:
            progress_dialog.setLabelText("Collecting item nodes...")
            progress_dialog.setRange(0, 0)
            QApplication.processEvents()
        
        self.item_nodes = []
        
        def traverse(node):
            if 'serverId' in node.attribs or 'clientId' in node.attribs:
                self.item_nodes.append(node)
            for child in node.children:
                traverse(child)
                
        traverse(self.otb_root)
        
        total_items = len(self.item_nodes)
        
        if progress_dialog:
            progress_dialog.setRange(0, total_items)
            progress_dialog.setValue(0)
            progress_dialog.setLabelText(f"Populating Item List (0/{total_items})...")
            QApplication.processEvents()
        
        root = self.tree.invisibleRootItem()
        unnamed_count = 0
        
        # Batch updates for performance
        updates_per_frame = 100 
        
        for i, node in enumerate(self.item_nodes):
            # FILTER: Skip items with Client ID 0 (empty sprites) as requested
            cid = node.attribs.get('clientId', 0)
            if cid != 0:
                self.add_tree_item(node, root)
                if 'name' not in node.attribs or not node.attribs['name']:
                    unnamed_count += 1
            
            if progress_dialog and i % updates_per_frame == 0:
                progress_dialog.setValue(i)
                progress_dialog.setLabelText(f"Populating Item List ({i}/{total_items})...")
                QApplication.processEvents()
                if progress_dialog.wasCanceled():
                    break
                    
        if progress_dialog:
            progress_dialog.setValue(total_items)
            progress_dialog.close()
                
        self.log(f"Loaded {len(self.item_nodes)} items.")
        if unnamed_count > 0:
            self.log(f"{unnamed_count} items are unnamed (Displayed as Item ID).")
            
    def add_tree_item(self, node, parent):
        sid = node.attribs.get('serverId', 0)
        cid = node.attribs.get('clientId', 0)
        name = node.attribs.get('name', '')
        
        # Format similar to reference: [Icon] 100 - Name
        display_text = f"{sid} - {name}" if name else f"{sid} - Item {cid}"
        if sid == 0: display_text = f"{cid} (Client ID) - {name}" if name else f"{cid} (Client ID)"
        
        item = QTreeWidgetItem(parent)
        item.setText(0, display_text)
        
        if cid > 0:
            pil_img = self.get_node_sprite(cid)
            if pil_img:
                icon_pm = pil_to_qpixmap(pil_img.resize((32, 32), Image.NEAREST))
                item.setIcon(0, QIcon(icon_pm))

        item.setData(0, Qt.ItemDataRole.UserRole, node)

    # ... get_node_sprite, on_item_clicked, update_node similar but mapping new fields ...
    def get_node_sprite(self, client_id):
        if not self.datspr_module: return None
        if not self.datspr_module.editor: return None
        try:
            if "items" in self.datspr_module.editor.things and client_id in self.datspr_module.editor.things["items"]:
                item = self.datspr_module.editor.things["items"][client_id]
                from datspr import DatEditor
                sprite_ids = DatEditor.extract_sprite_ids_from_texture_bytes(item["texture_bytes"])
                if sprite_ids and sprite_ids[0] > 0:
                    img = self.datspr_module.spr.get_sprite(sprite_ids[0])
                    return img
        except: pass
        return None

    def on_item_clicked(self, item, col):
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if node:
            self.current_node = node
            self.inp_server_id.setValue(node.attribs.get('serverId', 0))
            self.inp_client_id.setValue(node.attribs.get('clientId', 0))
            
            # Map flags
            flags = node.attribs.get('flags', 0)
            for chk, flag_val in self.flags_mapping:
                chk.setChecked(bool(flags & flag_val))
                
            # Props
            self.inp_name.setText(node.attribs.get('name', ''))
            self.inp_weight.setValue(node.attribs.get('weight', 0))
            self.inp_speed.setValue(node.attribs.get('speed', 0))
            self.inp_armor.setValue(node.attribs.get('armor', 0))
            self.inp_attack.setValue(node.attribs.get('attack', 0))
            self.inp_light_level.setValue(node.attribs.get('lightLevel', 0))
            self.inp_light_color.setValue(node.attribs.get('lightColor', 0))
            self.inp_minimap_color.setValue(node.attribs.get('minimapColor', 0))
            self.inp_wareid.setValue(node.attribs.get('wareId', 0))
            
            # Update Preview
            self.update_preview_from_input()
            
            # Check for Flag Mismatches
            self.check_flag_mismatches()

    def check_flag_mismatches(self):
        if not self.current_node: return
        cid = self.current_node.attribs.get('clientId', 0)
        
        dat_props = {}
        # Access dat editor via datspr_module
        if hasattr(self, 'datspr_module') and self.datspr_module and self.datspr_module.editor:
             if "items" in self.datspr_module.editor.things and cid in self.datspr_module.editor.things["items"]:
                 dat_props = self.datspr_module.editor.things["items"][cid].get("props", {})

        # Mapping OTB Flag -> Dat Prop Key
        mapping = {
            FLAG_FULL_GROUND: "FullGround",
            FLAG_BLOCK_SOLID: "Unpassable",
            FLAG_BLOCK_PROJECTILE: "BlockMissile",
            FLAG_BLOCK_PATHFIND: "BlockPathfind",
            FLAG_PICKUPABLE: "Pickupable",
            FLAG_STACKABLE: "Stackable",
            FLAG_FORCE_USE: "ForceUse",
            FLAG_ROTATABLE: "Rotatable",
            FLAG_HANGABLE: "Hangable",
            FLAG_HAS_HEIGHT: "HasElevation",
            FLAG_ALWAYS_ON_TOP: "OnTop",
        }
        
        # Inverted Logic Mappings (OTB=True <=> DAT=False)
        inverted_mapping = {
            FLAG_MOVEABLE: "Unmoveable" 
        }

        for chk, flag_val in self.flags_mapping:
            # Reset Style
            chk.setStyleSheet("QCheckBox::indicator:checked { background-color: #d32f2f; border: 1px solid #b71c1c; }")
            chk.setToolTip("")
            
            otb_state = chk.isChecked()
            
            if flag_val in mapping:
                dat_key = mapping[flag_val]
                dat_state = dat_key in dat_props
                
                # If OTB says TRUE, but DAT says FALSE -> Mismatch (Critical)
                if otb_state and not dat_state:
                     chk.setStyleSheet("QCheckBox { color: #ffeb3b; font-weight: bold; } QCheckBox::indicator:checked { background-color: #fbc02d; border: 1px solid #fbc02d; }")
                     chk.setToolTip(f"⚠️ AVISO: Esta flag está marcada no OTB, mas NÃO consta no arquivo .DAT ('{dat_key}').\nIsso pode gerar erros. Verifique se o item no .dat deveria ter '{dat_key}' ativo ou desmarque esta opção.")
            
            elif flag_val in inverted_mapping:
                dat_key = inverted_mapping[flag_val]
                dat_state = dat_key in dat_props
                
                # Mismatch: OTB Moveable (True) AND DAT Unmoveable (True)
                if otb_state and dat_state:
                     chk.setStyleSheet("QCheckBox { color: #ffeb3b; font-weight: bold; } QCheckBox::indicator:checked { background-color: #fbc02d; border: 1px solid #fbc02d; }")
                     chk.setToolTip(f"⚠️ CONFLITO DE LÓGICA:\nNo OTB está como 'Movable' (pode mover), mas o cliente tem a flag '{dat_key}' (não pode mover) ativada.\nO item não poderá ser movido no jogo.")
            
    def update_preview_from_input(self):
        cid = self.inp_client_id.value()
        if cid > 0:
            pil_img = self.get_node_sprite(cid)
            if pil_img:
                pm = pil_to_qpixmap(pil_img.resize((64, 64), Image.NEAREST))
                self.lbl_preview.setPixmap(pm)
            else:
                self.lbl_preview.clear()
        else:
            self.lbl_preview.clear()

    def save_otb(self):
        if not self.otb_root: return
        path, _ = QFileDialog.getSaveFileName(self, "Save OTB", "", "OTB Files (*.otb)")
        if not path: return
        OTBHandler.save(self.otb_root, path)
        self.log("Saved OTB file.")
            
    def filter_tree(self, text):
        search_term = text.lower()
        root = self.tree.invisibleRootItem()
        child_count = root.childCount()
        
        for i in range(child_count):
            item = root.child(i)
            if not search_term:
                item.setHidden(False)
            else:
                item.setHidden(search_term not in item.text(0).lower())

    def open_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item: return
        
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if not node: return
        
        menu = QMenu()
        menu.setStyleSheet("QMenu { background-color: #252525; border: 1px solid #444; color: white; } QMenu::item:selected { background-color: #0d47a1; }")
        
        dup_action = menu.addAction("Duplicate")
        dup_action.triggered.connect(self.duplicate_item)
        
        reload_action = menu.addAction("Reload")
        reload_action.triggered.connect(self.reload_current_item)
        
        menu.addSeparator()
        
        sid = node.attribs.get('serverId', 0)
        cid = node.attribs.get('clientId', 0)
        name = node.attribs.get('name', 'Item')
        
        cp_sid = menu.addAction(f"Copy Server ID ({sid})")
        cp_sid.triggered.connect(lambda: QApplication.clipboard().setText(str(sid)))
        
        cp_cid = menu.addAction(f"Copy Client ID ({cid})")
        cp_cid.triggered.connect(lambda: QApplication.clipboard().setText(str(cid)))
        
        cp_name = menu.addAction(f"Copy Name ('{name}')")
        cp_name.triggered.connect(lambda: QApplication.clipboard().setText(name))
        
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def open_extended_attributes(self):
        if not self.current_node: return
        dlg = ExtendedAttributesDialog(self.current_node.attribs, self)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.show()
        
    def on_prop_change(self):
        # Update current node attributes from UI
        if not self.current_node: return
        # Safety check: ensure all widgets are initialized before accessing them
        if not hasattr(self, 'inp_type'): return
        
        # Appearance
        self.current_node.attribs['serverId'] = self.inp_server_id.value()
        
        # Props
        name = self.inp_name.text()
        if name: self.current_node.attribs['name'] = name
        elif 'name' in self.current_node.attribs: del self.current_node.attribs['name']
        
        self.current_node.attribs['weight'] = self.inp_weight.value()
        self.current_node.attribs['speed'] = self.inp_speed.value()
        self.current_node.attribs['armor'] = self.inp_armor.value()
        self.current_node.attribs['attack'] = self.inp_attack.value()
        self.current_node.attribs['lightLevel'] = self.inp_light_level.value()
        self.current_node.attribs['lightColor'] = self.inp_light_color.value()
        self.current_node.attribs['minimapColor'] = self.inp_minimap_color.value()
        self.current_node.attribs['wareId'] = self.inp_wareid.value()
        
        # Update tree text if Server ID changed
        current_item = self.tree.currentItem()
        if current_item:
            sid = self.current_node.attribs.get('serverId', 0)
            cid = self.current_node.attribs.get('clientId', 0)
            name_txt = self.current_node.attribs.get('name', '')
            display_text = f"{sid} - {name_txt}" if name_txt else f"{sid} - Item {cid}"
            if sid == 0: display_text = f"{cid} (Client ID) - {name_txt}" if name_txt else f"{cid} (Client ID)"
            current_item.setText(0, display_text)

    def on_client_id_change(self):
        if not self.current_node: return
        self.current_node.attribs['clientId'] = self.inp_client_id.value()
        self.update_preview_from_input()
        self.check_flag_mismatches()
        self.on_prop_change() # Update tree text

    def on_flag_change(self):
        if not self.current_node: return
        
        flags = 0
        for chk, val in self.flags_mapping:
            if chk.isChecked():
                flags |= val
        
        self.current_node.attribs['flags'] = flags

    def update_node(self):
        self.on_prop_change()
        self.on_flag_change()
        self.on_flag_change()
        self.check_flag_mismatches()
        self.on_client_id_change()
        self.log("Node updated in memory (Save to persist).")

    def scan_otb(self):
        if not self.otb_root: return
        self.log("Scanning OTB structure...")
        
        node_count = 0
        max_sid = 0
        
        def traverse(node):
            nonlocal node_count, max_sid
            node_count += 1
            if 'serverId' in node.attribs:
                if node.attribs['serverId'] > max_sid: max_sid = node.attribs['serverId']
            for child in node.children:
                traverse(child)
                
        traverse(self.otb_root)
        self.log(f"Scan complete. Total Nodes: {node_count}. Max Server ID: {max_sid}")

    def debug_current_node(self):
        if not self.current_node: 
            self.log("No node selected to debug.")
            return

        node = self.current_node
        self.console_log.clear()
        self.log("=== ITEM DEBUG ===")
        self.log(f"Node Type: {node.type}")
        self.log(f"Current Parsed SID: {node.attribs.get('serverId', 'Not Found')}")
        self.log(f"Current Parsed CID: {node.attribs.get('clientId', 'Not Found')}")
        self.log(f"Parsed Attributes: {list(node.attribs.keys())}")
        
        # Analyze Raw Props
        self.log("--- Raw Property Analysis ---")
        p = io.BytesIO(node.props)
        raw_attrs_found = []
        while True:
            attr_byte = p.read(1)
            if not attr_byte: break
            attr = attr_byte[0]
            size_b = p.read(2)
            if len(size_b) < 2: break
            size = struct.unpack('<H', size_b)[0]
            data = p.read(size)
            
            raw_attrs_found.append(f"ID {attr} (len {len(data)})")
            
            # Specific check for ServerID (16)
            if attr == 16:
                val = struct.unpack('<H', data[:2])[0] if len(data) >= 2 else "ERR"
                self.log(f"-> FOUND SERVER_ID (16): Value = {val}")
        
        self.log(f"All Raw Attribute IDs in blob: {raw_attrs_found}")
        self.log("==================")

    def scan_otb(self):
        if not self.otb_root: return
        self.console_log.clear()
        self.log("Starting Full Diagnostic Scan...")
        
        total = 0
        zero_sid = 0
        no_cid = 0
        no_name = 0
        
        def traverse(node):
            nonlocal total, zero_sid, no_cid, no_name
            # Check only Item nodes (usually those with any attributes)
            if node.props: 
                total += 1
                sid = node.attribs.get('serverId', 0)
                cid = node.attribs.get('clientId', 0)
                name = node.attribs.get('name', '')
                
                if sid == 0: zero_sid += 1
                if cid == 0: no_cid += 1
                if not name: no_name += 1
            
            for child in node.children:
                traverse(child)
        
        traverse(self.otb_root)
        
        self.log(f"Scan Complete.")
        self.log(f"Total Nodes with Props: {total}")
        self.log(f"Nodes with ServerID 0: {zero_sid}")
        self.log(f"Nodes with ClientID 0: {no_cid}")
        self.log(f"Nodes Unnamed: {no_name}")
        
        if zero_sid == total:
             self.log("CRITICAL: All items have ServerID 0. This suggests the Parser is missing Attribute 16, or the file does not contain Server IDs (using ClientID mapping?).")
        elif zero_sid > 0:
             self.log("Warning: Some items have ServerID 0. This is common if they are not used or purely client-side.")

    def update_node(self):
        if self.current_node:
            node = self.current_node
            node.attribs['serverId'] = self.inp_server_id.value()
            node.attribs['clientId'] = self.inp_client_id.value()
            node.attribs['name'] = self.inp_name.text()
            node.attribs['weight'] = self.inp_weight.value()
            node.attribs['speed'] = self.inp_speed.value()
            node.attribs['armor'] = self.inp_armor.value()
            node.attribs['attack'] = self.inp_attack.value()
            node.attribs['lightLevel'] = self.inp_light_level.value()
            node.attribs['lightColor'] = self.inp_light_color.value()
            node.attribs['minimapColor'] = self.inp_minimap_color.value()
            node.attribs['wareId'] = self.inp_ware_id.value()
            
            flags = 0
            for chk, flag_val in self.flags_mapping:
                if chk.isChecked(): flags |= flag_val
            node.attribs['flags'] = flags
            
            self.log(f"Updated Node SID:{node.attribs['serverId']}")

