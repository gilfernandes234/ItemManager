# spell_maker.py

import xml.etree.ElementTree as ET
from xml.dom import minidom
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QSpinBox, QPushButton, QTextEdit, QWidget, QApplication,
    QGridLayout, QComboBox, QFileDialog, QCheckBox, QLineEdit,
    QMessageBox, QTabWidget, QTableWidget, QTableWidgetItem, QSplitter,
    QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
import os
import re

def prettify_xml(elem):

    rough_string = ET.tostring(elem, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="\t").split('\n', 1)[1]

class LuaSyntaxHighlighter(QSyntaxHighlighter):

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.highlighting_rules = []
        
        # Keywords Lua
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569cd6"))
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = [
            'local', 'function', 'end', 'if', 'then', 'else', 'elseif',
            'for', 'while', 'do', 'return', 'break', 'not', 'and', 'or', 'true', 'false'
        ]
        for word in keywords:
            self.highlighting_rules.append((re.compile(f"\\b{word}\\b"), keyword_format))
        
        # Funções Tibia
        tibia_format = QTextCharFormat()
        tibia_format.setForeground(QColor("#4ec9b0"))
        tibia_functions = [
            'Combat', 'Condition', 'Position', 'Creature', 'Player',
            'setCombatArea', 'setCombatParam', 'onCastSpell', 'doCombat',
            'createCombatArea', 'getPosition', 'sendMagicEffect', 'getHealth'
        ]
        for func in tibia_functions:
            self.highlighting_rules.append((re.compile(f"\\b{func}\\b"), tibia_format))
        
        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#ce9178"))
        self.highlighting_rules.append((re.compile(r"'[^']*'"), string_format))
        self.highlighting_rules.append((re.compile(r'"[^"]*"'), string_format))
        
        # Números
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#b5cea8"))
        self.highlighting_rules.append((re.compile(r'\b\d+\b'), number_format))
        
        # Comentários
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6a9955"))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((re.compile(r'--[^\n]*'), comment_format))
    
    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)

class SpellMakerWindow(QDialog):

    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.spells_data = []
        self.current_spell = None
        self.setWindowTitle("Spell Maker - Tibia Spell Editor")
        self.setModal(False)
        self.resize(1200, 700)
        self.setup_ui()
    
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        # Barra de ferramentas
        toolbar = QHBoxLayout()
        
        self.load_spells_btn = QPushButton("📂 Load spells.xml")
        self.load_spells_btn.clicked.connect(self.load_spells_xml)
        toolbar.addWidget(self.load_spells_btn)
        
        self.new_spell_btn = QPushButton("➕ New Spell")
        self.new_spell_btn.clicked.connect(self.create_new_spell)
        toolbar.addWidget(self.new_spell_btn)
        
        self.save_spell_btn = QPushButton("💾 Save Spell")
        self.save_spell_btn.clicked.connect(self.save_current_spell)
        self.save_spell_btn.setEnabled(False)
        toolbar.addWidget(self.save_spell_btn)
        
        self.save_all_btn = QPushButton("💾 Save All to XML")
        self.save_all_btn.clicked.connect(self.save_all_spells)
        self.save_all_btn.setEnabled(False)
        toolbar.addWidget(self.save_all_btn)
        
        self.delete_spell_btn = QPushButton("🗑️ Delete Spell")
        self.delete_spell_btn.clicked.connect(self.delete_spell)
        self.delete_spell_btn.setEnabled(False)
        toolbar.addWidget(self.delete_spell_btn)
        
        toolbar.addStretch()
        
        self.spell_count_label = QLabel("0 spells loaded")
        toolbar.addWidget(self.spell_count_label)
        
        main_layout.addLayout(toolbar)
        
        # Splitter principal
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # ======== PAINEL ESQUERDO: Lista de Spells ========
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # Filtros
        filter_group = QGroupBox("Filters")
        filter_layout = QGridLayout()
        
        # Busca por nome
        filter_layout.addWidget(QLabel("Search:"), 0, 0)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by name or words...")
        self.search_input.textChanged.connect(self.filter_spells)
        filter_layout.addWidget(self.search_input, 0, 1)
        
        # Filtro por grupo
        filter_layout.addWidget(QLabel("Group:"), 1, 0)
        self.group_filter = QComboBox()
        self.group_filter.addItems(["All", "attack", "healing", "support"])
        self.group_filter.currentTextChanged.connect(self.filter_spells)
        filter_layout.addWidget(self.group_filter, 1, 1)
        
        # Filtro por vocação
        filter_layout.addWidget(QLabel("Vocation:"), 2, 0)
        self.vocation_filter = QComboBox()
        self.vocation_filter.addItems([
            "All", "Sorcerer", "Druid", "Paladin", "Knight",
            "Master Sorcerer", "Elder Druid", "Royal Paladin", "Elite Knight"
        ])
        self.vocation_filter.currentTextChanged.connect(self.filter_spells)
        filter_layout.addWidget(self.vocation_filter, 2, 1)
        
        filter_group.setLayout(filter_layout)
        left_layout.addWidget(filter_group)
        
        # Lista de spells
        self.spell_list = QListWidget()
        self.spell_list.itemSelectionChanged.connect(self.on_spell_selected)
        left_layout.addWidget(self.spell_list)
        
        main_splitter.addWidget(left_panel)
        
        # ======== PAINEL DIREITO: Editor ========
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Abas do editor
        self.editor_tabs = QTabWidget()
        
        # === ABA 1: Informações da Spell ===
        info_tab = QWidget()
        info_layout = QVBoxLayout(info_tab)
        
        # Grupo: Basic Information
        basic_group = QGroupBox("Basic Information")
        basic_layout = QGridLayout()
        
        row = 0
        self.spell_fields = {}
        
        # Nome
        basic_layout.addWidget(QLabel("Name:"), row, 0)
        self.spell_fields['name'] = QLineEdit()
        basic_layout.addWidget(self.spell_fields['name'], row, 1)
        
        # Words
        basic_layout.addWidget(QLabel("Words:"), row, 2)
        self.spell_fields['words'] = QLineEdit()
        self.spell_fields['words'].setPlaceholderText("exori gran")
        basic_layout.addWidget(self.spell_fields['words'], row, 3)
        row += 1
        
        # Type
        basic_layout.addWidget(QLabel("Type:"), row, 0)
        self.spell_fields['type'] = QComboBox()
        self.spell_fields['type'].addItems(["instant", "rune", "conjure"])
        basic_layout.addWidget(self.spell_fields['type'], row, 1)
        
        # Group
        basic_layout.addWidget(QLabel("Group:"), row, 2)
        self.spell_fields['group'] = QComboBox()
        self.spell_fields['group'].addItems(["attack", "healing", "support", "special"])
        basic_layout.addWidget(self.spell_fields['group'], row, 3)
        row += 1
        
        # Spell ID
        basic_layout.addWidget(QLabel("Spell ID:"), row, 0)
        self.spell_fields['spellid'] = QSpinBox()
        self.spell_fields['spellid'].setRange(1, 9999)
        basic_layout.addWidget(self.spell_fields['spellid'], row, 1)
        
        # Script
        basic_layout.addWidget(QLabel("Script:"), row, 2)
        self.spell_fields['script'] = QLineEdit()
        self.spell_fields['script'].setPlaceholderText("attack/spell_name.lua")
        basic_layout.addWidget(self.spell_fields['script'], row, 3)
        
        basic_group.setLayout(basic_layout)
        info_layout.addWidget(basic_group)
        
        # Grupo: Requirements
        req_group = QGroupBox("Requirements")
        req_layout = QGridLayout()
        
        row = 0
        # Level
        req_layout.addWidget(QLabel("Level:"), row, 0)
        self.spell_fields['level'] = QSpinBox()
        self.spell_fields['level'].setRange(0, 9999)
        self.spell_fields['level'].setValue(1)
        req_layout.addWidget(self.spell_fields['level'], row, 1)
        
        # Mana
        req_layout.addWidget(QLabel("Mana:"), row, 2)
        self.spell_fields['mana'] = QSpinBox()
        self.spell_fields['mana'].setRange(0, 9999)
        self.spell_fields['mana'].setValue(50)
        req_layout.addWidget(self.spell_fields['mana'], row, 3)
        
        # Soul
        req_layout.addWidget(QLabel("Soul:"), row, 4)
        self.spell_fields['soul'] = QSpinBox()
        self.spell_fields['soul'].setRange(0, 100)
        req_layout.addWidget(self.spell_fields['soul'], row, 5)
        row += 1
        
        # Premium
        self.spell_fields['premium'] = QCheckBox("Premium Only")
        req_layout.addWidget(self.spell_fields['premium'], row, 0, 1, 2)
        
        # Need Learn
        self.spell_fields['needlearn'] = QCheckBox("Need Learn")
        req_layout.addWidget(self.spell_fields['needlearn'], row, 2, 1, 2)
        
        req_group.setLayout(req_layout)
        info_layout.addWidget(req_group)
        
        # Grupo: Combat Parameters
        combat_group = QGroupBox("Combat Parameters")
        combat_layout = QGridLayout()
        
        row = 0
        # Range
        combat_layout.addWidget(QLabel("Range:"), row, 0)
        self.spell_fields['range'] = QSpinBox()
        self.spell_fields['range'].setRange(0, 10)
        combat_layout.addWidget(self.spell_fields['range'], row, 1)
        
        # Cooldown
        combat_layout.addWidget(QLabel("Cooldown (ms):"), row, 2)
        self.spell_fields['cooldown'] = QSpinBox()
        self.spell_fields['cooldown'].setRange(0, 999999)
        self.spell_fields['cooldown'].setValue(2000)
        self.spell_fields['cooldown'].setSingleStep(1000)
        combat_layout.addWidget(self.spell_fields['cooldown'], row, 3)
        
        # Group Cooldown
        combat_layout.addWidget(QLabel("Group CD (ms):"), row, 4)
        self.spell_fields['groupcooldown'] = QSpinBox()
        self.spell_fields['groupcooldown'].setRange(0, 999999)
        self.spell_fields['groupcooldown'].setValue(2000)
        self.spell_fields['groupcooldown'].setSingleStep(1000)
        combat_layout.addWidget(self.spell_fields['groupcooldown'], row, 5)
        row += 1
        
        # Checkboxes de propriedades
        self.spell_fields['aggressive'] = QCheckBox("Aggressive")
        combat_layout.addWidget(self.spell_fields['aggressive'], row, 0, 1, 2)
        
        self.spell_fields['blockwalls'] = QCheckBox("Block Walls")
        combat_layout.addWidget(self.spell_fields['blockwalls'], row, 2, 1, 2)
        
        self.spell_fields['needtarget'] = QCheckBox("Need Target")
        combat_layout.addWidget(self.spell_fields['needtarget'], row, 4, 1, 2)
        row += 1
        
        self.spell_fields['selftarget'] = QCheckBox("Self Target")
        combat_layout.addWidget(self.spell_fields['selftarget'], row, 0, 1, 2)
        
        self.spell_fields['direction'] = QCheckBox("Direction")
        combat_layout.addWidget(self.spell_fields['direction'], row, 2, 1, 2)
        
        self.spell_fields['needweapon'] = QCheckBox("Need Weapon")
        combat_layout.addWidget(self.spell_fields['needweapon'], row, 4, 1, 2)
        
        combat_group.setLayout(combat_layout)
        info_layout.addWidget(combat_group)
        
        # Grupo: Vocations
        voc_group = QGroupBox("Vocations")
        voc_layout = QHBoxLayout()
        
        self.vocation_checks = {}
        vocations = [
            "Sorcerer", "Druid", "Paladin", "Knight",
            "Master Sorcerer", "Elder Druid", "Royal Paladin", "Elite Knight"
        ]
        
        voc_col_layout = QVBoxLayout()
        for i, voc in enumerate(vocations):
            checkbox = QCheckBox(voc)
            self.vocation_checks[voc] = checkbox
            voc_col_layout.addWidget(checkbox)
            if i == 3:
                voc_layout.addLayout(voc_col_layout)
                voc_col_layout = QVBoxLayout()
        
        voc_layout.addLayout(voc_col_layout)
        voc_layout.addStretch()
        voc_group.setLayout(voc_layout)
        info_layout.addWidget(voc_group)
        
        info_layout.addStretch()
        self.editor_tabs.addTab(info_tab, "📋 Spell Info")
        
        # === ABA 2: Script Lua ===
        script_tab = QWidget()
        script_layout = QVBoxLayout(script_tab)
        
        # Toolbar do script
        script_toolbar = QHBoxLayout()
        
        self.template_combo = QComboBox()
        self.template_combo.addItems([
            "Blank",
            "Attack Spell (Area)",
            "Attack Spell (Target)",
            "Healing Spell",
            "Support Spell (Buff)",
            "Wave Spell",
            "Beam Spell"
        ])
        self.template_combo.currentIndexChanged.connect(self.apply_spell_template)
        script_toolbar.addWidget(QLabel("Template:"))
        script_toolbar.addWidget(self.template_combo)
        script_toolbar.addStretch()
        
        self.load_script_btn = QPushButton("📂 Load Script")
        self.load_script_btn.clicked.connect(self.load_script_file)
        script_toolbar.addWidget(self.load_script_btn)
        
        script_layout.addLayout(script_toolbar)
        
        # Editor de script
        self.script_editor = QTextEdit()
        self.script_editor.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; "
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 10pt;"
        )
        self.script_highlighter = LuaSyntaxHighlighter(self.script_editor.document())
        script_layout.addWidget(self.script_editor)
        
        self.editor_tabs.addTab(script_tab, "📜 Lua Script")
        
        # === ABA 3: XML Preview ===
        xml_tab = QWidget()
        xml_layout = QVBoxLayout(xml_tab)
        
        xml_toolbar = QHBoxLayout()
        self.copy_xml_btn = QPushButton("📋 Copy XML")
        self.copy_xml_btn.clicked.connect(self.copy_xml)
        xml_toolbar.addWidget(self.copy_xml_btn)
        xml_toolbar.addStretch()
        xml_layout.addLayout(xml_toolbar)
        
        self.xml_preview = QTextEdit()
        self.xml_preview.setReadOnly(True)
        self.xml_preview.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; "
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 9pt;"
        )
        xml_layout.addWidget(self.xml_preview)
        
        self.editor_tabs.addTab(xml_tab, "📄 XML Preview")
        
        # Conecta mudanças para atualizar XML
# spell_maker.py - CORREÇÃO

# Substitua a seção de conexão de sinais (linhas 403-411) por:

        # Conecta mudanças para atualizar XML
        for field_name, widget in self.spell_fields.items():
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self.update_xml_preview)
            elif isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self.update_xml_preview)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self.update_xml_preview)  # ← CORREÇÃO
            elif isinstance(widget, QCheckBox):
                widget.stateChanged.connect(self.update_xml_preview)
        
        for checkbox in self.vocation_checks.values():
            checkbox.stateChanged.connect(self.update_xml_preview)

        
        right_layout.addWidget(self.editor_tabs)
        main_splitter.addWidget(right_panel)
        
        # Proporções do splitter
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)
        
        main_layout.addWidget(main_splitter)
    
    def load_spells_xml(self):

        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(current_dir)
        default_path = os.path.join(base_dir, 'assets', 'xml', 'spells', 'spells.xml')
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select spells.xml", default_path, "XML files (*.xml);;All files (*.*)"
        )
        
        if not filepath:
            return
        
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
            
            self.spells_data.clear()
            self.spell_list.clear()
            
            for spell_elem in root.findall('.//instant'):
                spell_data = self.parse_spell_element(spell_elem)
                self.spells_data.append(spell_data)
            
            for spell_elem in root.findall('.//rune'):
                spell_data = self.parse_spell_element(spell_elem, spell_type='rune')
                self.spells_data.append(spell_data)
            
            for spell_elem in root.findall('.//conjure'):
                spell_data = self.parse_spell_element(spell_elem, spell_type='conjure')
                self.spells_data.append(spell_data)
            
            self.populate_spell_list()
            self.spell_count_label.setText(f"{len(self.spells_data)} spells loaded")
            self.save_all_btn.setEnabled(True)
            
            QMessageBox.information(self, "Success", f"Loaded {len(self.spells_data)} spells from:\n{filepath}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load spells.xml:\n{e}")
    
    def parse_spell_element(self, elem, spell_type='instant'):

        spell_data = {
            'type': spell_type,
            'name': elem.get('name', ''),
            'words': elem.get('words', ''),
            'group': elem.get('group', 'attack'),
            'spellid': int(elem.get('spellid', 0)) if elem.get('spellid') else 0,
            'level': int(elem.get('level', 1)),
            'mana': int(elem.get('mana', 0)),
            'soul': int(elem.get('soul', 0)) if elem.get('soul') else 0,
            'premium': elem.get('premium', '0') == '1',
            'needlearn': elem.get('needlearn', '0') == '1',
            'range': int(elem.get('range', 0)) if elem.get('range') else 0,
            'cooldown': int(elem.get('cooldown', 2000)) if elem.get('cooldown') else 2000,
            'groupcooldown': int(elem.get('groupcooldown', 2000)) if elem.get('groupcooldown') else 2000,
            'aggressive': elem.get('aggressive', '0') == '1',
            'blockwalls': elem.get('blockwalls', '0') == '1',
            'needtarget': elem.get('needtarget', '0') == '1',
            'selftarget': elem.get('selftarget', '0') == '1',
            'direction': elem.get('direction', '0') == '1',
            'needweapon': elem.get('needweapon', '0') == '1',
            'script': elem.get('script', ''),
            'vocations': []
        }
        
        # Parse vocações
        for voc_elem in elem.findall('vocation'):
            voc_name = voc_elem.get('name', '')
            if voc_name:
                spell_data['vocations'].append(voc_name)
        
        return spell_data
    
    def populate_spell_list(self):

        self.spell_list.clear()
        for spell in self.spells_data:
            item_text = f"{spell['name']} ({spell['words']}) - Lvl {spell['level']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, spell)
            self.spell_list.addItem(item)
    
    def filter_spells(self):
 
        search_text = self.search_input.text().lower()
        group_filter = self.group_filter.currentText()
        voc_filter = self.vocation_filter.currentText()
        
        for i in range(self.spell_list.count()):
            item = self.spell_list.item(i)
            spell = item.data(Qt.ItemDataRole.UserRole)
            
            # Filtro de busca
            match_search = (search_text in spell['name'].lower() or 
                          search_text in spell['words'].lower())
            
            # Filtro de grupo
            match_group = (group_filter == "All" or spell['group'] == group_filter.lower())
            
            # Filtro de vocação
            match_voc = (voc_filter == "All" or voc_filter in spell['vocations'])
            
            item.setHidden(not (match_search and match_group and match_voc))
    
    def on_spell_selected(self):

        selected_items = self.spell_list.selectedItems()
        if not selected_items:
            return
        
        self.current_spell = selected_items[0].data(Qt.ItemDataRole.UserRole)
        self.load_spell_to_editor(self.current_spell)
        self.save_spell_btn.setEnabled(True)
        self.delete_spell_btn.setEnabled(True)
    
    def load_spell_to_editor(self, spell_data):
   
        # Campos básicos
        self.spell_fields['name'].setText(spell_data.get('name', ''))
        self.spell_fields['words'].setText(spell_data.get('words', ''))
        self.spell_fields['type'].setCurrentText(spell_data.get('type', 'instant'))
        self.spell_fields['group'].setCurrentText(spell_data.get('group', 'attack'))
        self.spell_fields['spellid'].setValue(spell_data.get('spellid', 0))
        self.spell_fields['script'].setText(spell_data.get('script', ''))
        
        # Requirements
        self.spell_fields['level'].setValue(spell_data.get('level', 1))
        self.spell_fields['mana'].setValue(spell_data.get('mana', 0))
        self.spell_fields['soul'].setValue(spell_data.get('soul', 0))
        self.spell_fields['premium'].setChecked(spell_data.get('premium', False))
        self.spell_fields['needlearn'].setChecked(spell_data.get('needlearn', False))
        
        # Combat
        self.spell_fields['range'].setValue(spell_data.get('range', 0))
        self.spell_fields['cooldown'].setValue(spell_data.get('cooldown', 2000))
        self.spell_fields['groupcooldown'].setValue(spell_data.get('groupcooldown', 2000))
        self.spell_fields['aggressive'].setChecked(spell_data.get('aggressive', False))
        self.spell_fields['blockwalls'].setChecked(spell_data.get('blockwalls', False))
        self.spell_fields['needtarget'].setChecked(spell_data.get('needtarget', False))
        self.spell_fields['selftarget'].setChecked(spell_data.get('selftarget', False))
        self.spell_fields['direction'].setChecked(spell_data.get('direction', False))
        self.spell_fields['needweapon'].setChecked(spell_data.get('needweapon', False))
        
        # Vocations
        for voc_name, checkbox in self.vocation_checks.items():
            checkbox.setChecked(voc_name in spell_data.get('vocations', []))
        
        # Carrega script
        self.load_spell_script(spell_data.get('script', ''))
        
        # Atualiza XML preview
        self.update_xml_preview()
    
    def load_spell_script(self, script_path):

        if not script_path:
            self.script_editor.clear()
            return
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(current_dir)
        full_path = os.path.join(base_dir, 'assets', 'xml', 'spells','scripts', script_path)
        
        if os.path.exists(full_path):
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    self.script_editor.setPlainText(f.read())
            except Exception as e:
                self.script_editor.setPlainText(f"-- Error loading script: {e}")
        else:
            self.script_editor.setPlainText(f"-- Script file not found: {full_path}")
    
    def create_new_spell(self):
  
        self.current_spell = {
            'type': 'instant',
            'name': 'New Spell',
            'words': 'exori new',
            'group': 'attack',
            'spellid': 0,
            'level': 1,
            'mana': 50,
            'soul': 0,
            'premium': False,
            'needlearn': False,
            'range': 3,
            'cooldown': 2000,
            'groupcooldown': 2000,
            'aggressive': True,
            'blockwalls': True,
            'needtarget': False,
            'selftarget': False,
            'direction': False,
            'needweapon': False,
            'script': 'attack/new_spell.lua',
            'vocations': []
        }
        
        self.load_spell_to_editor(self.current_spell)
        self.script_editor.clear()
        self.save_spell_btn.setEnabled(True)
    
    def save_current_spell(self):

        if not self.current_spell:
            return
        
        # Atualiza dados da spell com valores dos campos
        spell_data = {
            'type': self.spell_fields['type'].currentText(),
            'name': self.spell_fields['name'].text(),
            'words': self.spell_fields['words'].text(),
            'group': self.spell_fields['group'].currentText(),
            'spellid': self.spell_fields['spellid'].value(),
            'level': self.spell_fields['level'].value(),
            'mana': self.spell_fields['mana'].value(),
            'soul': self.spell_fields['soul'].value(),
            'premium': self.spell_fields['premium'].isChecked(),
            'needlearn': self.spell_fields['needlearn'].isChecked(),
            'range': self.spell_fields['range'].value(),
            'cooldown': self.spell_fields['cooldown'].value(),
            'groupcooldown': self.spell_fields['groupcooldown'].value(),
            'aggressive': self.spell_fields['aggressive'].isChecked(),
            'blockwalls': self.spell_fields['blockwalls'].isChecked(),
            'needtarget': self.spell_fields['needtarget'].isChecked(),
            'selftarget': self.spell_fields['selftarget'].isChecked(),
            'direction': self.spell_fields['direction'].isChecked(),
            'needweapon': self.spell_fields['needweapon'].isChecked(),
            'script': self.spell_fields['script'].text(),
            'vocations': [voc for voc, cb in self.vocation_checks.items() if cb.isChecked()]
        }
        
        # Salva script Lua
        script_path = spell_data['script']
        if script_path:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            base_dir = os.path.dirname(current_dir)
            full_script_path = os.path.join(base_dir, 'assets', 'xml', 'spells', script_path)
            
            # Cria diretórios se necessário
            os.makedirs(os.path.dirname(full_script_path), exist_ok=True)
            
            try:
                with open(full_script_path, 'w', encoding='utf-8') as f:
                    f.write(self.script_editor.toPlainText())
            except Exception as e:
                QMessageBox.warning(self, "Warning", f"Could not save script:\n{e}")
        
        # Atualiza ou adiciona na lista
        found = False
        for i, spell in enumerate(self.spells_data):
            if spell.get('name') == self.current_spell.get('name'):
                self.spells_data[i] = spell_data
                found = True
                break
        
        if not found:
            self.spells_data.append(spell_data)
        
        self.current_spell = spell_data
        self.populate_spell_list()
        self.spell_count_label.setText(f"{len(self.spells_data)} spells loaded")
        
        QMessageBox.information(self, "Success", f"Spell '{spell_data['name']}' saved successfully!")
    
    def delete_spell(self):
    
        if not self.current_spell:
            return
        
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete spell '{self.current_spell['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.spells_data = [s for s in self.spells_data if s.get('name') != self.current_spell.get('name')]
            self.populate_spell_list()
            self.spell_count_label.setText(f"{len(self.spells_data)} spells loaded")
            self.create_new_spell()
    
    def save_all_spells(self):

        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(current_dir)
        default_path = os.path.join(base_dir, 'assets', 'xml', 'spells', 'spells.xml')
        
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save spells.xml", default_path, "XML files (*.xml)"
        )
        
        if not filepath:
            return
        
        try:
            root = ET.Element('spells')
            
            # Agrupa por tipo
            for spell in self.spells_data:
                spell_elem = ET.SubElement(root, spell['type'])
                
                # Atributos obrigatórios
                spell_elem.set('name', spell['name'])
                if spell['words']:
                    spell_elem.set('words', spell['words'])
                
                # Atributos opcionais
                if spell.get('group'):
                    spell_elem.set('group', spell['group'])
                if spell.get('spellid'):
                    spell_elem.set('spellid', str(spell['spellid']))
                if spell.get('level'):
                    spell_elem.set('level', str(spell['level']))
                if spell.get('mana'):
                    spell_elem.set('mana', str(spell['mana']))
                if spell.get('soul'):
                    spell_elem.set('soul', str(spell['soul']))
                if spell.get('premium'):
                    spell_elem.set('premium', '1')
                if spell.get('needlearn'):
                    spell_elem.set('needlearn', '1')
                if spell.get('range'):
                    spell_elem.set('range', str(spell['range']))
                if spell.get('cooldown'):
                    spell_elem.set('cooldown', str(spell['cooldown']))
                if spell.get('groupcooldown'):
                    spell_elem.set('groupcooldown', str(spell['groupcooldown']))
                if spell.get('aggressive'):
                    spell_elem.set('aggressive', '1')
                if spell.get('blockwalls'):
                    spell_elem.set('blockwalls', '1')
                if spell.get('needtarget'):
                    spell_elem.set('needtarget', '1')
                if spell.get('selftarget'):
                    spell_elem.set('selftarget', '1')
                if spell.get('direction'):
                    spell_elem.set('direction', '1')
                if spell.get('needweapon'):
                    spell_elem.set('needweapon', '1')
                if spell.get('script'):
                    spell_elem.set('script', spell['script'])
                
                # Vocações
                for vocation in spell.get('vocations', []):
                    voc_elem = ET.SubElement(spell_elem, 'vocation')
                    voc_elem.set('name', vocation)
            
            # Salva com formatação
            xml_string = prettify_xml(root)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write(xml_string)
            
            QMessageBox.information(self, "Success", f"Saved {len(self.spells_data)} spells to:\n{filepath}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save spells.xml:\n{e}")
    
    def update_xml_preview(self):
     
        spell_elem = ET.Element('instant')
        
        # Atributos
        name = self.spell_fields['name'].text()
        if name:
            spell_elem.set('name', name)
        
        words = self.spell_fields['words'].text()
        if words:
            spell_elem.set('words', words)
        
        group = self.spell_fields['group'].currentText()
        if group:
            spell_elem.set('group', group)
        
        spellid = self.spell_fields['spellid'].value()
        if spellid:
            spell_elem.set('spellid', str(spellid))
        
        spell_elem.set('level', str(self.spell_fields['level'].value()))
        spell_elem.set('mana', str(self.spell_fields['mana'].value()))
        
        if self.spell_fields['soul'].value() > 0:
            spell_elem.set('soul', str(self.spell_fields['soul'].value()))
        
        if self.spell_fields['premium'].isChecked():
            spell_elem.set('premium', '1')
        
        if self.spell_fields['range'].value() > 0:
            spell_elem.set('range', str(self.spell_fields['range'].value()))
        
        spell_elem.set('cooldown', str(self.spell_fields['cooldown'].value()))
        spell_elem.set('groupcooldown', str(self.spell_fields['groupcooldown'].value()))
        
        if self.spell_fields['aggressive'].isChecked():
            spell_elem.set('aggressive', '1')
        if self.spell_fields['blockwalls'].isChecked():
            spell_elem.set('blockwalls', '1')
        if self.spell_fields['needtarget'].isChecked():
            spell_elem.set('needtarget', '1')
        if self.spell_fields['selftarget'].isChecked():
            spell_elem.set('selftarget', '1')
        if self.spell_fields['direction'].isChecked():
            spell_elem.set('direction', '1')
        if self.spell_fields['needweapon'].isChecked():
            spell_elem.set('needweapon', '1')
        if self.spell_fields['needlearn'].isChecked():
            spell_elem.set('needlearn', '1')
        
        script = self.spell_fields['script'].text()
        if script:
            spell_elem.set('script', script)
        
        # Vocações
        for voc_name, checkbox in self.vocation_checks.items():
            if checkbox.isChecked():
                voc_elem = ET.SubElement(spell_elem, 'vocation')
                voc_elem.set('name', voc_name)
        
        # Formata e exibe
        xml_string = prettify_xml(spell_elem)
        self.xml_preview.setPlainText(xml_string)
    
    def copy_xml(self):

        QApplication.clipboard().setText(self.xml_preview.toPlainText())
        QMessageBox.information(self, "Success", "XML copied to clipboard!")
    
    def load_script_file(self):

        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(current_dir)
        default_path = os.path.join(base_dir, 'assets', 'xml', 'spells')
        
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select Lua Script", default_path, "Lua files (*.lua);;All files (*.*)"
        )
        
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    self.script_editor.setPlainText(f.read())
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not load script:\n{e}")
    
    def apply_spell_template(self, index):

        templates = {
            0: "",
            1: self.get_area_attack_template(),
            2: self.get_target_attack_template(),
            3: self.get_healing_template(),
            4: self.get_buff_template(),
            5: self.get_wave_template(),
            6: self.get_beam_template()
        }
        
        template = templates.get(index, "")
        if template:
            self.script_editor.setPlainText(template)
    
    def get_area_attack_template(self):
        return """local combat = Combat()
combat:setParameter(COMBAT_PARAM_TYPE, COMBAT_PHYSICALDAMAGE)
combat:setParameter(COMBAT_PARAM_EFFECT, CONST_ME_HITAREA)
combat:setParameter(COMBAT_PARAM_DISTANCEEFFECT, CONST_ANI_WEAPONTYPE)

function onGetFormulaValues(player, level, magicLevel)
    local min = (level / 5) + (magicLevel * 1.5) + 10
    local max = (level / 5) + (magicLevel * 2.5) + 20
    return -min, -max
end

combat:setCallback(CALLBACK_PARAM_LEVELMAGICVALUE, "onGetFormulaValues")

local area = createCombatArea(AREA_CIRCLE3X3)
combat:setArea(area)

function onCastSpell(creature, variant)
    return combat:execute(creature, variant)
end"""
    
    def get_target_attack_template(self):
        return """local combat = Combat()
combat:setParameter(COMBAT_PARAM_TYPE, COMBAT_PHYSICALDAMAGE)
combat:setParameter(COMBAT_PARAM_EFFECT, CONST_ME_HITAREA)
combat:setParameter(COMBAT_PARAM_DISTANCEEFFECT, CONST_ANI_WEAPONTYPE)

function onGetFormulaValues(player, level, magicLevel)
    local min = (level / 5) + (magicLevel * 2) + 15
    local max = (level / 5) + (magicLevel * 3) + 25
    return -min, -max
end

combat:setCallback(CALLBACK_PARAM_LEVELMAGICVALUE, "onGetFormulaValues")

function onCastSpell(creature, variant)
    return combat:execute(creature, variant)
end"""
    
    def get_healing_template(self):
        return """local combat = Combat()
combat:setParameter(COMBAT_PARAM_TYPE, COMBAT_HEALING)
combat:setParameter(COMBAT_PARAM_EFFECT, CONST_ME_MAGIC_BLUE)
combat:setParameter(COMBAT_PARAM_AGGRESSIVE, false)

function onGetFormulaValues(player, level, magicLevel)
    local min = (level / 5) + (magicLevel * 3) + 20
    local max = (level / 5) + (magicLevel * 5) + 40
    return min, max
end

combat:setCallback(CALLBACK_PARAM_LEVELMAGICVALUE, "onGetFormulaValues")

function onCastSpell(creature, variant)
    return combat:execute(creature, variant)
end"""
    
    def get_buff_template(self):
        return """local combat = Combat()
combat:setParameter(COMBAT_PARAM_EFFECT, CONST_ME_MAGIC_GREEN)
combat:setParameter(COMBAT_PARAM_AGGRESSIVE, false)

local condition = Condition(CONDITION_HASTE)
condition:setParameter(CONDITION_PARAM_TICKS, 10000)
condition:setFormula(0.3, -24, 0.3, -24)
combat:addCondition(condition)

function onCastSpell(creature, variant)
    return combat:execute(creature, variant)
end"""
    
    def get_wave_template(self):
        return """local combat = Combat()
combat:setParameter(COMBAT_PARAM_TYPE, COMBAT_PHYSICALDAMAGE)
combat:setParameter(COMBAT_PARAM_EFFECT, CONST_ME_HITAREA)

function onGetFormulaValues(player, level, magicLevel)
    local min = (level / 5) + (magicLevel * 1.5) + 10
    local max = (level / 5) + (magicLevel * 2.5) + 20
    return -min, -max
end

combat:setCallback(CALLBACK_PARAM_LEVELMAGICVALUE, "onGetFormulaValues")

local area = createCombatArea(AREA_WAVE4)
combat:setArea(area)

function onCastSpell(creature, variant)
    return combat:execute(creature, variant)
end"""
    
    def get_beam_template(self):
        return """local combat = Combat()
combat:setParameter(COMBAT_PARAM_TYPE, COMBAT_PHYSICALDAMAGE)
combat:setParameter(COMBAT_PARAM_EFFECT, CONST_ME_ENERGYAREA)

function onGetFormulaValues(player, level, magicLevel)
    local min = (level / 5) + (magicLevel * 2) + 15
    local max = (level / 5) + (magicLevel * 3) + 25
    return -min, -max
end

combat:setCallback(CALLBACK_PARAM_LEVELMAGICVALUE, "onGetFormulaValues")

local area = createCombatArea(AREA_BEAM5)
combat:setArea(area)

function onCastSpell(creature, variant)
    return combat:execute(creature, variant)
end"""


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    window = SpellMakerWindow()
    window.show()
    sys.exit(app.exec())
