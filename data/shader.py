import sys, time
import os
import qdarktheme
import re

from PyQt6.QtWidgets import (QApplication, QMainWindow, QTextEdit, QVBoxLayout,
                             QHBoxLayout, QPushButton, QWidget, QSplitter,
                             QFileDialog, QSlider, QLabel, QTabWidget, QListWidget, QCheckBox,
                             QColorDialog, QInputDialog, QComboBox, QDialog,
                             QFormLayout, QSpinBox, QDialogButtonBox, QLineEdit, QMessageBox)

                               
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram, QOpenGLTexture
from PyQt6.QtCore import Qt, QTimer, QRegularExpression, QSize, QRect
from OpenGL import GL
from PyQt6.QtGui import QImage, QPixmap, QSyntaxHighlighter, QTextCharFormat, QFont, QColor, QPainter, QTextFormat

from PIL import Image

from data import BaseAI, GeminiAI, PerplexityAI
from data.base_ai import AIThread


from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
FRAGS_DIR = ASSETS_DIR / "frags"


VERT_SRC = """
#version 120
attribute vec2 a_Position;
attribute vec2 a_TexCoord;
varying vec2 v_TexCoord;
void main()
{
    v_TexCoord = a_TexCoord;
    gl_Position = vec4(a_Position, 0.0, 1.0);
}
"""

FRAG_DEFAULT = """
#version 120
varying vec2 v_TexCoord;
uniform sampler2D u_Tex0;
void main() {
gl_FragColor = texture2D(u_Tex0, v_TexCoord);
}
"""

class AIChatWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.conversation_history = []
        

        # Provedores disponíveis
        self.available_providers = {
            "Google Gemini": GeminiAI,
            "Perplexity AI": PerplexityAI,  # <- ADICIONE ESTA LINHA          
            # "Anthropic Claude": ClaudeAI,  # Descomentar quando implementar
            # "OpenAI GPT": OpenAIAI,        # Descomentar quando implementar
        }
        
        self.current_provider: BaseAI = None
        self.conversation_history = []
        self.last_code_suggestion = None
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        title_label = QLabel("AI Assistant")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 5px;")
        layout.addWidget(title_label)
        
        provider_layout = QHBoxLayout()
        provider_label = QLabel("Provedor:")
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(list(self.available_providers.keys()))
        self.provider_combo.currentTextChanged.connect(self.on_provider_changed)
        provider_layout.addWidget(provider_label)
        provider_layout.addWidget(self.provider_combo)
        layout.addLayout(provider_layout)


        model_layout = QHBoxLayout()
        model_label = QLabel("Model:")
        self.model_combo = QComboBox()
        self.model_combo.setEnabled(False) 
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.model_combo)
        layout.addLayout(model_layout)
                
        api_layout = QHBoxLayout()
        api_label = QLabel("API Key:")
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("Paste your Api key here")
        self.api_input.setEchoMode(QLineEdit.EchoMode.Password)
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.connect_ai)
        api_layout.addWidget(api_label)
        api_layout.addWidget(self.api_input)
        api_layout.addWidget(connect_btn)
        layout.addLayout(api_layout)
        
        project_mode_layout = QHBoxLayout()
        self.project_mode_checkbox = QCheckBox("Full Project Mode")
        self.project_mode_checkbox.setToolTip("Includes all .lua files in the folder in the context")
        project_mode_layout.addWidget(self.project_mode_checkbox)
        project_mode_layout.addStretch()
        layout.addLayout(project_mode_layout)
        

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setAcceptRichText(True)        
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e; 
                padding: 10px;
                font-size: 13px;
                line-height: 1.5;
            }
            code {
                background-color: #2d2d2d;
                padding: 2px 5px;
                border-radius: 3px;
                font-family: 'Consolas', monospace;
            }
            pre {
                background-color: #2d2d2d;
                padding: 10px;
                border-radius: 5px;
                overflow-x: auto;
            }
        """)
        layout.addWidget(self.chat_display)

        input_layout = QHBoxLayout()
        self.message_input = QTextEdit()
        self.message_input.setMaximumHeight(80)
        self.message_input.setPlaceholderText("Type your question here... (Ctrl+Enter to send)")
        self.message_input.installEventFilter(self)
        
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self.send_message)
        send_btn.setMinimumHeight(60)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(send_btn)
        layout.addLayout(input_layout)
        
        buttons_layout = QHBoxLayout()
        
        clear_btn = QPushButton("Clear Chat")
        clear_btn.clicked.connect(self.clear_chat)

       
        copy_code_btn = QPushButton("📋 Copiar Código")
        copy_code_btn.clicked.connect(self.copy_code_to_clipboard)
        copy_code_btn.setStyleSheet("background-color: #1a5490; color: white;")
        copy_code_btn.setToolTip("Copia o último código sugerido pela IA (limpo, sem formatação)")       
   
        buttons_layout.addWidget(copy_code_btn)
        buttons_layout.addWidget(clear_btn)
        
        
        
        
        layout.addLayout(buttons_layout)
        
        
        quick_actions_layout = QHBoxLayout()
        
        suggest_shader_btn = QPushButton("✨ Sugerir Shader OTClient")
        suggest_shader_btn.clicked.connect(self.suggest_otclient_shader)
        suggest_shader_btn.setStyleSheet("background-color: #4a148c; color: white;")
        suggest_shader_btn.setToolTip("Pede à IA para sugerir um shader para OTClient")
        
        quick_actions_layout.addWidget(suggest_shader_btn)
        quick_actions_layout.addStretch()  # Espaço à direita
        
        layout.addLayout(quick_actions_layout)        
        
        self.status_label = QLabel("Connect to the AI first")
        self.status_label.setStyleSheet("color: #ff9800; padding: 5px;")
        layout.addWidget(self.status_label)
        

                    
    def on_provider_changed(self, provider_name):
        """Chamado quando o usuário troca de provedor"""
        self.status_label.setText(f"Provedor selecionado: {provider_name}")
        self.status_label.setStyleSheet("color: #2196f3; padding: 5px;")
        
        if self.current_provider:
            self.current_provider.disconnect()
            self.current_provider = None
    
    def connect_ai(self):

        api_key = self.api_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Aviso", "Por favor, insira uma API Key válida")
            return

        provider_name = self.provider_combo.currentText()
        provider_class = self.available_providers.get(provider_name)
        
        if not provider_class:
            QMessageBox.critical(self, "Erro", "Provedor não encontrado")
            return

        try:

            if self.current_provider:
                self.current_provider.disconnect()
                self.current_provider = None

            self.current_provider = provider_class()
            success, message = self.current_provider.connect(api_key)
            
            if success:
                self.status_label.setText(f"✓ {message}")
                self.status_label.setStyleSheet("color: #4caf50; padding: 5px;")
                self.chat_display.append(f"<b>Sistema:</b> {message}! Como posso ajudar?<br><br>")
                
                self.populate_model_combo()
            else:
                QMessageBox.critical(self, "Erro", message)
                self.status_label.setText(f"✗ {message}")
                self.status_label.setStyleSheet("color: #f44336; padding: 5px;")
                
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao conectar: {str(e)}")


    def populate_model_combo(self):

        if not self.current_provider:
            return
        
        self.model_combo.clear()
        

        if hasattr(self.current_provider, 'get_available_models'):
            models = self.current_provider.get_available_models()
            self.model_combo.addItems(models)
            self.model_combo.setEnabled(True)

            if hasattr(self.current_provider, 'model_name') and self.current_provider.model_name:
                index = self.model_combo.findText(self.current_provider.model_name)
                if index >= 0:
                    self.model_combo.setCurrentIndex(index)
        else:
            self.model_combo.setEnabled(False)

    def on_model_changed(self, model_name):

        if not self.current_provider or not model_name:
            return
        
        # Verificar se o provedor tem método set_model
        if hasattr(self.current_provider, 'set_model'):
            success = self.current_provider.set_model(model_name)
            if success:
                self.status_label.setText(f"Modelo alterado para: {model_name}")
                self.status_label.setStyleSheet("color: #2196f3; padding: 5px;")
                self.chat_display.append(f"<b>Sistema:</b> Modelo alterado para <b>{model_name}</b><br><br>")
            else:
                QMessageBox.warning(self, "Aviso", f"Não foi possível trocar para o modelo {model_name}")



        
    def send_message(self):

        if not self.current_provider or not self.current_provider.is_connected:
            QMessageBox.warning(self, "Aviso", "Conecte-se à IA primeiro!")
            return
        
        message = self.message_input.toPlainText().strip()
        if not message:
            return
        
        # Exibir mensagem do usuário com formatação
        self.chat_display.append(f'''
        <div style="margin: 10px 0; padding: 10px; background-color: #1a3a52; border-radius: 8px;">
            <p style="color: #81d4fa; font-weight: bold; margin-bottom: 8px;">👤 Você:</p>
            <p style="color: #e0e0e0; line-height: 1.5;">{message}</p>
        </div>
        ''')
        
        self.message_input.clear()
        self.message_input.setEnabled(False)
        self.status_label.setText("⏳ Processando...")
        self.status_label.setStyleSheet("color: #2196f3; padding: 5px;")
        
        context_prompt = self.build_context_prompt(message)
        self.ai_thread = AIThread(self.current_provider, context_prompt)
        self.ai_thread.response_ready.connect(self.display_response)
        self.ai_thread.error_occurred.connect(self.display_error)
        self.ai_thread.start()

   
      
    def build_context_prompt(self, user_message):
        try:
            main_window = self.window()
            context_parts = []
            

            if hasattr(main_window, 'textedit'):
                shader_code = main_window.textedit.toPlainText()
                cursor = main_window.textedit.textCursor()
                selected_text = cursor.selectedText().replace('\u2029', '\n')
                
                context_parts.append("=== SHADER GLSL ATUAL (Fragment Shader) ===")
                
                if selected_text:
                    context_parts.append("```")
                    context_parts.append("// CÓDIGO SELECIONADO:")
                    context_parts.append(selected_text)
                    context_parts.append("```")
                    context_parts.append("\n=== SHADER COMPLETO (para contexto) ===")
                
                context_parts.append("```")
                context_parts.append(shader_code)
                context_parts.append("```")
                context_parts.append("")
                

                if hasattr(main_window, 'glwidget'):
                    if main_window.glwidget.background_loaded:
                        context_parts.append("📌 Background/Textura principal (u_Tex0): CARREGADO")
                    if main_window.glwidget.shader_texture_loaded:
                        context_parts.append("📌 Textura secundária do shader (u_Tex1): CARREGADO")
                    context_parts.append("")
            
            context_parts.append("=== PERGUNTA DO USUÁRIO ===")
            context_parts.append(user_message)
            context_parts.append("")
            context_parts.append("📋 INSTRUÇÕES:")
            context_parts.append("- Você é um especialista em GLSL (OpenGL Shading Language)")
            context_parts.append("- Analise o shader acima e forneça sugestões, correções ou melhorias")
            context_parts.append("- Se sugerir código, retorne APENAS o código completo do fragment shader dentro de ``````")
            context_parts.append("- Não adicione comentários fora do bloco de código")
            context_parts.append("- Sempre responda em português do Brasil")
            context_parts.append("- Uniformes disponíveis: u_Time (float), u_Tex0 (sampler2D), u_Tex1 (sampler2D), u_Resolution (vec2)")
            context_parts.append("- Varyings disponíveis: v_TexCoord (vec2)")
            context_parts.append("- CRÍTICO: Use TABS ou 4 ESPAÇOS para indentação em CADA LINHA de código")
            context_parts.append("- CRÍTICO: Mantenha a hierarquia de indentação: função main() > blocos if/for > conteúdo interno")
            context_parts.append("- Exemplo de indentação correta:")
            context_parts.append("```glsl")
            context_parts.append("void main() {")
            context_parts.append("    vec4 color = texture2D(u_Tex0, v_TexCoord);")
            context_parts.append("    if (color.a > 0.5) {")
            context_parts.append("        color.rgb *= 1.5;")
            context_parts.append("    }")
            context_parts.append("    gl_FragColor = color;")
            context_parts.append("}")
            context_parts.append("```")
            
            context_parts.append("- Não adicione comentários fora do bloco de código")
            context_parts.append("- Sempre responda em português do Brasil")
            
            return '\n'.join(context_parts)
            
        except Exception as e:
            print(f"Erro ao montar contexto para IA: {e}")
            return f"{user_message}\n\nResponda em português do Brasil sobre shaders GLSL."


    def copy_code_to_clipboard(self):

        if not self.last_code_suggestion:
            QMessageBox.warning(self, "Aviso", "A IA ainda não sugeriu nenhum código")
            return
        
        from PyQt6.QtWidgets import QApplication
        
        clipboard = QApplication.clipboard()
        clipboard.setText(self.last_code_suggestion)
        
        self.chat_display.append(
            "<p style='color: #4caf50'><b>✓ Sistema:</b> Código copiado para a área de transferência!</p><br>"
        )
        
        self.status_label.setText("✓ Código copiado!")
        self.status_label.setStyleSheet("color: #4caf50; padding: 5px;")
                                           
    def get_current_file_context(self, user_message):
        try:
            main_window = self.window()
            if not hasattr(main_window, "tabs"):
                return user_message

            current_editor = main_window.tabs.currentWidget()
            if not isinstance(current_editor, CodeEditor):
                return user_message

            context_parts = []


            file_path = getattr(current_editor, "file_path", None)
            file_content = current_editor.toPlainText()
            selected_text = current_editor.textCursor().selectedText().replace("\u2029", "\n")

            if file_path:
                file_name = os.path.basename(file_path)
                file_ext = os.path.splitext(file_path)[1]
                context_parts.append(f"Current file: {file_name} ({file_ext})")

            if self.project_mode_checkbox.isChecked() and hasattr(main_window, "working_directory"):
                context_parts.append("\nFULL PROJECT CONTEXT:\n")

                project_files = self.scan_project_files(main_window.working_directory)

                for pfile in project_files[:10]:  
                    try:
                        with open(pfile, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        preview = content[:500] + "..." if len(content) > 500 else content
                        
                        context_parts.append(
                            f"\n--- {os.path.basename(pfile)} ---\n```text\n{preview}\n```"
                        )
                    except Exception:
                        pass

            if selected_text:
                context_parts.append("\nSelected code:\n```")
                context_parts.append(selected_text)
                context_parts.append("```")

            elif file_content.strip():
                if len(file_content) > 4000:
                    preview = file_content[:4000]
                    context_parts.append("\nContent (first 4000 chars):\n```")
                    context_parts.append(preview)
                    context_parts.append("\n# ... (remaining omitted)\n```")
                else:
                    context_parts.append("\nFull content:\n```")
                    context_parts.append(file_content)
                    context_parts.append("```")


            context_parts.append(f"\nQuestion: {user_message}")
            context_parts.append(
                "\nIMPORTANT: If you suggest code, provide ONLY the full code ready to replace,"
                " with no explanations inside the code block."
            )
            context_parts.append("\nRespond in English.")

            return "\n".join(context_parts)

        except Exception as e:
            print(f"Error getting context: {e}")
            return user_message + "\n\nPlease respond in English."


    def scan_project_files(self, directory, extensions=None):
        project_files = []  
        
        if extensions is None:
            extensions = ['.lua', '.py', '.js', '.ts', '.json', '.xml', 
                         '.html', '.css', '.otui', '.otml', '.txt']
        
        try:
            for root, dirs, files in os.walk(directory):
                dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '__pycache__', '.vscode']]
                
                for file in files:
                    if any(file.endswith(ext) for ext in extensions):
                        project_files.append(os.path.join(root, file))
                        
                    if len(project_files) >= 15:
                        break
                if len(project_files) >= 15:
                    break
        except Exception as e:
            print(f"Error scanning project: {e}")
        
        return project_files

    
    def eventFilter(self, obj, event):
        if obj == self.message_input and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                self.send_message()
                return True
        return super().eventFilter(obj, event)
       
    def display_response(self, response):
        self.message_input.setEnabled(True)
        self.status_label.setText("✓ Resposta recebida")
        self.status_label.setStyleSheet("color: #4caf50; padding: 5px;")
        
        self.conversation_history.append({"role": "assistant", "content": response})
        
        # **ADICIONE/MOVA ESTA LINHA PARA CÁ - ANTES DO HTML**
        self.update_last_code_suggestion(response)
        
        # Converter markdown para HTML
        html_response = self.markdown_to_html(response)
        
        # Exibir resposta
        self.chat_display.append(
            f"<div style='margin: 10px 0; padding: 10px; background-color: #252525; border-radius: 8px;'>"
        )
        self.chat_display.append(
            f"<p style='color: #4fc3f7; font-weight: bold; margin-bottom: 8px;'>🤖 IA:</p>"
        )
        self.chat_display.append(html_response)
        self.chat_display.append("</div>")
        
        # Scroll para o final
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def suggest_otclient_shader(self):
        """Envia automaticamente pedido de sugestão de shader para OTClient"""
        if not self.current_provider or not self.current_provider.is_connected:
            QMessageBox.warning(self, "Aviso", "Conecte-se à IA primeiro!")
            return
        
        # Define a mensagem
        message = "Sugira um Shader para OTClient"
        
        # Coloca no input (opcional, para o usuário ver)
        self.message_input.setPlainText(message)
        
        # Envia automaticamente
        self.send_message()


    def markdown_to_html(self, text):

        def format_code_block(match):
            language = match.group(1) or 'text'
            code = match.group(2).strip()

            code = code.replace("&", "&amp;")
            code = code.replace("<", "&lt;")
            code = code.replace(">", "&gt;")
            code = code.replace(" ", "&nbsp;")  # **ADICIONE: Preserva espaços**
            code = code.replace("\n", "<br>")    # **ADICIONE: Preserva quebras de linha**            
                
            return f'''
            <div style="margin: 10px 0;">
                <div style="background-color: #1a1a1a; color: #00ff00; padding: 4px 8px; 
                            border-radius: 4px 4px 0 0; font-size: 11px; font-weight: bold;">
                    {language.upper()}
                </div>
                <pre style="background-color: #1e1e1e; color: #d4d4d4; padding: 15px; 
                            border-radius: 0 0 4px 4px; margin: 0; overflow-x: auto; 
                            font-family: 'Consolas', 'Monaco', monospace; font-size: 13px; 
                            line-height: 1.5; border: 1px solid #333;">{code}</pre>
            </div>
            '''
        
        text = re.sub(r'```(\w+)?\n(.*?)```', format_code_block, text, flags=re.DOTALL)
        
        text = re.sub(
            r'`([^`]+)`',
            r'<code style="background-color: #2d2d2d; color: #e06c75; padding: 2px 6px; '
            r'border-radius: 3px; font-family: monospace; font-size: 12px;">\1</code>',
            text
        )
        

        text = re.sub(r'\*\*(.+?)\*\*', r'<strong style="color: #61dafb;">\1</strong>', text)
        text = re.sub(r'__(.+?)__', r'<strong style="color: #61dafb;">\1</strong>', text)
        
        text = re.sub(r'\*(.+?)\*', r'<em style="color: #98c379;">\1</em>', text)
        text = re.sub(r'_(.+?)_', r'<em style="color: #98c379;">\1</em>', text)
        
        text = re.sub(r'^### (.+)$', r'<h3 style="color: #c678dd; margin: 15px 0 10px 0;">\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h2 style="color: #c678dd; margin: 15px 0 10px 0;">\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h1 style="color: #c678dd; margin: 15px 0 10px 0;">\1</h1>', text, flags=re.MULTILINE)
        
        text = re.sub(r'^\- (.+)$', r'<li style="margin-left: 20px; color: #abb2bf;">\1</li>', text, flags=re.MULTILINE)
        text = re.sub(r'^\* (.+)$', r'<li style="margin-left: 20px; color: #abb2bf;">\1</li>', text, flags=re.MULTILINE)
        
        text = re.sub(r'^\d+\. (.+)$', r'<li style="margin-left: 20px; color: #abb2bf;">\1</li>', text, flags=re.MULTILINE)
        

        paragraphs = text.split('\n\n')
        formatted_paragraphs = []
        for para in paragraphs:
            para = para.strip()
            if para and not para.startswith('<'):  
        
                para = para.replace('\n', '<br>')
                formatted_paragraphs.append(f'<p style="color: #abb2bf; margin: 8px 0; line-height: 1.6;">{para}</p>')
            elif para:
                formatted_paragraphs.append(para)
        
        return '\n'.join(formatted_paragraphs)


    def update_last_code_suggestion(self, raw_text):

        try:
            # Procurar blocos de código em markdown ```lang ... ```
            code_blocks = re.findall(r"```(?:[a-zA-Z0-9_+-]+)?\n(.*?)```", raw_text, re.DOTALL)
            if code_blocks:
                self.last_code_suggestion = code_blocks[-1].strip()
                return

            stripped = raw_text.strip()
            lines = stripped.splitlines()
            if len(lines) > 1 and any(kw in stripped for kw in ("def ", "class ", "{", "}", "function ", "local ")):
                self.last_code_suggestion = stripped
        except Exception as e:

            print(f"Erro ao extrair código da resposta da IA: {e}")
        
    def markdown_to_html(self, text):
        text = text.replace('\n\n', '</p><p>')
             

        text = re.sub(r'`([^`]+)`', r'<code style="background-color: #2d2d2d; padding: 2px 5px; border-radius: 3px;">\1</code>', text)
        

        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
        

        text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
        text = re.sub(r'_(.+?)_', r'<i>\1</i>', text)
        
        text = re.sub(r'^### (.+)$', r'<h3 style="color: #569CD6; margin-top: 10px;">\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h2 style="color: #569CD6; margin-top: 10px;">\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h1 style="color: #569CD6; margin-top: 10px;">\1</h1>', text, flags=re.MULTILINE)
        
        text = re.sub(r'^\* (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        text = re.sub(r'^- (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        

        text = re.sub(r'^\d+\. (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        

        text = re.sub(r'(<li>.*?</li>)(?=\n(?!<li>))', r'<ul>\1</ul>', text, flags=re.DOTALL)
        
        text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2" style="color: #4A9EFF;">\1</a>', text)
        
        text = text.replace('\n', '<br>')
        
        text = f'<p>{text}</p>'
        
        return text
   
    def display_error(self, error):
        self.chat_display.append(f"<b>Error:</b> {error}<br><br>")
        self.message_input.setEnabled(True)
        self.status_label.setText("Error during request")
        self.status_label.setStyleSheet("color: #f44336; padding: 5px;")
        
          
        
    
    def clear_chat(self):
        """Clears the chat history"""
        self.chat_display.clear()
        self.conversation_history = []

class ShaderWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.frag_source = FRAG_DEFAULT
        self.program = None
        self.start_time = time.time()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)
        self.vertices = None
        self.texCoords = None
        
        self.repeat_checkbox = QCheckBox("Repetir", self)
        self.repeat_checkbox.setChecked(True)
        self.repeat_checkbox.stateChanged.connect(self.set_wrap_mode_repeat)      


        self.background_texture = None
        self.background_loaded = False
        self.background_image = None
        
        self.shader_texture = None
        self.shader_texture_loaded = False
        self.shader_image = None
        
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        
        
    def set_wrap_mode_repeat(self, state):

        if self.background_texture is not None:
            if state == Qt.CheckState.Checked.value:
                self.background_texture.setWrapMode(QOpenGLTexture.WrapMode.Repeat)
            else:
                self.background_texture.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
            self.update()
            

    def rebuild_program(self):
        if self.program is not None:
            self.program.release()
            self.program = None
        
        prog = QOpenGLShaderProgram()
        if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERT_SRC):
            print("Erro vertex shader:\n", prog.log())
            return
        if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, self.frag_source):
            print("Erro fragment shader:\n", prog.log())
            return
        if not prog.link():
            print("Erro linkando programa:\n", prog.log())
            return
        
        self.program = prog
        print("Shader compilado e linkado com sucesso.")

    def initializeGL(self):

        GL.glClearColor(0.0, 0.0, 0.0, 0.0)  
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        

        self.vertices = [-1.0, -1.0,
                         1.0, -1.0,
                        -1.0,  1.0,
                         1.0,  1.0]
        

        self.texCoords = [0.0, 1.0, 
                         1.0, 1.0, 
                         0.0, 0.0,  
                         1.0, 0.0] 
        
        self.rebuild_program()

    def update_texcoords_with_zoom(self):

        zoom = self.zoom
        pan_x = self.pan_x
        pan_y = self.pan_y
        
    
        min_x = (0.5 - 0.5 / zoom) + pan_x
        max_x = (0.5 + 0.5 / zoom) + pan_x
        min_y = (0.5 - 0.5 / zoom) + pan_y
        max_y = (0.5 + 0.5 / zoom) + pan_y
        
      
        self.texCoords = [min_x, max_y,  
                         max_x, max_y,  
                         min_x, min_y,  
                         max_x, min_y]  

    def resizeGL(self, w, h):

        size = min(w, h)
        x_offset = (w - size) // 2
        y_offset = (h - size) // 2
        GL.glViewport(x_offset, y_offset, size, size)

    def paintGL(self):
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        if self.program is None:
            return
        
        self.program.bind()
        
        t = float(time.time() - self.start_time)
        loc_time = self.program.uniformLocation("u_Time")
        if loc_time != -1:
            self.program.setUniformValue(loc_time, t)
        
     
        if self.background_loaded and self.background_image is not None:
            loc_resolution = self.program.uniformLocation("u_Resolution")
            if loc_resolution != -1:
                self.program.setUniformValue(
                    loc_resolution,
                    float(self.background_image.width()),
                    float(self.background_image.height())
                )
        

        if self.background_loaded and self.background_texture is not None:
            self.background_texture.bind(0)
            tex0_loc = self.program.uniformLocation("u_Tex0")
            if tex0_loc != -1:
                self.program.setUniformValue(tex0_loc, 0)
        

        if self.shader_texture_loaded and self.shader_texture is not None:
            self.shader_texture.bind(1)
            tex1_loc = self.program.uniformLocation("u_Tex1")
            if tex1_loc != -1:
                self.program.setUniformValue(tex1_loc, 1)
        

        self.update_texcoords_with_zoom()
        

        pos_loc = self.program.attributeLocation("a_Position")
        if pos_loc != -1:
            GL.glEnableVertexAttribArray(pos_loc)
            GL.glVertexAttribPointer(pos_loc, 2, GL.GL_FLOAT, False, 0, self.vertices)
        

        texcoord_loc = self.program.attributeLocation("a_TexCoord")
        if texcoord_loc != -1:
            GL.glEnableVertexAttribArray(texcoord_loc)
            GL.glVertexAttribPointer(texcoord_loc, 2, GL.GL_FLOAT, False, 0, self.texCoords)
        
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
        
        if pos_loc != -1:
            GL.glDisableVertexAttribArray(pos_loc)
        if texcoord_loc != -1:
            GL.glDisableVertexAttribArray(texcoord_loc)
        
        if self.background_loaded and self.background_texture is not None:
            self.background_texture.release()
        if self.shader_texture_loaded and self.shader_texture is not None:
            self.shader_texture.release()
        
        self.program.release()

    def load_background(self, filepath: str):

        self.makeCurrent()
        
        img = QImage(filepath)
        if img.isNull():
            print(f"❌ Erro ao carregar background: {filepath}")
            self.doneCurrent()
            return
        
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        self.background_image = img
        
        if self.background_texture is not None:
            self.background_texture.destroy()
        
        self.background_texture = QOpenGLTexture(QOpenGLTexture.Target.Target2D)
        self.background_texture.setData(img, QOpenGLTexture.MipMapGeneration.GenerateMipMaps)
        self.background_texture.setMinificationFilter(QOpenGLTexture.Filter.Linear)
        self.background_texture.setMagnificationFilter(QOpenGLTexture.Filter.Linear)
        
        if self.repeat_checkbox.isChecked():
            self.background_texture.setWrapMode(QOpenGLTexture.WrapMode.Repeat)
        else:
            self.background_texture.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
        
        self.background_loaded = True
        
        print(f"✅ Background carregado: {filepath} ({img.width()}x{img.height()})")
        self.doneCurrent()
        self.update()

    def load_shader_texture(self, filepath: str):

        self.makeCurrent()
        
        img = QImage(filepath)
        if img.isNull():
            print(f"❌ Erro ao carregar textura do shader: {filepath}")
            self.doneCurrent()
            return
        
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        self.shader_image = img
        
        if self.shader_texture is not None:
            self.shader_texture.destroy()
        
        self.shader_texture = QOpenGLTexture(QOpenGLTexture.Target.Target2D)
        self.shader_texture.setData(img, QOpenGLTexture.MipMapGeneration.GenerateMipMaps)
        self.shader_texture.setMinificationFilter(QOpenGLTexture.Filter.Linear)
        self.shader_texture.setMagnificationFilter(QOpenGLTexture.Filter.Linear)
        self.shader_texture.setWrapMode(QOpenGLTexture.WrapMode.Repeat)
        self.shader_texture_loaded = True
        
        print(f"✅ Textura do shader carregada: {filepath} ({img.width()}x{img.height()})")
        self.doneCurrent()
        self.update()

    def update_fragment_shader(self, source: str):
        self.frag_source = source
        self.makeCurrent()
        self.rebuild_program()
        self.doneCurrent()
        self.update()

    def set_zoom(self, zoom_value):

        self.zoom = zoom_value / 100.0
        self.update()

    def reset_zoom(self):

        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.update()
        
               
    def export_frame(self, filepath):

        self.makeCurrent()
        frame = self.grabFramebuffer()
        if frame.save(filepath, "PNG"):
            print(f"✅ Frame exportado: {filepath}")
            return True
        else:
            print(f"❌ Erro ao exportar frame: {filepath}")
            return False
        self.doneCurrent()
        
        
        
    def export_animation(self, output_dir, num_frames=60, fps=30):

        os.makedirs(output_dir, exist_ok=True)
        
        for i in range(num_frames):

            self.start_time = time.time() - (i / fps)
            

            self.update()
            QApplication.processEvents()
            

            filename = f"frame_{i:04d}.png"
            filepath = os.path.join(output_dir, filename)
            self.export_frame(filepath)
        
        print(f"✅ {num_frames} frames exportados para {output_dir}")
        
        
    def export_frame_with_resolution(self, filepath, width, height):

        from PyQt6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
        
        self.makeCurrent()
        

        fbo_format = QOpenGLFramebufferObjectFormat()
        fbo_format.setAttachment(QOpenGLFramebufferObject.Attachment.CombinedDepthStencil)
        fbo_format.setSamples(4)  
        
       
        fbo = QOpenGLFramebufferObject(width, height, fbo_format)
        
        if not fbo.isValid():
            print(f"❌ Erro ao criar framebuffer {width}x{height}")
            self.doneCurrent()
            return False
        

        fbo.bind()
        

        GL.glViewport(0, 0, width, height)
        
 
        GL.glClearColor(0.0, 0.0, 0.0, 0.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        

        if self.program is not None:
            self.program.bind()
            t = float(time.time() - self.start_time)
            loc_time = self.program.uniformLocation("u_Time")
            if loc_time != -1:
                self.program.setUniformValue(loc_time, t)

            if self.background_loaded and self.background_image is not None:
                loc_resolution = self.program.uniformLocation("u_Resolution")
                if loc_resolution != -1:
                    self.program.setUniformValue(
                        loc_resolution,
                        float(self.background_image.width()),
                        float(self.background_image.height())
                    )
            
  
            if self.background_loaded and self.background_texture is not None:
                self.background_texture.bind(0)
                tex0_loc = self.program.uniformLocation("u_Tex0")
                if tex0_loc != -1:
                    self.program.setUniformValue(tex0_loc, 0)
            
            if self.shader_texture_loaded and self.shader_texture is not None:
                self.shader_texture.bind(1)
                tex1_loc = self.program.uniformLocation("u_Tex1")
                if tex1_loc != -1:
                    self.program.setUniformValue(tex1_loc, 1)
            
    
            self.update_texcoords_with_zoom()
            
        
            pos_loc = self.program.attributeLocation("a_Position")
            if pos_loc != -1:
                GL.glEnableVertexAttribArray(pos_loc)
                GL.glVertexAttribPointer(pos_loc, 2, GL.GL_FLOAT, False, 0, self.vertices)
            
            texcoord_loc = self.program.attributeLocation("a_TexCoord")
            if texcoord_loc != -1:
                GL.glEnableVertexAttribArray(texcoord_loc)
                GL.glVertexAttribPointer(texcoord_loc, 2, GL.GL_FLOAT, False, 0, self.texCoords)
            
            GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
            

            if pos_loc != -1:
                GL.glDisableVertexAttribArray(pos_loc)
            if texcoord_loc != -1:
                GL.glDisableVertexAttribArray(texcoord_loc)
            
            if self.background_loaded and self.background_texture is not None:
                self.background_texture.release()
            if self.shader_texture_loaded and self.shader_texture is not None:
                self.shader_texture.release()
            
            self.program.release()
        

        image = fbo.toImage()
        
 
        image = image.convertToFormat(QImage.Format.Format_RGBA8888)
        
        fbo.release()
        

        success = image.save(filepath, "PNG")
        
        if success:
            print(f"✅ Frame {width}x{height} exportado: {filepath}")
        else:
            print(f"❌ Erro ao exportar {filepath}")
        
        self.doneCurrent()
        return success

                    
class SquareWidget(QWidget):

    def __init__(self, child_widget, parent=None):
        super().__init__(parent)
        self.child = child_widget

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addStretch()
        container_layout.addWidget(child_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        container_layout.addStretch()
        container.setLayout(container_layout)
        layout.addWidget(container)
        self.setLayout(layout)

    def resizeEvent(self, event):
        size = min(event.size().width(), event.size().height())
        self.child.setFixedSize(size, size)
        super().resizeEvent(event)
        
       
class GLSLHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.highlighting_rules = []
        
        # Palavras-chave GLSL
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#C586C0"))  # Roxo
        keyword_format.setFontWeight(QFont.Weight.Bold)
        
        keywords = [
            "attribute", "const", "uniform", "varying", "break", "continue",
            "do", "for", "while", "if", "else", "in", "out", "inout",
            "true", "false", "discard", "return", "struct"
        ]
        
        for keyword in keywords:
            pattern = QRegularExpression(f"\\b{keyword}\\b")
            self.highlighting_rules.append((pattern, keyword_format))
        
        # Tipos de dados
        type_format = QTextCharFormat()
        type_format.setForeground(QColor("#4EC9B0"))  # Ciano
        
        types = [
            "void", "bool", "int", "float", "vec2", "vec3", "vec4",
            "bvec2", "bvec3", "bvec4", "ivec2", "ivec3", "ivec4",
            "mat2", "mat3", "mat4", "sampler2D", "samplerCube"
        ]
        
        for glsl_type in types:
            pattern = QRegularExpression(f"\\b{glsl_type}\\b")
            self.highlighting_rules.append((pattern, type_format))
        
        # Funções built-in
        function_format = QTextCharFormat()
        function_format.setForeground(QColor("#DCDCAA"))  # Amarelo
        
        functions = [
            "texture2D", "texture", "mix", "smoothstep", "step", "clamp",
            "sin", "cos", "tan", "abs", "pow", "sqrt", "length", "distance",
            "dot", "cross", "normalize", "reflect", "mod", "fract", "floor",
            "ceil", "min", "max", "radians", "degrees", "atan", "asin", "acos"
        ]
        
        for func in functions:
            pattern = QRegularExpression(f"\\b{func}\\b")
            self.highlighting_rules.append((pattern, function_format))
        
        # Números
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#B5CEA8"))  # Verde claro
        pattern = QRegularExpression(r"\b\d+\.?\d*\b")
        self.highlighting_rules.append((pattern, number_format))
        
        # Comentários de linha
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955"))  # Verde escuro
        comment_format.setFontItalic(True)
        pattern = QRegularExpression("//[^\n]*")
        self.highlighting_rules.append((pattern, comment_format))
        
        # Comentários de bloco
        self.multiline_comment_format = QTextCharFormat()
        self.multiline_comment_format.setForeground(QColor("#6A9955"))
        self.multiline_comment_format.setFontItalic(True)
        self.comment_start_expression = QRegularExpression("/\\*")
        self.comment_end_expression = QRegularExpression("\\*/")
    
    def highlightBlock(self, text):
        # Aplica regras simples
        for pattern, fmt in self.highlighting_rules:
            iterator = pattern.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)
        
        # Comentários multilinha
        self.setCurrentBlockState(0)
        start_index = 0
        if self.previousBlockState() != 1:
            start_index = self.comment_start_expression.match(text).capturedStart()
        
        while start_index >= 0:
            match = self.comment_end_expression.match(text, start_index)
            end_index = match.capturedStart()
            
            if end_index == -1:
                self.setCurrentBlockState(1)
                comment_length = len(text) - start_index
            else:
                comment_length = end_index - start_index + match.capturedLength()
            
            self.setFormat(start_index, comment_length, self.multiline_comment_format)
            start_index = self.comment_start_expression.match(text, start_index + comment_length).capturedStart()
        
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeeditor = editor

    def sizeHint(self):
        return QSize(self.codeeditor.linenumberareawidth(), 0)

    def paintEvent(self, event):
        self.codeeditor.linenumberareapaintevent(event)


class CodeEditor(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.linenumberarea = LineNumberArea(self)
        
        # Conecta sinais
        self.document().blockCountChanged.connect(self.updatelinenumberareawidth)
        self.verticalScrollBar().valueChanged.connect(self.updatelinenumberarea_scroll)
        self.textChanged.connect(self.updatelinenumberarea_content)
        self.cursorPositionChanged.connect(self.highlightcurrentline)
        
        self.updatelinenumberareawidth(0)
        self.highlightcurrentline()
    
    def linenumberareawidth(self):
        """Calcula a largura necessária para os números de linha"""
        digits = 1
        max_num = max(1, self.document().blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1
        
        space = 10 + self.fontMetrics().horizontalAdvance('9') * digits
        return space
    
    def updatelinenumberareawidth(self, _):

        self.setViewportMargins(self.linenumberareawidth(), 0, 0, 0)
    
    def updatelinenumberarea_scroll(self, _):

        self.linenumberarea.update()
    
    def updatelinenumberarea_content(self):

        self.linenumberarea.update()
    
    def resizeEvent(self, event):

        super().resizeEvent(event)
        cr = self.contentsRect()
        self.linenumberarea.setGeometry(
            QRect(cr.left(), cr.top(), self.linenumberareawidth(), cr.height())
        )
    
    def highlightcurrentline(self):

        extra_selections = []
        
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor("#2d2d30")
            
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        
        self.setExtraSelections(extra_selections)
    
    def linenumberareapaintevent(self, event):

        painter = QPainter(self.linenumberarea)
        painter.fillRect(event.rect(), QColor("#1e1e1e"))  #
        

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        

        content_offset = self.contentOffset()
        block_geometry = self.document().documentLayout().blockBoundingRect(block)
        top = int(block_geometry.translated(content_offset).top())
        bottom = top + int(block_geometry.height())
        

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                
      
                if block_number == self.textCursor().blockNumber():
                    painter.setPen(QColor("#ffffff"))  
                    painter.setFont(self.font())
                else:
                    painter.setPen(QColor("#858585"))  
                
                painter.drawText(
                    0, top,
                    self.linenumberarea.width() - 5,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number
                )
            
            block = block.next()
            top = bottom
            block_geometry = self.document().documentLayout().blockBoundingRect(block)
            bottom = top + int(block_geometry.height())
            block_number += 1
    
    def firstVisibleBlock(self):

        block = self.document().firstBlock()
        while block.isValid():
            if block.isVisible():
                block_geometry = self.document().documentLayout().blockBoundingRect(block)
                if block_geometry.translated(self.contentOffset()).top() >= 0:
                    return block
            block = block.next()
        return self.document().firstBlock()
    
    def contentOffset(self):
        """Retorna o offset do conteúdo (scroll)"""
        from PyQt6.QtCore import QPointF
        vertical_offset = -self.verticalScrollBar().value()
        horizontal_offset = -self.horizontalScrollBar().value()
        return QPointF(horizontal_offset, vertical_offset)

       
class ShaderEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shader Editor")
        self.setGeometry(100, 100, 800, 800)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

 
        btn_layout = QHBoxLayout()

        load_background_btn = QPushButton("Carregar Background")
        load_background_btn.clicked.connect(self.load_background)
        btn_layout.addWidget(load_background_btn)
                      
        load_shader_tex_btn = QPushButton("Carregar Textura Shader")
        load_shader_tex_btn.clicked.connect(self.load_shader_texture)
        btn_layout.addWidget(load_shader_tex_btn)
        
        update_btn = QPushButton("Atualizar Shader")
        update_btn.clicked.connect(self.apply_shader)
        btn_layout.addWidget(update_btn)


        save_btn = QPushButton("Salvar Como")
        save_btn.clicked.connect(self.save_shader_as)
        btn_layout.addWidget(save_btn)


        btn_layout.addSpacing(20)
        zoom_label = QLabel("Zoom:")
        btn_layout.addWidget(zoom_label)


        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(1)  # 0.2x
        self.zoom_slider.setMaximum(500)  # 5.0x
        self.zoom_slider.setValue(100)  # 1.0x (padrão)
        self.zoom_slider.setMaximumWidth(200)
        self.zoom_slider.sliderMoved.connect(self.on_zoom_change)
        btn_layout.addWidget(self.zoom_slider)
        
        self.zoom_value_label = QLabel("1.00x")
        btn_layout.addWidget(self.zoom_value_label)
        
        reset_zoom_btn = QPushButton("Reset Zoom")
        reset_zoom_btn.clicked.connect(self.reset_zoom)
        btn_layout.addWidget(reset_zoom_btn)
        
        
        export_frame_btn = QPushButton("Exportar Frame")
        export_frame_btn.clicked.connect(self.export_single_frame)
        btn_layout.addWidget(export_frame_btn)

        export_anim_btn = QPushButton("Exportar Animação")
        export_anim_btn.clicked.connect(self.export_animation_dialog)
        btn_layout.addWidget(export_anim_btn)
        
       
        pick_color_btn = QPushButton("Pick Color")
        pick_color_btn.clicked.connect(self.pickcolor)           
        btn_layout.addWidget(pick_color_btn)
     
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # Criar splitter HORIZONTAL principal (Editor+Preview à esquerda | Chat à direita)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. SPLITTER VERTICAL À ESQUERDA (Editor em cima, Preview embaixo)
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # 1.1 TabWidget (Editor + Shaders + Modelo de Teste)
        self.tab_widget = QTabWidget()

        self.shader_update_timer = QTimer()
        self.shader_update_timer.setSingleShot(True)
        self.shader_update_timer.timeout.connect(self.apply_shader)

        self.text_edit = CodeEditor()
        self.text_edit.setPlainText(FRAG_DEFAULT)
        font = QFont("Consolas", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.text_edit.setFont(font)
        self.highlighter = GLSLHighlighter(self.text_edit.document())
        self.text_edit.textChanged.connect(self.schedule_shader_update)
        self.tab_widget.addTab(self.text_edit, "Editor")
        self.text_edit.setTabStopDistance(4 * self.text_edit.fontMetrics().horizontalAdvance(' '))
        self.text_edit.setStyleSheet("""
            QTextEdit {
                padding: 8px;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
            }
        """)

        self.gl_widget = ShaderWidget()
        squarewrapper = SquareWidget(self.gl_widget)
        right_splitter.addWidget(self.tab_widget)
        right_splitter.addWidget(squarewrapper)

        # Lista de shaders e assets
        self.shader_list = QListWidget()
        self.shader_list.itemClicked.connect(self.load_shader_from_list)
        self.tab_widget.addTab(self.shader_list, "Shaders Prontos")

        assetswidget = QWidget()
        assetslayout = QVBoxLayout(assetswidget)
        infolabel = QLabel("Clique para testar shaders em imagens predefinidas")
        infolabel.setWordWrap(True)
        assetslayout.addWidget(infolabel)

        #standalone - não remover
        # self.testassets = {
            # "Escudo": "assets/shield.png",
            # "Espada": "assets/sword.png",
            # "Machado": "assets/axe.png",
            # "Armadura": "assets/armor.png",
            # "Outfit 1": "assets/outfit1.png",
            # "Outfit 2": "assets/outfit2.png",
            # "Tile 1": "assets/t2.png",
            # "Tile 2": "assets/t3.png",
            # "Paisagem 1": "assets/landscape1.png",
            # "Paisagem 2": "assets/landscape2.png",
          #standalone - não remover


          
        self.testassets = {
            "Escudo": str(IMAGES_DIR / "shield.png"),
            "Espada": str(IMAGES_DIR / "sword.png"),
            "Machado": str(IMAGES_DIR / "axe.png"),
            "Armadura": str(IMAGES_DIR / "armor.png"),
            "Outfit 1": str(IMAGES_DIR / "outfit1.png"),
            "Outfit 2": str(IMAGES_DIR / "outfit2.png"),
            "Tile 1": str(IMAGES_DIR / "t2.png"),
            "Tile 2": str(IMAGES_DIR / "t3.png"),
            "Paisagem 1": str(IMAGES_DIR / "landscape1.png"),
            "Paisagem 2": str(IMAGES_DIR / "landscape2.png"),        
        
     
           }
        for assetname, assetpath in self.testassets.items():
            btn = QPushButton(assetname)
            btn.clicked.connect(lambda checked, path=assetpath, name=assetname: 
                               self.load_test_asset(path, name))
            assetslayout.addWidget(btn)

        assetslayout.addStretch()
        self.tab_widget.addTab(assetswidget, "Modelo de Teste")


        right_splitter.setSizes([600, 400])

        main_splitter.addWidget(right_splitter)

        self.aichat = AIChatWidget(self)
        self.aichat.setMinimumWidth(280)
        self.aichat.setMaximumWidth(450)
        main_splitter.addWidget(self.aichat)

        main_splitter.setSizes([1050, 350])

        layout.addWidget(main_splitter)

        self.load_shader_files()

        
    def toggle_ai_chat(self):
        """Mostra ou oculta o chat de IA"""
        chat = self.main_splitter.widget(2)
        if chat.isVisible():
            chat.hide()
        else:
            chat.show()        

    

    def schedule_shader_update(self):
        """Agenda a atualização do shader após 500ms sem alterações"""
        self.shader_update_timer.stop()
        self.shader_update_timer.start(500) 
        
    def pickcolor(self):

        color = QColorDialog.getColor()
        if color.isValid():
            r = color.red() / 255.0
            g = color.green() / 255.0
            b = color.blue() / 255.0
            color_code = f"vec3({r:.3f}, {g:.3f}, {b:.3f})"
            

            cursor = self.text_edit.textCursor()
            cursor.insertText(color_code)
            
            print(f"✅ Cor inserida: {color_code}")


    def load_background(self):

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Carregar Background (Paisagem/Item/Outfit)",
            "",
            "PNG Images (*.png);;All Files (*)"
        )
        if filepath:
            self.gl_widget.load_background(filepath)
    
    def load_shader_texture(self):

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Carregar Textura do Shader (Fog/Rain/Aura)",
            "",
            "PNG Images (*.png);;All Files (*)"
        )
        if filepath:
            self.gl_widget.load_shader_texture(filepath)
    
    def load_test_asset(self, asset_path, asset_name):
        """Carrega asset de teste como BACKGROUND"""
        full_path = os.path.join(os.path.dirname(__file__), asset_path)
        
        if not os.path.exists(full_path):
            print(f"⚠︝ Asset não encontrado: {full_path}")
            return
        
        self.gl_widget.load_background(full_path)  
        print(f"✅ Background carregado: {asset_name}")

    def load_shader_files(self):
        
       #standalone - não remover
       # frags_dir = os.path.join(os.path.dirname(__file__), "frags")
        frags_dir = FRAGS_DIR    
        
        if not os.path.exists(frags_dir):
            print(f"⚠︝ Pasta 'frags/' não encontrada em: {frags_dir}")
            return
        

        shader_files = [f for f in os.listdir(frags_dir) if f.endswith('.frag')]
        
        if not shader_files:
            print("⚠︝ Nenhum arquivo .frag encontrado na pasta frags/")
            return
        
        # Adiciona à lista
        for shader_file in sorted(shader_files):
            self.shader_list.addItem(shader_file)
        
        print(f"✅ {len(shader_files)} shaders carregados da pasta frags/")


    def load_shader_from_list(self, item):

        shader_name = item.text()
               #standalone - não remover #standalone - não remover
        # frags_dir = os.path.join(os.path.dirname(__file__), "frags")
        frags_dir = FRAGS_DIR         
        shader_path = os.path.join(frags_dir, shader_name)
        
        try:
            with open(shader_path, 'r', encoding='utf-8') as f:
                shader_code = f.read()
            
 
            self.text_edit.setPlainText(shader_code)
            
   
            self.apply_shader()
            

            self.tab_widget.setCurrentIndex(0)
            
            print(f"✅ Shader carregado: {shader_name}")
        except Exception as e:
            print(f"❌ Erro ao carregar shader {shader_name}: {e}")

    def load_image(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Carregar Imagem",
            "",
            "PNG Images (*.png);;All Files (*)"
        )
        if filepath:
            self.gl_widget.load_image(filepath)

    def apply_shader(self):
        src = self.text_edit.toPlainText()
        self.gl_widget.update_fragment_shader(src)

    def on_zoom_change(self, value):

        zoom = value / 100.0
        self.gl_widget.set_zoom(value)
        self.zoom_value_label.setText(f"{zoom:.2f}x")

    def reset_zoom(self):

        self.zoom_slider.setValue(100)
        self.gl_widget.reset_zoom()
        self.zoom_value_label.setText("1.00x")
        
        
    def save_shader_as(self):
        
        #standalone - não remover
        #frags_dir = os.path.join(os.path.dirname(__file__), "frags")
        frags_dir = FRAGS_DIR 
        

        if not os.path.exists(frags_dir):
            os.makedirs(frags_dir)
            print(f"✅ Pasta 'frags/' criada em: {frags_dir}")
        

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Shader Como",
            frags_dir,
            "Fragment Shader (*.frag);;All Files (*)"
        )
        
        if not filepath:
            return  
        

        if not filepath.endswith('.frag'):
            filepath += '.frag'
        
        try:
           
            shader_code = self.text_edit.toPlainText()
            
          
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(shader_code)
            
            print(f"✅ Shader salvo: {os.path.basename(filepath)}")
            
      
            self.refresh_shader_list()
            
        except Exception as e:
            print(f"❌ Erro ao salvar shader: {e}")
            
    def refresh_shader_list(self):

        self.shader_list.clear()
        self.load_shader_files()

    def export_single_frame(self):


        dialog = QDialog(self)
        dialog.setWindowTitle("Exportar Frame")
        layout = QFormLayout()
        

        resolution_combo = QComboBox()
        resolution_combo.addItems([
            "32x32",
            "64x64",
            "96x96",
            "128x128",
            "256x256",
            "512x512",
            "Customizado"
        ])
        resolution_combo.setCurrentIndex(1)  
        layout.addRow("Resolução:", resolution_combo)
        
        width_spin = QSpinBox()
        width_spin.setRange(1, 4096)
        width_spin.setValue(64)
        width_spin.setEnabled(False)
        layout.addRow("Largura Custom:", width_spin)
        
        height_spin = QSpinBox()
        height_spin.setRange(1, 4096)
        height_spin.setValue(64)
        height_spin.setEnabled(False)
        layout.addRow("Altura Custom:", height_spin)
        
        def on_resolution_change(index):
            is_custom = resolution_combo.currentText() == "Customizado"
            width_spin.setEnabled(is_custom)
            height_spin.setEnabled(is_custom)
        
        resolution_combo.currentIndexChanged.connect(on_resolution_change)
        

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        
        dialog.setLayout(layout)
        
  
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        resolution_text = resolution_combo.currentText()
        
        if resolution_text == "32x32":
            width, height = 32, 32
        elif resolution_text == "64x64":
            width, height = 64, 64
        elif resolution_text == "96x96":
            width, height = 96, 96
        elif resolution_text == "128x128":
            width, height = 128, 128
        elif resolution_text == "256x256":
            width, height = 256, 256
        elif resolution_text == "512x512":
            width, height = 512, 512
        else:  
            width = width_spin.value()
            height = height_spin.value()
        

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar Frame Como",
            f"frame_{width}x{height}.png",
            "PNG Images (*.png);;All Files (*)"
        )
        
        if not filepath:
            return
        
        if not filepath.endswith('.png'):
            filepath += '.png'
        
 
        self.gl_widget.export_frame_with_resolution(filepath, width, height)

    def export_animation_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Exportar Animação")
        layout = QFormLayout()

        # Formato de saída
        format_combo = QComboBox()
        format_combo.addItems(["PNG Frames", "GIF Animado"])
        format_combo.setCurrentIndex(0)
        layout.addRow("Formato:", format_combo)

        resolution_combo = QComboBox()
        resolution_combo.addItems([
            "32x32",
            "64x64",
            "128x128",
            "256x256"
        ])
        resolution_combo.setCurrentIndex(1)  # 64x64 como padrão
        layout.addRow("Resolução:", resolution_combo)

        frames_spin = QSpinBox()
        frames_spin.setRange(1, 300)
        frames_spin.setValue(60)
        layout.addRow("Frames:", frames_spin)

        fps_spin = QSpinBox()
        fps_spin.setRange(1, 60)
        fps_spin.setValue(30)
        layout.addRow("FPS:", fps_spin)


        loop_check = QCheckBox("Loop Infinito")
        loop_check.setChecked(True)
        layout.addRow("GIF Loop:", loop_check)

        bg_color_combo = QComboBox()
        bg_color_combo.addItems(["Transparente (Preto)", "Branco", "Personalizado"])
        bg_color_combo.setCurrentIndex(0)
        layout.addRow("Fundo GIF:", bg_color_combo)
               

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        dialog.setLayout(layout)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        resolution_text = resolution_combo.currentText()
        if "32x32" in resolution_text:
            width, height = 32, 32
        elif "64x64" in resolution_text:
            width, height = 64, 64
        elif "128x128" in resolution_text:
            width, height = 128, 128
        else:
            width, height = 256, 256

        num_frames = frames_spin.value()
        fps = fps_spin.value()
        export_gif = format_combo.currentText() == "GIF Animado"
        loop_forever = loop_check.isChecked()

        if export_gif:

            filepath, _ = QFileDialog.getSaveFileName(
                self,
                "Salvar Animação Como",
                f"animation_{width}x{height}_{fps}fps.gif",
                "GIF Images (*.gif);;All Files (*)"
            )

            if not filepath:
                return

            if not filepath.endswith('.gif'):
                filepath += '.gif'

            bg_choice = bg_color_combo.currentText()
            self.export_animation_as_gif(filepath, width, height, num_frames, fps, loop_forever, bg_choice)

        else:

            output_dir = QFileDialog.getExistingDirectory(
                self,
                "Escolher Pasta para Exportar Frames",
                ""
            )

            if not output_dir:
                return

            self.export_animation_as_frames(output_dir, width, height, num_frames, fps)

    def export_animation_as_frames(self, output_dir, width, height, num_frames, fps):

        os.makedirs(output_dir, exist_ok=True)
        original_start = self.gl_widget.start_time

        print(f"🎬 Iniciando exportação de {num_frames} frames em {width}x{height}...")

        for i in range(num_frames):
            self.gl_widget.start_time = time.time() - (i / fps)
            self.gl_widget.update()
            QApplication.processEvents()

            filename = f"frame_{i:04d}.png"
            filepath = os.path.join(output_dir, filename)
            self.gl_widget.export_frame_with_resolution(filepath, width, height)

            if (i + 1) % 10 == 0:
                print(f"📊 Progresso: {i + 1}/{num_frames} frames")

        self.gl_widget.start_time = original_start
        print(f"✅ {num_frames} frames ({width}x{height}) exportados para {output_dir}")

    def export_animation_as_gif(self, filepath, width, height, num_frames, fps, loop_forever, bg_choice="Transparente (Preto)"):

        import tempfile
        import shutil
        

        if bg_choice == "Branco":
            bg_color = (255, 255, 255)
        elif bg_choice == "Personalizado":
            color = QColorDialog.getColor()
            if color.isValid():
                bg_color = (color.red(), color.green(), color.blue())
            else:
                bg_color = (0, 0, 0)
        else:  
            bg_color = (0, 0, 0)
        
        temp_dir = tempfile.mkdtemp()
        original_start = self.gl_widget.start_time
        
        print(f"🎬 Iniciando exportação de GIF {width}x{height} com {num_frames} frames...")
        print(f"🎨 Cor de fundo: RGB{bg_color}")  
        
        frames = []
        
        try:
            for i in range(num_frames):
                self.gl_widget.start_time = time.time() - (i / fps)
                self.gl_widget.update()
                QApplication.processEvents()
                
                temp_file = os.path.join(temp_dir, f"frame_{i:04d}.png")
                self.gl_widget.export_frame_with_resolution(temp_file, width, height)
                
                img = Image.open(temp_file)
                
                if img.mode == 'RGBA':
                    rgb_img = Image.new('RGB', img.size, bg_color)
                    rgb_img.paste(img, mask=img.split()[3])
                    frames.append(rgb_img)
                else:
                    frames.append(img.convert('RGB'))
                
                if (i + 1) % 10 == 0:
                    print(f"📊 Progresso: {i + 1}/{num_frames} frames")
            
            # Criar GIF
            duration = int(1000 / fps)
            loop_value = 0 if loop_forever else 1
            
            frames[0].save(
                filepath,
                save_all=True,
                append_images=frames[1:],
                duration=duration,
                loop=loop_value,
                optimize=True,
                disposal=2
            )
            
            self.gl_widget.start_time = original_start
            print(f"✅ GIF exportado: {filepath}")
            print(f"   Fundo: RGB{bg_color}")
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarktheme.load_stylesheet())
    w = ShaderEditor()
    w.resize(1200, 700)
    w.show()
    sys.exit(app.exec())

