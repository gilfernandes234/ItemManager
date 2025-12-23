import sys, time
import os

from PyQt6.QtWidgets import (QApplication, QMainWindow, QTextEdit, QVBoxLayout,
                             QHBoxLayout, QPushButton, QWidget, QSplitter,
                             QFileDialog, QSlider, QLabel, QTabWidget, QListWidget, QCheckBox,
                             QColorDialog, QInputDialog, QComboBox, QDialog,
                             QFormLayout, QSpinBox, QDialogButtonBox)

                               
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram, QOpenGLTexture
from PyQt6.QtCore import Qt, QTimer, QRegularExpression
from OpenGL import GL
from PyQt6.QtGui import QImage, QPixmap, QSyntaxHighlighter, QTextCharFormat, QFont, QColor

from pathlib import Path
import qdarktheme  
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
        
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.tab_widget = QTabWidget()
        
        self.shader_update_timer = QTimer()
        self.shader_update_timer.setSingleShot(True)
        self.shader_update_timer.timeout.connect(self.apply_shader)        
        
        self.text_edit = QTextEdit()
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
        square_wrapper = SquareWidget(self.gl_widget)
        
        splitter.addWidget(self.tab_widget)  
        splitter.addWidget(square_wrapper)
        splitter.setSizes([350, 350])
        
        layout.addWidget(splitter)
        
        
        self.shader_list = QListWidget()
        self.shader_list.itemClicked.connect(self.load_shader_from_list)
        self.tab_widget.addTab(self.shader_list, "Shaders Prontos")
        

        assets_widget = QWidget()
        assets_layout = QVBoxLayout(assets_widget)
        
        info_label = QLabel("Clique para testar shaders em imagens predefinidas:")
        info_label.setWordWrap(True)
        assets_layout.addWidget(info_label)
               
        self.test_assets = {
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
        
                    

        for asset_name, asset_path in self.test_assets.items():
            btn = QPushButton(asset_name)
            btn.clicked.connect(lambda checked, path=asset_path, name=asset_name: 
                              self.load_test_asset(path, name))
            assets_layout.addWidget(btn)
        
        assets_layout.addStretch()
        
        self.tab_widget.addTab(assets_widget, "Modelo de Teste")
        
        self.load_shader_files() 
        
        
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
        full_path = Path(asset_path)

        if not full_path.is_absolute():
            full_path = IMAGES_DIR / asset_path

        if not full_path.exists():
            print(f"⚠︝ Asset não encontrado: {full_path}")
            return

        self.gl_widget.load_background(str(full_path))
        print(f"✅ Background carregado: {asset_name}")


    def load_shader_files(self):
        frags_dir = FRAGS_DIR

        if not frags_dir.exists():
            print(f"⚠︝ Pasta 'frags/' não encontrada em: {frags_dir}")
            return

        shader_files = [f.name for f in frags_dir.glob("*.frag")]

        if not shader_files:
            print("⚠︝ Nenhum arquivo .frag encontrado na pasta frags/")
            return

        for shader_file in sorted(shader_files):
            self.shader_list.addItem(shader_file)

        print(f"✅ {len(shader_files)} shaders carregados da pasta frags/")


    def load_shader_from_list(self, item):
        shader_name = item.text()
        shader_path = FRAGS_DIR / shader_name

        try:
            with open(shader_path, "r", encoding="utf-8") as f:
                shader_code = f.read()

            self.text_edit.setPlainText(shader_code)
            self.apply_shader()
            self.tab_widget.setCurrentIndex(0)

            print(f"✅ Shader carregado: {shader_name}")

        except Exception as e:
            print(f"❌ Erro ao carregar shader {shader_name}: {e}")


    def save_shader_as(self):
        FRAGS_DIR.mkdir(parents=True, exist_ok=True)

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar Shader Como",
            str(FRAGS_DIR),
            "Fragment Shader (*.frag);;All Files (*)"
        )




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
        

        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Escolher Pasta para Exportar Frames",
            ""
        )
        
        if not output_dir:
            return
        
 
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
            
            
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ShaderEditor()
    w.showMaximized()
    app.setStyleSheet(qdarktheme.load_stylesheet())
    w.show()
    sys.exit(app.exec())

