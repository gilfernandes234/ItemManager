# looktype_generator.py
import xml.etree.ElementTree as ET
from xml.dom import minidom
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QSpinBox, QPushButton, QTextEdit, QWidget, QApplication,
    QGridLayout, QFrame, QComboBox, QFileDialog, QCheckBox, QLineEdit,
    QMessageBox, QTabWidget, QTableWidget, QTableWidgetItem, QSplitter,
    QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QClipboard, QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PIL import Image
import os
import struct
import re



def prettify_xml(elem):
    """Formata o XML com indentação"""
    rough_string = ET.tostring(elem, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ").split('\n', 1)[1]


class OutfitMount:
    """Classe para armazenar dados de outfit ou mount"""
    def __init__(self, id, name, type_value, premium=False):
        self.id = id
        self.name = name
        self.type_value = type_value  # looktype para outfit, id para mount
        self.premium = premium


class XMLLoader:
    """Carrega e parseia arquivos XML de outfits e mounts"""
    
    @staticmethod
    def load_outfits(xml_path):
        outfits = []
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            for outfit in root.findall('outfit'):
                outfit_id = int(outfit.get('id', 0))
                name = outfit.get('name', f'Outfit {outfit_id}')
                looktype = int(outfit.get('looktype', 0))
                premium = outfit.get('premium', 'no').lower() == 'yes'
                
                outfits.append(OutfitMount(outfit_id, name, looktype, premium))
                
        except Exception as e:
            print(f"Erro ao carregar outfits.xml: {e}")
        
        return outfits
    
    @staticmethod
    def load_mounts(xml_path):

        mounts = []
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            for mount in root.findall('mount'):
                mount_id = int(mount.get('id', 0))
                name = mount.get('name', f'Mount {mount_id}')
                clientid = int(mount.get('clientid', 0))
                premium = mount.get('premium', 'no').lower() == 'yes'
                
                mounts.append(OutfitMount(mount_id, name, clientid, premium))
                
        except Exception as e:
            print(f"Erro ao carregar mounts.xml: {e}")
        
        return mounts
        
        


class LuaSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighting para scripts Lua"""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Regras de highlighting
        self.highlighting_rules = []
        
        # Keywords Lua
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#569cd6"))
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = [
            'local', 'function', 'end', 'if', 'then', 'else', 'elseif',
            'for', 'while', 'do', 'return', 'break', 'not', 'and', 'or'
        ]
        for word in keywords:
            pattern = f"\\b{word}\\b"
            self.highlighting_rules.append((re.compile(pattern), keyword_format))
        
        # Funções Tibia NPC
        tibia_format = QTextCharFormat()
        tibia_format.setForeground(QColor("#4ec9b0"))
        tibia_functions = [
            'KeywordHandler', 'NpcHandler', 'StdModule', 'FocusModule',
            'onCreatureAppear', 'onCreatureDisappear', 'onCreatureSay', 'onThink'
        ]
        for func in tibia_functions:
            pattern = f"\\b{func}\\b"
            self.highlighting_rules.append((re.compile(pattern), tibia_format))
        
        # Strings
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#ce9178"))
        self.highlighting_rules.append((re.compile(r"'[^']*'"), string_format))
        self.highlighting_rules.append((re.compile(r'"[^"]*"'), string_format))
        
        # Comentários
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6a9955"))
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((re.compile(r'--[^\n]*'), comment_format))
    
    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), format)

class NPCManager(QWidget):
    """Widget de gerenciamento de NPCs"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.npcs_data = []
        self.current_npc = None
        self.scripts_cache = {}
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Botões de ação
        action_layout = QHBoxLayout()
        self.load_npcs_btn = QPushButton("🔄 Load NPCs")
        self.load_npcs_btn.clicked.connect(self.load_all_npcs)
        
        self.new_npc_btn = QPushButton("➕ New NPC")
        self.new_npc_btn.clicked.connect(self.create_new_npc)
        
        self.save_npc_btn = QPushButton("💾 Save NPC")
        self.save_npc_btn.clicked.connect(self.save_current_npc)
        self.save_npc_btn.setEnabled(False)
        
        self.delete_npc_btn = QPushButton("🗑️ Delete NPC")
        self.delete_npc_btn.clicked.connect(self.delete_npc)
        self.delete_npc_btn.setEnabled(False)
        
        action_layout.addWidget(self.load_npcs_btn)
        action_layout.addWidget(self.new_npc_btn)
        action_layout.addWidget(self.save_npc_btn)
        action_layout.addWidget(self.delete_npc_btn)
        action_layout.addStretch()
        
        layout.addLayout(action_layout)
        
        # Splitter horizontal: Lista NPCs | Editor
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Lista de NPCs
        npc_list_widget = QWidget()
        npc_list_layout = QVBoxLayout(npc_list_widget)
        
        # Campo de busca
        search_layout = QHBoxLayout()
        search_label = QLabel("🔍 Search:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter NPCs...")
        self.search_input.textChanged.connect(self.filter_npcs)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        npc_list_layout.addLayout(search_layout)
        
        # Tabela de NPCs
        self.npc_table = QTableWidget()
        self.npc_table.setColumnCount(4)
        self.npc_table.setHorizontalHeaderLabels(["Name", "Script", "Looktype", "Location"])
        self.npc_table.horizontalHeader().setStretchLastSection(True)
        self.npc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.npc_table.itemSelectionChanged.connect(self.on_npc_selected)
        npc_list_layout.addWidget(self.npc_table)
        
        splitter.addWidget(npc_list_widget)
        
        # Editor de NPC
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        
        # Abas do editor
        self.editor_tabs = QTabWidget()
        
        # Aba 1: Informações básicas
        info_tab = QWidget()
        info_layout = QGridLayout(info_tab)
        
        row = 0
        self.npc_fields = {}
        
        fields_config = [
            ('name', 'Name:', QLineEdit, ''),
            ('script', 'Script File:', QLineEdit, '.lua'),
            ('walkinterval', 'Walk Interval:', QSpinBox, 2000),
            ('floorchange', 'Floor Change:', QSpinBox, 0),
            ('speechbubble', 'Speech Bubble:', QSpinBox, 3),
            ('health_now', 'Health Now:', QSpinBox, 100),
            ('health_max', 'Health Max:', QSpinBox, 100),
        ]
        
        for field_name, label_text, widget_class, default_val in fields_config:
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignmentFlag.AlignRight)
            
            if widget_class == QLineEdit:
                widget = QLineEdit()
                widget.setText(str(default_val))
            else:  # QSpinBox
                widget = QSpinBox()
                widget.setRange(0, 999999)
                widget.setValue(int(default_val))
            
            self.npc_fields[field_name] = widget
            info_layout.addWidget(label, row, 0)
            info_layout.addWidget(widget, row, 1)
            row += 1
        
        # Template de script
        template_layout = QHBoxLayout()
        template_label = QLabel("Script Template:")
        template_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.template_combo = QComboBox()
        self.template_combo.addItems([
            "Blank",
            "Bless Seller",
            "Shop (Buy/Sell)",
            "Quest Giver",
            "Teleporter",
            "Bank",
            "Custom Dialog"
        ])
        self.template_combo.currentIndexChanged.connect(self.apply_script_template)
        
        template_layout.addWidget(template_label)
        template_layout.addWidget(self.template_combo, 1)
        info_layout.addLayout(template_layout, row, 0, 1, 2)
        
        info_layout.setRowStretch(row + 1, 1)
        self.editor_tabs.addTab(info_tab, "📋 Info")
        
        # Aba 2: Script Lua
        script_tab = QWidget()
        script_layout = QVBoxLayout(script_tab)
        
        self.script_editor = QTextEdit()
        self.script_editor.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; "
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 10pt;"
        )
        self.highlighter = LuaSyntaxHighlighter(self.script_editor.document())
        
        script_layout.addWidget(self.script_editor)
        self.editor_tabs.addTab(script_tab, "📜 Script")
        
        editor_layout.addWidget(self.editor_tabs)
        splitter.addWidget(editor_widget)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        layout.addWidget(splitter)
    
    def load_all_npcs(self):
        """Carrega todos os NPCs da pasta assets/xml/npc/"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(current_dir)
        npc_dir = os.path.join(base_dir, 'assets', 'xml', 'npc')
        
        if not os.path.exists(npc_dir):
            QMessageBox.warning(self, "Warning", f"NPC directory not found:\n{npc_dir}")
            return
        
        self.npcs_data.clear()
        self.npc_table.setRowCount(0)
        
        # Escaneia todos os arquivos XML
        for filename in os.listdir(npc_dir):
            if filename.endswith('.xml'):
                xml_path = os.path.join(npc_dir, filename)
                try:
                    tree = ET.parse(xml_path)
                    root = tree.getroot()
                    
                    if root.tag == 'npc':
                        npc_data = {
                            'filename': filename,
                            'filepath': xml_path,
                            'name': root.get('name', ''),
                            'script': root.get('script', ''),
                            'walkinterval': int(root.get('walkinterval', 2000)),
                            'floorchange': int(root.get('floorchange', 0)),
                            'speechbubble': int(root.get('speechbubble', 3)),
                        }
                        
                        # Health
                        health = root.find('health')
                        if health is not None:
                            npc_data['health_now'] = int(health.get('now', 100))
                            npc_data['health_max'] = int(health.get('max', 100))
                        
                        # Look
                        look = root.find('look')
                        if look is not None:
                            npc_data['looktype'] = int(look.get('type', 0))
                            npc_data['head'] = int(look.get('head', 0))
                            npc_data['body'] = int(look.get('body', 0))
                            npc_data['legs'] = int(look.get('legs', 0))
                            npc_data['feet'] = int(look.get('feet', 0))
                            npc_data['addons'] = int(look.get('addons', 0))
                            npc_data['mount'] = int(look.get('mount', 0))
                        
                        self.npcs_data.append(npc_data)
                        
                        # Adiciona na tabela
                        row = self.npc_table.rowCount()
                        self.npc_table.insertRow(row)
                        self.npc_table.setItem(row, 0, QTableWidgetItem(npc_data['name']))
                        self.npc_table.setItem(row, 1, QTableWidgetItem(npc_data['script']))
                        self.npc_table.setItem(row, 2, QTableWidgetItem(str(npc_data.get('looktype', 'N/A'))))
                        self.npc_table.setItem(row, 3, QTableWidgetItem(filename))
                
                except Exception as e:
                    print(f"Error loading {filename}: {e}")
        
        QMessageBox.information(self, "Success", f"Loaded {len(self.npcs_data)} NPCs")
    
    def filter_npcs(self, text):
        """Filtra NPCs na tabela"""
        for row in range(self.npc_table.rowCount()):
            match = False
            for col in range(self.npc_table.columnCount()):
                item = self.npc_table.item(row, col)
                if item and text.lower() in item.text().lower():
                    match = True
                    break
            self.npc_table.setRowHidden(row, not match)
    
    def on_npc_selected(self):
        """Quando um NPC é selecionado na tabela"""
        selected = self.npc_table.selectedItems()
        if not selected:
            return
        
        row = selected[0].row()
        if row >= len(self.npcs_data):
            return
        
        self.current_npc = self.npcs_data[row]
        self.load_npc_to_editor(self.current_npc)
        self.save_npc_btn.setEnabled(True)
        self.delete_npc_btn.setEnabled(True)
    
    def load_npc_to_editor(self, npc_data):
        """Carrega dados do NPC no editor"""
        # Preenche campos
        self.npc_fields['name'].setText(npc_data.get('name', ''))
        self.npc_fields['script'].setText(npc_data.get('script', ''))
        self.npc_fields['walkinterval'].setValue(npc_data.get('walkinterval', 2000))
        self.npc_fields['floorchange'].setValue(npc_data.get('floorchange', 0))
        self.npc_fields['speechbubble'].setValue(npc_data.get('speechbubble', 3))
        self.npc_fields['health_now'].setValue(npc_data.get('health_now', 100))
        self.npc_fields['health_max'].setValue(npc_data.get('health_max', 100))
        
        # Carrega script Lua
        script_name = npc_data.get('script', '')
        if script_name:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            base_dir = os.path.dirname(current_dir)
            script_path = os.path.join(base_dir, 'assets', 'xml', 'npc', 'scripts', script_name)
            
            if os.path.exists(script_path):
                try:
                    with open(script_path, 'r', encoding='utf-8') as f:
                        script_content = f.read()
                        self.script_editor.setPlainText(script_content)
                        self.scripts_cache[script_name] = script_content
                except Exception as e:
                    self.script_editor.setPlainText(f"-- Error loading script: {e}")
            else:
                self.script_editor.setPlainText("-- Script file not found")
    
    def create_new_npc(self):
        """Cria um novo NPC"""
        self.current_npc = None
        
        # Limpa campos
        self.npc_fields['name'].setText("New NPC")
        self.npc_fields['script'].setText("new_npc.lua")
        self.npc_fields['walkinterval'].setValue(2000)
        self.npc_fields['floorchange'].setValue(0)
        self.npc_fields['speechbubble'].setValue(3)
        self.npc_fields['health_now'].setValue(100)
        self.npc_fields['health_max'].setValue(100)
        
        self.script_editor.clear()
        self.save_npc_btn.setEnabled(True)
    
    def apply_script_template(self, index):
        """Aplica template de script"""
        templates = {
            0: "",  # Blank
            1: self.get_bless_template(),
            2: self.get_shop_template(),
            3: self.get_quest_template(),
            4: self.get_teleport_template(),
            5: self.get_bank_template(),
            6: self.get_dialog_template(),
        }
        
        template = templates.get(index, "")
        if template:
            self.script_editor.setPlainText(template)
    
    def get_bless_template(self):
        """Template de vendedor de bênçãos"""
        return """local keywordHandler = KeywordHandler:new()
local npcHandler = NpcHandler:new(keywordHandler)
NpcSystem.parseParameters(npcHandler)

function onCreatureAppear(cid) npcHandler:onCreatureAppear(cid) end
function onCreatureDisappear(cid) npcHandler:onCreatureDisappear(cid) end
function onCreatureSay(cid, type, msg) npcHandler:onCreatureSay(cid, type, msg) end
function onThink() npcHandler:onThink() end

local blessCost = 10000

for i = 1, 5 do
    local node = keywordHandler:addKeyword({'bless ' .. i}, StdModule.say, {
        npcHandler = npcHandler,
        onlyFocus = true,
        text = 'Do you want to buy blessing ' .. i .. ' for ' .. blessCost .. ' gold?'
    })
    
    node:addChildKeyword({'yes'}, StdModule.bless, {
        npcHandler = npcHandler,
        bless = i,
        premium = true,
        cost = blessCost
    })
    
    node:addChildKeyword({'no'}, StdModule.say, {
        npcHandler = npcHandler,
        onlyFocus = true,
        reset = true,
        text = 'Too expensive, eh?'
    })
end

npcHandler:addModule(FocusModule:new())"""
    
    def get_shop_template(self):
        return """local keywordHandler = KeywordHandler:new()
local npcHandler = NpcHandler:new(keywordHandler)
NpcSystem.parseParameters(npcHandler)

function onCreatureAppear(cid) npcHandler:onCreatureAppear(cid) end
function onCreatureDisappear(cid) npcHandler:onCreatureDisappear(cid) end
function onCreatureSay(cid, type, msg) npcHandler:onCreatureSay(cid, type, msg) end
function onThink() npcHandler:onThink() end

-- Shop items
local shopModule = ShopModule:new()
npcHandler:addModule(shopModule)

shopModule:addBuyableItem({'health potion'}, 7618, 50, 'health potion')
shopModule:addBuyableItem({'mana potion'}, 7620, 50, 'mana potion')

shopModule:addSellableItem({'sword'}, 2376, 35, 'sword')

npcHandler:addModule(FocusModule:new())"""
    
    def get_quest_template(self):
        return """local keywordHandler = KeywordHandler:new()
local npcHandler = NpcHandler:new(keywordHandler)
NpcSystem.parseParameters(npcHandler)

function onCreatureAppear(cid) npcHandler:onCreatureAppear(cid) end
function onCreatureDisappear(cid) npcHandler:onCreatureDisappear(cid) end
function onCreatureSay(cid, type, msg) npcHandler:onCreatureSay(cid, type, msg) end
function onThink() npcHandler:onThink() end

function greetCallback(cid)
    return true
end

-- Quest keywords
keywordHandler:addKeyword({'quest'}, StdModule.say, {
    npcHandler = npcHandler,
    onlyFocus = true,
    text = 'I have a quest for you!'
})

npcHandler:setCallback(CALLBACK_GREET, greetCallback)
npcHandler:addModule(FocusModule:new())"""
    
    def get_teleport_template(self):
        return """local keywordHandler = KeywordHandler:new()
local npcHandler = NpcHandler:new(keywordHandler)
NpcSystem.parseParameters(npcHandler)

function onCreatureAppear(cid) npcHandler:onCreatureAppear(cid) end
function onCreatureDisappear(cid) npcHandler:onCreatureDisappear(cid) end
function onCreatureSay(cid, type, msg) npcHandler:onCreatureSay(cid, type, msg) end
function onThink() npcHandler:onThink() end

local travelNode = keywordHandler:addKeyword({'travel'}, StdModule.say, {
    npcHandler = npcHandler,
    onlyFocus = true,
    text = 'Where do you want to go? {Thais} or {Carlin}?'
})

travelNode:addChildKeyword({'thais'}, StdModule.travel, {
    npcHandler = npcHandler,
    premium = false,
    cost = 100,
    destination = {x=1000, y=1000, z=7}
})

npcHandler:addModule(FocusModule:new())"""
    
    def get_bank_template(self):
        return """local keywordHandler = KeywordHandler:new()
local npcHandler = NpcHandler:new(keywordHandler)
NpcSystem.parseParameters(npcHandler)

function onCreatureAppear(cid) npcHandler:onCreatureAppear(cid) end
function onCreatureDisappear(cid) npcHandler:onCreatureDisappear(cid) end
function onCreatureSay(cid, type, msg) npcHandler:onCreatureSay(cid, type, msg) end
function onThink() npcHandler:onThink() end

keywordHandler:addKeyword({'balance'}, StdModule.balance)
keywordHandler:addKeyword({'deposit'}, StdModule.deposit)
keywordHandler:addKeyword({'withdraw'}, StdModule.withdraw)

npcHandler:addModule(FocusModule:new())"""
    
    def get_dialog_template(self):
        return """local keywordHandler = KeywordHandler:new()
local npcHandler = NpcHandler:new(keywordHandler)
NpcSystem.parseParameters(npcHandler)

function onCreatureAppear(cid) npcHandler:onCreatureAppear(cid) end
function onCreatureDisappear(cid) npcHandler:onCreatureDisappear(cid) end
function onCreatureSay(cid, type, msg) npcHandler:onCreatureSay(cid, type, msg) end
function onThink() npcHandler:onThink() end

-- Custom dialog
keywordHandler:addKeyword({'hello'}, StdModule.say, {
    npcHandler = npcHandler,
    onlyFocus = true,
    text = 'Welcome, traveler!'
})

npcHandler:addModule(FocusModule:new())"""
    
    def save_current_npc(self):
        """Salva o NPC atual"""
        name = self.npc_fields['name'].text()
        script = self.npc_fields['script'].text()
        
        if not name or not script:
            QMessageBox.warning(self, "Warning", "Name and script filename are required!")
            return
        
        # Diretórios
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(current_dir)
        npc_dir = os.path.join(base_dir, 'assets', 'xml', 'npc')
        scripts_dir = os.path.join(npc_dir, 'scripts')
        
        # Cria diretórios se não existirem
        os.makedirs(npc_dir, exist_ok=True)
        os.makedirs(scripts_dir, exist_ok=True)
        
        # Salva XML
        xml_filename = f"{name.lower().replace(' ', '_')}.xml"
        xml_path = os.path.join(npc_dir, xml_filename)
        
        npc_elem = ET.Element('npc')
        npc_elem.set('name', name)
        npc_elem.set('script', script)
        npc_elem.set('walkinterval', str(self.npc_fields['walkinterval'].value()))
        npc_elem.set('floorchange', str(self.npc_fields['floorchange'].value()))
        npc_elem.set('speechbubble', str(self.npc_fields['speechbubble'].value()))
        
        health = ET.SubElement(npc_elem, 'health')
        health.set('now', str(self.npc_fields['health_now'].value()))
        health.set('max', str(self.npc_fields['health_max'].value()))
        
        # Salva XML formatado
        from xml.dom import minidom
        rough_string = ET.tostring(npc_elem, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ").split('\n', 1)[1]
        
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
        
        # Salva script Lua
        script_path = os.path.join(scripts_dir, script)
        script_content = self.script_editor.toPlainText()
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        QMessageBox.information(self, "Success", f"NPC saved:\n{xml_path}\n{script_path}")
        self.load_all_npcs()
    
    def delete_npc(self):
        """Deleta o NPC selecionado"""
        if not self.current_npc:
            return
        
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete NPC '{self.current_npc['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Remove XML
                if os.path.exists(self.current_npc['filepath']):
                    os.remove(self.current_npc['filepath'])
                
                # Remove script (opcional)
                script_path = self.current_npc['filepath'].replace('.xml', '').replace('npc', 'npc/scripts') + f"/{self.current_npc['script']}"
                if os.path.exists(script_path):
                    os.remove(script_path)
                
                QMessageBox.information(self, "Success", "NPC deleted")
                self.load_all_npcs()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete NPC:\n{e}")
        


class ColorPicker(QWidget):
    """Widget para selecionar cores do Tibia (0-132)"""
    colorChanged = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_color = 0
        self.tibia_colors = self._generate_tibia_palette()
        self.setup_ui()
    
    def _generate_tibia_palette(self):
        """Gera a paleta de cores do Tibia (HSI)"""
        colors = []
        # Paleta simplificada - você pode refinar isso depois
        for i in range(133):
            # Aproximação da paleta HSI do Tibia
            if i == 0:
                colors.append((0, 0, 0))  # Preto
            else:
                hue = (i % 7) * 36
                sat = min(255, (i // 7) * 20)
                val = min(255, 50 + (i % 19) * 10)
                colors.append(self._hsv_to_rgb(hue, sat, val))
        return colors
    
    def _hsv_to_rgb(self, h, s, v):
        """Converte HSV para RGB"""
        s = s / 255.0
        v = v / 255.0
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c
        
        if h < 60:
            r, g, b = c, x, 0
        elif h < 120:
            r, g, b = x, c, 0
        elif h < 180:
            r, g, b = 0, c, x
        elif h < 240:
            r, g, b = 0, x, c
        elif h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
        
        return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.spin = QSpinBox()
        self.spin.setRange(0, 132)
        self.spin.setValue(0)
        self.spin.setFixedWidth(60)
        self.spin.valueChanged.connect(self.on_value_changed)
        
        self.preview = QLabel()
        self.preview.setFixedSize(30, 30)
        self.preview.setStyleSheet("background-color: #000000; border: 1px solid gray;")
        
        layout.addWidget(self.spin)
        layout.addWidget(self.preview)
    
    def on_value_changed(self, value):
        self.current_color = value
        r, g, b = self.tibia_colors[value]
        self.preview.setStyleSheet(
            f"background-color: rgb({r}, {g}, {b}); border: 1px solid gray;"
        )
        self.colorChanged.emit(value)
    
    def value(self):
        return self.spin.value()
    
    def setValue(self, value):
        self.spin.setValue(value)


class LookTypeGeneratorWindow(QDialog):
    """Janela do gerador de LookType para NPCs com suporte a XML"""
    
    def __init__(self, spr_editor=None, dat_editor=None, parent=None):
        super().__init__(parent)
        self.spr_editor = spr_editor
        self.dat_editor = dat_editor
        self.current_direction = 2
        self.setWindowTitle("LookType Generator")
        self.setModal(False)
        self.resize(900, 700)

        # Listas de outfits e mounts
        self.outfits_list = []
        self.mounts_list = []
        
        self.looktype_data = {
            'type': 0,
            'head': 0,
            'body': 0,
            'legs': 0,
            'feet': 0,
            'addons': 0,
            'mount': 0,
        }
        
        self.npc_data = {
            'name': 'Alice',
            'script': 'bless.lua',
            'walkinterval': 6000,
            'floorchange': 0,
            'speechbubble': 3,
            'health_now': 100,
            'health_max': 100
        }
        
        self.setup_ui()
        self.auto_load_xml_files()  
        self.update_xml()

    
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        
        # Cria o QTabWidget principal
        self.main_tabs = QTabWidget()

        # ============================================
        # Aba 1: Editor de LookType
        # ============================================
        looktype_tab = QWidget()
        
        # Scroll Setup
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        scroll_content = QWidget()
        looktype_layout = QVBoxLayout(scroll_content)
        
        scroll_area.setWidget(scroll_content)
        
        tab_layout = QVBoxLayout(looktype_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll_area)

        # Grupo de carregamento de XMLs
        xml_load_group = QGroupBox("Load XML Files")
        xml_load_layout = QHBoxLayout()
        
        self.outfit_xml_btn = QPushButton("Load outfits.xml")
        self.outfit_xml_btn.clicked.connect(self.load_outfits_xml)
        xml_load_layout.addWidget(self.outfit_xml_btn)
        
        self.outfit_xml_label = QLabel("No file loaded")
        self.outfit_xml_label.setStyleSheet("color: gray;")
        xml_load_layout.addWidget(self.outfit_xml_label, 1)
        
        self.mount_xml_btn = QPushButton("Load mounts.xml")
        self.mount_xml_btn.clicked.connect(self.load_mounts_xml)
        xml_load_layout.addWidget(self.mount_xml_btn)
        
        self.mount_xml_label = QLabel("No file loaded")
        self.mount_xml_label.setStyleSheet("color: gray;")
        xml_load_layout.addWidget(self.mount_xml_label, 1)
        
        xml_load_group.setLayout(xml_load_layout)
        looktype_layout.addWidget(xml_load_group)  # ← Mudou de main_layout para looktype_layout
        
        # Grupo NPC Info
        npc_group = QGroupBox("NPC Information")
        npc_layout = QGridLayout()
        
        row = 0
        self.npc_widgets = {}
        
        for field, default_val in [
            ('name', 'Alice'),
            ('script', 'bless.lua'),
            ('walkinterval', 6000),
            ('floorchange', 0),
            ('speechbubble', 3)
        ]:
            label = QLabel(f"{field.capitalize()}:")
            label.setMinimumWidth(100)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
            if isinstance(default_val, int):
                widget = QSpinBox()
                widget.setRange(0, 999999)
                widget.setValue(default_val)
                widget.valueChanged.connect(self.on_npc_data_changed)
            else:
                widget = QLineEdit(default_val)
                widget.textChanged.connect(self.on_npc_data_changed)
            
            self.npc_widgets[field] = widget
            npc_layout.addWidget(label, row, 0)
            npc_layout.addWidget(widget, row, 1)
            row += 1
        
        npc_group.setLayout(npc_layout)
        looktype_layout.addWidget(npc_group)  # ← Mudou de main_layout para looktype_layout
        
        # Grupo LookType
        looktype_group = QGroupBox("LookType Configuration")
        looktype_main = QHBoxLayout()
        
        # Coluna esquerda - Outfit e cores
        left_col = QVBoxLayout()
        
        # Outfit Selector (ComboBox)
        outfit_layout = QHBoxLayout()
        outfit_label = QLabel("Outfit:")
        outfit_label.setMinimumWidth(70)
        outfit_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.outfit_combo = QComboBox()
        self.outfit_combo.setMinimumWidth(200)
        self.outfit_combo.currentIndexChanged.connect(self.on_outfit_selected)
        outfit_layout.addWidget(outfit_label)
        outfit_layout.addWidget(self.outfit_combo)
        outfit_layout.addStretch()
        left_col.addLayout(outfit_layout)
        
        # Type manual (para casos sem XML)
        type_layout = QHBoxLayout()
        type_label = QLabel("Type ID:")
        type_label.setMinimumWidth(70)
        type_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.type_spin = QSpinBox()
        self.type_spin.setRange(0, 0xFFFFFF)
        self.type_spin.setValue(0)
        self.type_spin.setFixedWidth(100)
        self.type_spin.valueChanged.connect(self.on_type_manual_changed)
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_spin)
        
        self.random_colors_btn = QPushButton("🎲 Random Colors")
        self.random_colors_btn.clicked.connect(self.randomize_colors)
        type_layout.addWidget(self.random_colors_btn)
        type_layout.addStretch()
        left_col.addLayout(type_layout)
        
        # Head
        head_layout = QHBoxLayout()
        head_label = QLabel("Head:")
        head_label.setMinimumWidth(70)
        head_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.head_picker = ColorPicker()
        self.head_picker.colorChanged.connect(self.on_looktype_changed)
        head_layout.addWidget(head_label)
        head_layout.addWidget(self.head_picker)
        head_layout.addStretch()
        left_col.addLayout(head_layout)
        
        # Body
        body_layout = QHBoxLayout()
        body_label = QLabel("Body:")
        body_label.setMinimumWidth(70)
        body_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.body_picker = ColorPicker()
        self.body_picker.colorChanged.connect(self.on_looktype_changed)
        body_layout.addWidget(body_label)
        body_layout.addWidget(self.body_picker)
        body_layout.addStretch()
        left_col.addLayout(body_layout)
        
        # Legs
        legs_layout = QHBoxLayout()
        legs_label = QLabel("Legs:")
        legs_label.setMinimumWidth(70)
        legs_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.legs_picker = ColorPicker()
        self.legs_picker.colorChanged.connect(self.on_looktype_changed)
        legs_layout.addWidget(legs_label)
        legs_layout.addWidget(self.legs_picker)
        legs_layout.addStretch()
        left_col.addLayout(legs_layout)
        
        # Feet
        feet_layout = QHBoxLayout()
        feet_label = QLabel("Feet:")
        feet_label.setMinimumWidth(70)
        feet_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.feet_picker = ColorPicker()
        self.feet_picker.colorChanged.connect(self.on_looktype_changed)
        feet_layout.addWidget(feet_label)
        feet_layout.addWidget(self.feet_picker)
        feet_layout.addStretch()
        left_col.addLayout(feet_layout)
        
        looktype_main.addLayout(left_col)
        
        # Coluna direita - Mount, addons e preview
        right_col = QVBoxLayout()
        
        # Addons
        addons_layout = QHBoxLayout()
        addons_label = QLabel("Addons:")
        addons_label.setMinimumWidth(70)
        addons_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.addons_spin = QSpinBox()
        self.addons_spin.setRange(0, 3)
        self.addons_spin.setValue(0)
        self.addons_spin.setFixedWidth(100)
        self.addons_spin.valueChanged.connect(self.on_looktype_changed)
        addons_layout.addWidget(addons_label)
        addons_layout.addWidget(self.addons_spin)
        addons_layout.addStretch()
        right_col.addLayout(addons_layout)
        
        # Mount Selector
        mount_layout = QHBoxLayout()
        mount_label = QLabel("Mount:")
        mount_label.setMinimumWidth(70)
        mount_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.mount_combo = QComboBox()
        self.mount_combo.setMinimumWidth(150)
        self.mount_combo.currentIndexChanged.connect(self.on_mount_selected)
        mount_layout.addWidget(mount_label)
        mount_layout.addWidget(self.mount_combo)
        mount_layout.addStretch()
        right_col.addLayout(mount_layout)
        
        # Mount ID manual
        mount_id_layout = QHBoxLayout()
        mount_id_label = QLabel("Mount ID:")
        mount_id_label.setMinimumWidth(70)
        mount_id_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.mount_spin = QSpinBox()
        self.mount_spin.setRange(0, 0xFFFFFF)
        self.mount_spin.setValue(0)
        self.mount_spin.setFixedWidth(100)
        self.mount_spin.valueChanged.connect(self.on_mount_manual_changed)
        mount_id_layout.addWidget(mount_id_label)
        mount_id_layout.addWidget(self.mount_spin)
        mount_id_layout.addStretch()
        right_col.addLayout(mount_id_layout)
        
        # Preview container
        preview_container = QVBoxLayout()

        # Título
        preview_title = QLabel("Preview")
        preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_title.setStyleSheet("font-weight: bold; font-size: 10pt;")
        preview_container.addWidget(preview_title)

        # Grid para botões direcionais + preview
        direction_grid = QGridLayout()
        direction_grid.setSpacing(5)
        direction_grid.setContentsMargins(0, 0, 0, 0)

        # Botão UP (South - costas)
        self.btn_north = QPushButton("South")
        self.btn_north.setFixedSize(32, 32)
        self.btn_north.clicked.connect(lambda: self.change_direction(0))
        direction_grid.addWidget(self.btn_north, 0, 1, Qt.AlignmentFlag.AlignCenter)

        # Botão LEFT (West - esquerda)
        self.btn_west = QPushButton("Left")
        self.btn_west.setFixedSize(32, 32)
        self.btn_west.clicked.connect(lambda: self.change_direction(3))
        direction_grid.addWidget(self.btn_west, 1, 0, Qt.AlignmentFlag.AlignCenter)

        # Preview no centro (com frame)
        preview_frame = QFrame()
        preview_frame.setFrameShape(QFrame.Shape.Box)
        preview_frame.setStyleSheet("background-color: #222121; border: 2px solid #555555;")
        preview_layout = QVBoxLayout(preview_frame)
        preview_layout.setContentsMargins(5, 5, 5, 5)

        self.outfit_preview = QLabel()
        self.outfit_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.outfit_preview.setFixedSize(96, 96)
        self.outfit_preview.setText("Preview")
        preview_layout.addWidget(self.outfit_preview)

        direction_grid.addWidget(preview_frame, 1, 1)

        # Botão RIGHT (East - direita)
        self.btn_east = QPushButton("Right")
        self.btn_east.setFixedSize(32, 32)
        self.btn_east.clicked.connect(lambda: self.change_direction(1))
        direction_grid.addWidget(self.btn_east, 1, 2, Qt.AlignmentFlag.AlignCenter)

        # Botão DOWN (North)
        self.btn_south = QPushButton("North")
        self.btn_south.setFixedSize(32, 32)
        self.btn_south.setStyleSheet("background-color: #007acc; color: white;")
        self.btn_south.clicked.connect(lambda: self.change_direction(2))
        direction_grid.addWidget(self.btn_south, 2, 1, Qt.AlignmentFlag.AlignCenter)

        preview_container.addLayout(direction_grid)

        # Info label
        self.preview_info_label = QLabel("Load SPR/DAT for preview")
        self.preview_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_info_label.setStyleSheet("color: gray; font-size: 9pt;")
        preview_container.addWidget(self.preview_info_label)

        right_col.addLayout(preview_container)
        right_col.addStretch()
        
        looktype_main.addLayout(right_col)
        looktype_group.setLayout(looktype_main)
        looktype_layout.addWidget(looktype_group)  # ← Mudou de main_layout para looktype_layout
        
        # Grupo XML Output
        xml_group = QGroupBox("XML Output")
        xml_layout = QVBoxLayout()
        
        self.xml_display = QTextEdit()
        self.xml_display.setReadOnly(True)
        self.xml_display.setMaximumHeight(120)
        self.xml_display.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas, monospace;"
        )
        xml_layout.addWidget(self.xml_display)
        
        xml_group.setLayout(xml_layout)
        looktype_layout.addWidget(xml_group)  # ← Mudou de main_layout para looktype_layout
        
        # Botões
        button_layout = QHBoxLayout()
        
        self.copy_btn = QPushButton("Copy XML")
        self.copy_btn.setMinimumWidth(70)
        self.copy_btn.clicked.connect(self.copy_xml)
        button_layout.addWidget(self.copy_btn)
        
        self.paste_btn = QPushButton("Paste XML")
        self.paste_btn.setMinimumWidth(70)
        self.paste_btn.clicked.connect(self.paste_xml)
        button_layout.addWidget(self.paste_btn)
        
        button_layout.addStretch()
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)
        
        looktype_layout.addLayout(button_layout)  # ← Mudou de main_layout para looktype_layout
        
        # ============================================
        # Adiciona as abas ao TabWidget
        # ============================================
        self.main_tabs.addTab(looktype_tab, "👤 LookType Editor")
        
        # Aba 2: NPC Manager
        self.npc_manager = NPCManager()
        self.main_tabs.addTab(self.npc_manager, "📂 NPC Manager")

        # Adiciona o TabWidget ao layout principal da janela
        main_layout.addWidget(self.main_tabs)
        
        # Inicializa combos vazios
        self.outfit_combo.addItem("(No outfit selected)", 0)
        self.mount_combo.addItem("(No mount)", 0)

        
    def auto_load_xml_files(self):
        """Busca e carrega automaticamente os arquivos XML da pasta assets"""
        # Determina o caminho base (sobe da pasta data/ para Itemmanager/)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_dir = os.path.dirname(current_dir)  # Sobe um nível
        assets_dir = os.path.join(base_dir, 'assets')
        
        # Tenta carregar outfits.xml
        outfit_path = os.path.join(assets_dir, 'xml', 'outfits.xml')
        if os.path.exists(outfit_path):
            try:
                self.outfits_list = XMLLoader.load_outfits(outfit_path)
                self.outfit_combo.clear()
                self.outfit_combo.addItem("(Select an outfit)", 0)
                for outfit in self.outfits_list:
                    premium_marker = " [Premium]" if outfit.premium else ""
                    self.outfit_combo.addItem(
                        f"{outfit.name} ({outfit.id}){premium_marker}",
                        outfit.type_value
                    )
                filename = os.path.basename(outfit_path)
                self.outfit_xml_label.setText(f"✓ {filename} ({len(self.outfits_list)} outfits)")
                self.outfit_xml_label.setStyleSheet("color: green;")
                print(f"✓ Loaded: {outfit_path}")
            except Exception as e:
                print(f"⚠ Error loading {outfit_path}: {e}")
        else:
            print(f"⚠ Not found: {outfit_path}")
        
        # Tenta carregar mount.xml
        mount_path = os.path.join(assets_dir, 'xml', 'mounts.xml')
        if os.path.exists(mount_path):
            try:
                self.mounts_list = XMLLoader.load_mounts(mount_path)
                self.mount_combo.clear()
                self.mount_combo.addItem("(No mount)", 0)
                for mount in self.mounts_list:
                    premium_marker = " [Premium]" if mount.premium else ""
                    self.mount_combo.addItem(
                        f"{mount.name} ({mount.id}){premium_marker}",
                        mount.type_value
                    )
                filename = os.path.basename(mount_path)
                self.mount_xml_label.setText(f"✓ {filename} ({len(self.mounts_list)} mounts)")
                self.mount_xml_label.setStyleSheet("color: green;")
                print(f"✓ Loaded: {mount_path}")
            except Exception as e:
                print(f"⚠ Error loading {mount_path}: {e}")
        else:
            print(f"⚠ Not found: {mount_path}")
            
    
    def load_outfits_xml(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select outfits.xml", "", "XML files (*.xml);;All files (*.*)"
        )
        
        if not filepath:
            return
        
        try:
            self.outfits_list = XMLLoader.load_outfits(filepath)
            
            # Limpa e preenche o combo
            self.outfit_combo.clear()
            self.outfit_combo.addItem("(Select an outfit)", 0)
            
            for outfit in self.outfits_list:
                premium_marker = " [Premium]" if outfit.premium else ""
                self.outfit_combo.addItem(
                    f"{outfit.name} ({outfit.id}){premium_marker}",
                    outfit.type_value
                )
            
            filename = os.path.basename(filepath)
            self.outfit_xml_label.setText(f"✓ {filename} ({len(self.outfits_list)} outfits)")
            self.outfit_xml_label.setStyleSheet("color: green;")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load outfits.xml:\n{e}")
    
    def load_mounts_xml(self):

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select mounts.xml", "", "XML files (*.xml);;All files (*.*)"
        )
        
        if not filepath:
            return
        
        try:
            self.mounts_list = XMLLoader.load_mounts(filepath)
            
            # Limpa e preenche o combo
            self.mount_combo.clear()
            self.mount_combo.addItem("(No mount)", 0)
            
            for mount in self.mounts_list:
                premium_marker = " [P]" if mount.premium else ""
                self.mount_combo.addItem(
                    f"{mount.name} (ID: {mount.id}){premium_marker}",
                    mount.type_value
                )
            
            filename = os.path.basename(filepath)
            self.mount_xml_label.setText(f"✓ {filename} ({len(self.mounts_list)} mounts)")
            self.mount_xml_label.setStyleSheet("color: green;")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load mounts.xml:\n{e}")
    
    def on_outfit_selected(self, index):
        """Quando um outfit é selecionado no combo"""
        if index > 0:
            looktype = self.outfit_combo.currentData()
            if looktype is not None:  # ← PROTEÇÃO ADICIONADA
                self.type_spin.setValue(looktype)
                self.looktype_data['type'] = looktype
                self.update_xml()
                self.update_outfit_preview()

    def on_mount_selected(self, index):
        """Quando uma mount é selecionada no combo"""
        mount_id = self.mount_combo.currentData()
        if mount_id is None:  # ← PROTEÇÃO ADICIONADA
            mount_id = 0
        self.mount_spin.setValue(mount_id)
        self.looktype_data['mount'] = mount_id
        self.update_xml()

    
    def on_type_manual_changed(self):
        """Quando o type é alterado manualmente"""
        self.looktype_data['type'] = self.type_spin.value()
        self.update_xml()
        self.update_outfit_preview()
    
    def on_mount_manual_changed(self):
        """Quando o mount ID é alterado manualmente"""
        self.looktype_data['mount'] = self.mount_spin.value()
        self.update_xml()
    
    def randomize_colors(self):
        """Gera cores aleatórias para todas as partes do corpo"""
        import random
        self.head_picker.setValue(random.randint(0, 132))
        self.body_picker.setValue(random.randint(0, 132))
        self.legs_picker.setValue(random.randint(0, 132))
        self.feet_picker.setValue(random.randint(0, 132))
    
    def on_npc_data_changed(self):
        """Atualiza os dados do NPC"""
        for field, widget in self.npc_widgets.items():
            if isinstance(widget, QLineEdit):
                self.npc_data[field] = widget.text()
            else:
                self.npc_data[field] = widget.value()
        
        self.update_xml()
    
    def on_looktype_changed(self):
        """Atualiza os valores do looktype"""
        self.looktype_data['type'] = self.type_spin.value()
        self.looktype_data['head'] = self.head_picker.value()
        self.looktype_data['body'] = self.body_picker.value()
        self.looktype_data['legs'] = self.legs_picker.value()
        self.looktype_data['feet'] = self.feet_picker.value()
        self.looktype_data['addons'] = self.addons_spin.value()
        self.looktype_data['mount'] = self.mount_spin.value()
        
        self.update_xml()
        self.update_outfit_preview()
    
    def update_xml(self):
        """Gera o XML do NPC"""
        npc = ET.Element('npc')
        npc.set('name', self.npc_data['name'])
        npc.set('script', self.npc_data['script'])
        npc.set('walkinterval', str(self.npc_data['walkinterval']))
        npc.set('floorchange', str(self.npc_data['floorchange']))
        npc.set('speechbubble', str(self.npc_data['speechbubble']))
        
        health = ET.SubElement(npc, 'health')
        health.set('now', str(self.npc_data.get('health_now', 100)))
        health.set('max', str(self.npc_data.get('health_max', 100)))
        
        look = ET.SubElement(npc, 'look')
        look.set('type', str(self.looktype_data['type']))
        look.set('head', str(self.looktype_data['head']))
        look.set('body', str(self.looktype_data['body']))
        look.set('legs', str(self.looktype_data['legs']))
        look.set('feet', str(self.looktype_data['feet']))
        look.set('addons', str(self.looktype_data['addons']))
        look.set('mount', str(self.looktype_data['mount']))

        xml_string = prettify_xml(npc)
        self.xml_display.setPlainText(xml_string)
    


    def change_direction(self, direction):
        """Muda a direção do preview (0=North, 1=East, 2=South, 3=West)"""
        self.current_direction = direction
        
        # Atualiza visual dos botões - MAPEAMENTO CORRETO
        buttons = {
            0: self.btn_north,   # North (⬆)
            1: self.btn_east,    # East (➡)
            2: self.btn_south,   # South (⬇)
            3: self.btn_west     # West (⬅)
        }
        
        for dir_id, btn in buttons.items():
            if dir_id == direction:
                btn.setStyleSheet("background-color: #007acc; color: white;")
            else:
                btn.setStyleSheet("")
        
        # Atualiza preview
        self.update_outfit_preview()


    def update_outfit_preview(self):
        """Atualiza o preview do outfit usando os sprites carregados"""
        if not self.spr_editor or not self.dat_editor:
            self.preview_info_label.setText("Load SPR/DAT for preview")
            return
        
        outfit_id = self.looktype_data['type']
        if outfit_id == 0 or outfit_id not in self.dat_editor.things.get('outfits', {}):
            self.outfit_preview.clear()
            self.outfit_preview.setText("N/A")
            return
        
        try:
            outfit_data = self.dat_editor.things['outfits'][outfit_id]
            texture_bytes = outfit_data['texture_bytes']
            
            # Parse do framegroup Idle
            offset = 1
            fg_type = texture_bytes[offset]
            offset += 1
            
            w, h = struct.unpack_from("BB", texture_bytes, offset)
            offset += 2
            
            if w > 1 or h > 1:
                offset += 1
            
            layers, px, py, pz, frames = struct.unpack_from("BBBBB", texture_bytes, offset)
            offset += 5
            
            if frames > 1:
                offset += 1 + 4 + 1 + (frames * 8)
            
            # Extrai sprite IDs
            total_sprites = w * h * px * py * pz * layers * frames
            spr_size = 4 if self.dat_editor.extended else 2
            fmt = "I" if spr_size == 4 else "H"
            
            sprite_ids = []
            for _ in range(total_sprites):
                sprite_id = struct.unpack_from(fmt, texture_bytes, offset)[0]
                sprite_ids.append(sprite_id)
                offset += spr_size
            
            # CÁLCULO DA DIREÇÃO - CORRIGIDO!
            # Ordem: layers → width → height → patternX (direções aqui!)
            sprites_per_direction = w * h * layers
            
            if px >= 4:  # ✓ DIREÇÕES EM PX, NÃO PY!
                direction = self.current_direction
                base_index = sprites_per_direction * direction  # ✓ MULTIPLICAR PELA DIREÇÃO DIRETAMENTE
                
                # Pega apenas os sprites dessa direção
                direction_sprites = sprite_ids[base_index:base_index + sprites_per_direction]
                
                composite = self.create_outfit_composite(
                    direction_sprites,
                    w, h, layers
                )
            else:
                # Sem direções, usa os primeiros sprites
                composite = self.create_outfit_composite(
                    sprite_ids[:sprites_per_direction],
                    w, h, layers
                )
            
            if composite:
                img_resized = composite.resize((96, 96), Image.NEAREST)
                from datspr import pil_to_qpixmap
                pixmap = pil_to_qpixmap(img_resized)
                self.outfit_preview.setPixmap(pixmap)
                
                # Mostra direção atual
                dir_names = ["North", "East", "South", "West"]
                dir_info = f" - {dir_names[self.current_direction]}" if px >= 4 else ""
                self.preview_info_label.setText(f"Outfit {outfit_id}{dir_info}")
            else:
                self.outfit_preview.setText("Error")
                
                
                
                
        except Exception as e:
            print(f"ERRO: {e}")
            import traceback
            traceback.print_exc()
            self.outfit_preview.setText("Error")



    def create_outfit_composite(self, sprite_ids, width, height, layers):
        """Cria composição invertendo X e Y e aplicando cores"""
        if not sprite_ids:
            return None
        
        try:
            composite = Image.new('RGBA', (width * 32, height * 32), (0, 0, 0, 0))
            
            idx = 0
            for layer in range(layers):
                for y in range(height):
                    for x in range(width):
                        if idx >= len(sprite_ids):
                            break
                        
                        sprite_id = sprite_ids[idx]
                        if sprite_id > 0:
                            img = self.spr_editor.get_sprite(sprite_id)
                            if img:
                                # APLICA AS CORES SELECIONADAS
                                img = self.apply_outfit_colors(
                                    img,
                                    self.looktype_data['head'],
                                    self.looktype_data['body'],
                                    self.looktype_data['legs'],
                                    self.looktype_data['feet']
                                )
                                
                                paste_x = (width - 1 - x) * 32
                                paste_y = (height - 1 - y) * 32
                                composite.paste(img, (paste_x, paste_y), img)
                        
                        idx += 1
            
            return composite
            
        except Exception as e:
            print(f"Erro: {e}")
            return None



    def apply_outfit_colors(self, sprite, head_color, body_color, legs_color, feet_color):
        """Aplica as cores do outfit baseado na máscara de template"""
        if not sprite:
            return sprite
        
        # Converte para RGB para manipulação
        sprite = sprite.convert('RGBA')
        pixels = sprite.load()
        width, height = sprite.size
        
        # Paleta HSI do Tibia (mesma do ColorPicker)
        tibia_colors = self.head_picker.tibia_colors  # Reutiliza a paleta
        
        # Cores da máscara (aproximadas)
        # Essas são as cores que o Tibia usa no sprite template
        MASK_YELLOW = (255, 255, 0)   # Head
        MASK_RED = (255, 0, 0)         # Body
        MASK_GREEN = (0, 255, 0)       # Legs
        MASK_BLUE = (0, 0, 255)      # Feet (cyan)
        
        def is_mask_color(pixel, mask_color, tolerance=50):
            """Verifica se um pixel é próximo de uma cor da máscara"""
            if len(pixel) < 4 or pixel[3] == 0:  # Transparente
                return False
            r, g, b = pixel[:3]
            mr, mg, mb = mask_color
            return (abs(r - mr) < tolerance and 
                    abs(g - mg) < tolerance and 
                    abs(b - mb) < tolerance)
        
        def get_brightness(pixel):
            """Calcula o brilho do pixel para manter sombras/luzes"""
            r, g, b = pixel[:3]
            return (r + g + b) / (3 * 255.0)
        
        def apply_color_with_brightness(color_id, brightness):
            """Aplica uma cor da paleta mantendo o brilho original"""
            if color_id == 0:
                return (0, 0, 0, 255)
            
            base_color = tibia_colors[color_id]
            r, g, b = base_color
            
            # Ajusta o brilho
            r = int(r * brightness)
            g = int(g * brightness)
            b = int(b * brightness)
            
            return (min(255, r), min(255, g), min(255, b), 255)
        
        # Aplica as cores
        for y in range(height):
            for x in range(width):
                pixel = pixels[x, y]
                
                if len(pixel) < 4 or pixel[3] == 0:  # Pula transparentes
                    continue
                
                brightness = get_brightness(pixel)
                
                # Verifica qual máscara corresponde e aplica a cor
                if is_mask_color(pixel, MASK_YELLOW):
                    pixels[x, y] = apply_color_with_brightness(head_color, brightness)
                elif is_mask_color(pixel, MASK_RED):
                    pixels[x, y] = apply_color_with_brightness(body_color, brightness)
                elif is_mask_color(pixel, MASK_GREEN):
                    pixels[x, y] = apply_color_with_brightness(legs_color, brightness)
                elif is_mask_color(pixel, MASK_BLUE):
                    pixels[x, y] = apply_color_with_brightness(feet_color, brightness)
        
        return sprite

    
    def copy_xml(self):
        """Copia o XML para a área de transferência"""
        xml_text = self.xml_display.toPlainText()
        if xml_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(xml_text)
    
    def paste_xml(self):
        """Cola XML da área de transferência e preenche os campos"""
        clipboard = QApplication.clipboard()
        xml_text = clipboard.text()
        
        if not xml_text:
            return
        
        try:
            root = ET.fromstring(xml_text)
            
            if root.tag == 'npc':
                self.npc_widgets['name'].setText(root.get('name', 'Alice'))
                self.npc_widgets['script'].setText(root.get('script', 'bless.lua'))
                self.npc_widgets['walkinterval'].setValue(int(root.get('walkinterval', 6000)))
                self.npc_widgets['floorchange'].setValue(int(root.get('floorchange', 0)))
                self.npc_widgets['speechbubble'].setValue(int(root.get('speechbubble', 3)))
                
                look = root.find('look')
                if look is not None:
                    self.type_spin.setValue(int(look.get('type', 0)))
                    self.head_picker.setValue(int(look.get('head', 0)))
                    self.body_picker.setValue(int(look.get('body', 0)))
                    self.legs_picker.setValue(int(look.get('legs', 0)))
                    self.feet_picker.setValue(int(look.get('feet', 0)))
                    self.addons_spin.setValue(int(look.get('addons', 0)))
                    self.mount_spin.setValue(int(look.get('mount', 0)))

            
            self.on_npc_data_changed()
            self.on_looktype_changed()
            
        except Exception as e:
            print(f"Erro ao fazer parse do XML: {e}")
            QMessageBox.warning(self, "Paste Error", f"Failed to parse XML:\n{e}")                  
