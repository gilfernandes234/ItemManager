import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QGridLayout, 
                             QLabel, QPushButton, QSizePolicy, QScrollArea)
from PyQt6.QtGui import QIcon, QCursor
from PyQt6.QtCore import Qt, QSize

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(BASE_DIR, "..", "assets", "window")

class ToolsTab(QWidget):
    def __init__(self, datspr_tab):
        super().__init__()
        self.datspr_tab = datspr_tab
        self.init_ui()

    def init_ui(self):
        # Main Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(25)

        # Centered Title/Header
        title_frame = QFrame()
        title_layout = QVBoxLayout(title_frame)
        title_layout.setContentsMargins(0, 0, 0, 20)
        title_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        lbl_title = QLabel("✨ Utility Tools")
        lbl_title.setStyleSheet("""
            font-size: 24px; 
            font-weight: bold; 
            color: #4a90e2;
        """)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(lbl_title)
        
        lbl_desc = QLabel("Access various generators and editors for Item Manager.")
        lbl_desc.setStyleSheet("color: #888; font-size: 13px;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.addWidget(lbl_desc)
        
        layout.addWidget(title_frame)

        # Tools Grid Container - Centered
        grid_container = QHBoxLayout()
        grid_container.addStretch()
        
        grid_frame = QFrame()
        grid_frame.setStyleSheet("""
            QFrame {
                background: rgba(22, 33, 62, 0.6);
                border: 1px solid rgba(74, 144, 226, 0.2);
                border-radius: 12px;
            }
        """)
        grid_frame.setMaximumWidth(800)
        
        grid_layout = QGridLayout(grid_frame)
        grid_layout.setContentsMargins(25, 25, 25, 25)
        grid_layout.setSpacing(12)

        # Tool Definitions: (Name, Icon, Tooltip, Callback, Color)
        tools = [
            ("🎨 Sprite Editor", "spriteEditor.png", "Extract and edit sprites", self.datspr_tab.open_sprite_editor, "#4a90e2"),
            ("⚡ Sprite Optimizer", "hash.png", "Optimize sprite storage", self.datspr_tab.open_sprite_optimizer, "#28a745"),
            ("👤 LookType Gen", "looktype.png", "Generate XML for LookTypes", self.datspr_tab.open_looktype_generator, "#9c27b0"),
            ("👾 Monster Gen", "monster.png", "Create custom monsters", self.datspr_tab.open_monster_generator, "#f44336"),
            ("✨ Spell Maker", "viewer_icon.png", "Design and test spells", self.datspr_tab.open_spell_maker, "#ff9800"),
            ("🔮 Shader Editor", "viewer_icon.png", "Edit client shaders", self.datspr_tab.open_shader, "#00bcd4"),
            ("💫 Particle Editor", "viewer_icon.png", "Edit particle effects", self.datspr_tab.open_particle, "#e91e63"),
        ]

        row = 0
        col = 0
        max_cols = 4

        for name, icon, tooltip, callback, color in tools:
            btn = self.create_tool_button(name, icon, tooltip, callback, color)
            grid_layout.addWidget(btn, row, col)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        grid_container.addWidget(grid_frame)
        grid_container.addStretch()
        layout.addLayout(grid_container)
        
        # Usplace Section (Beta)
        usplace_frame = QFrame()
        usplace_frame.setStyleSheet("""
            QFrame {
                background: rgba(74, 144, 226, 0.1);
                border: 1px dashed rgba(74, 144, 226, 0.4);
                border-radius: 12px;
            }
        """)
        usplace_frame.setMaximumWidth(800)
        
        usplace_layout = QVBoxLayout(usplace_frame)
        usplace_layout.setContentsMargins(20, 15, 20, 15)
        usplace_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        usplace_title = QLabel("🚀 Usplace")
        usplace_title.setStyleSheet("""
            font-size: 18px; 
            font-weight: bold; 
            color: #4a90e2;
        """)
        
        beta_label = QLabel("BETA")
        beta_label.setStyleSheet("""
            background-color: #ff9800;
            color: white;
            font-size: 10px;
            font-weight: bold;
            padding: 2px 8px;
            border-radius: 8px;
        """)
        beta_label.setFixedHeight(18)
        
        title_row = QHBoxLayout()
        title_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_row.addWidget(usplace_title)
        title_row.addWidget(beta_label)
        title_row.addStretch()
        
        usplace_desc = QLabel("Cloud sprite storage and sharing platform - Coming soon!")
        usplace_desc.setStyleSheet("color: #888; font-size: 12px;")
        
        usplace_layout.addLayout(title_row)
        usplace_layout.addWidget(usplace_desc)
        
        # Center the usplace frame
        usplace_container = QHBoxLayout()
        usplace_container.addStretch()
        usplace_container.addWidget(usplace_frame)
        usplace_container.addStretch()
        
        layout.addLayout(usplace_container)
        layout.addStretch()

    def create_tool_button(self, text, icon_name, tooltip, callback, color="#4a90e2"):
        btn = QPushButton(text)
        if icon_name:
            icon_file = os.path.join(ICON_PATH, icon_name)
            if os.path.exists(icon_file):
                btn.setIcon(QIcon(icon_file))
                
        btn.setIconSize(QSize(24, 24))
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(180, 45)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #16213e;
                border: 1px solid rgba(74, 144, 226, 0.3);
                border-left: 3px solid {color};
                border-radius: 8px;
                color: white;
                font-weight: 600;
                font-size: 12px;
                text-align: left;
                padding-left: 12px;
            }}
            QPushButton:hover {{
                background-color: rgba(74, 144, 226, 0.2);
                border: 1px solid {color};
                border-left: 3px solid {color};
            }}
            QPushButton:pressed {{
                background-color: {color};
            }}
        """)
        
        if callback:
            btn.clicked.connect(callback)
             
        return btn
