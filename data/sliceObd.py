import sys
import io
from PIL import Image

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSpinBox, QCheckBox, QSlider, QFileDialog, QListWidget,
    QListWidgetItem, QFrame, QGridLayout, QMessageBox,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsObject,
    QGroupBox, QAbstractItemView, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QSize
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QIcon

# ============================================================================
# Widget da Grade Interativa (Draggable Grid)
# ============================================================================
class GridOverlay(QGraphicsObject):
    """
    Representa a grade (SurfaceCells) que fica sobre a imagem.
    Pode ser arrastada pelo mouse.
    """
    positionChanged = pyqtSignal(int, int)  # Emite sinal quando arrastado

    def __init__(self, cell_size=32, rows=1, cols=1, subdivisions=False):
        super().__init__()
        self.cell_size = cell_size
        self.rows = rows
        self.cols = cols
        self.subdivisions = subdivisions
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(10) # Fica acima da imagem

    def boundingRect(self):
        width = self.cols * self.cell_size
        height = self.rows * self.cell_size
        return QRectF(0, 0, width, height)

    def paint(self, painter, option, widget):
        width = self.cols * self.cell_size
        height = self.rows * self.cell_size

        # Desenha a borda da grade (Branco com contraste)
        pen = QPen(QColor(255, 255, 255), 1, Qt.PenStyle.SolidLine)
        pen.setCosmetic(True) # Mantém espessura 1px independente do zoom
        painter.setPen(pen)
        painter.drawRect(0, 0, width, height)

        # Desenha as células internas
        if self.subdivisions or (self.rows > 1 or self.cols > 1):
            # Linhas verticais
            for c in range(1, self.cols):
                x = c * self.cell_size
                painter.drawLine(x, 0, x, height)
            
            # Linhas horizontais
            for r in range(1, self.rows):
                y = r * self.cell_size
                painter.drawLine(0, y, width, y)

        # Highlight semi-transparente para indicar a área de seleção
        painter.fillRect(0, 0, width, height, QColor(255, 255, 255, 30))

    def itemChange(self, change, value):
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionChange:
            # Emite a nova posição para atualizar os SpinBoxes
            new_pos = value
            self.positionChanged.emit(int(new_pos.x()), int(new_pos.y()))
        return super().itemChange(change, value)

    def update_grid(self, rows, cols, subdivisions):
        self.rows = rows
        self.cols = cols
        self.subdivisions = subdivisions
        self.prepareGeometryChange()
        self.update()

# ============================================================================
# Janela Principal do Slicer
# ============================================================================
class SliceWindow(QWidget):
    # Sinal emitido quando o usuário clica em "Import". Envia lista de PIL Images.
    sprites_imported = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Slicer")
        self.resize(900, 600)
        self.setStyleSheet("background-color: #494949; color: white;")
        
        self.current_image_pil = None # Imagem original carregada (PIL)
        self.sliced_images = []       # Lista de sprites cortadas
        self.cell_size = 32

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Toolbar ---
        toolbar = QFrame()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet("background-color: #333; border-bottom: 1px solid #222;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(10, 5, 10, 5)

        btn_open = QPushButton("Open Image")
        btn_open.setStyleSheet("background-color: #555; padding: 5px;")
        btn_open.clicked.connect(self.open_image)
        tb_layout.addWidget(btn_open)
        
        tb_layout.addStretch()

        btn_rot_r = QPushButton("Rot 90°")
        btn_rot_r.clicked.connect(lambda: self.transform_image("rotate_90"))
        tb_layout.addWidget(btn_rot_r)

        btn_flip_h = QPushButton("Flip H")
        btn_flip_h.clicked.connect(lambda: self.transform_image("flip_h"))
        tb_layout.addWidget(btn_flip_h)

        main_layout.addWidget(toolbar)

        # --- Área Central (Painéis) ---
        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)

        # 1. Painel Esquerdo (Controles)
        left_panel = QFrame()
        left_panel.setFixedWidth(200)
        left_panel.setStyleSheet("QFrame { background-color: #444; border-right: 1px solid #222; } QLabel { color: #ddd; }")
        lp_layout = QVBoxLayout(left_panel)
        
        # Grupo: Cells
        grp_cells = QGroupBox("Cells")
        grp_cells_layout = QGridLayout()
        
        self.chk_subdivisions = QCheckBox("Subdivisions")
        self.chk_subdivisions.toggled.connect(self.update_grid_visuals)
        grp_cells_layout.addWidget(self.chk_subdivisions, 0, 0, 1, 2)

        self.chk_empty = QCheckBox("Empty Sprites")
        self.chk_empty.setToolTip("Se marcado, salva sprites mesmo se forem transparentes")
        grp_cells_layout.addWidget(self.chk_empty, 1, 0, 1, 2)

        # Spinboxes X, Y
        grp_cells_layout.addWidget(QLabel("X:"), 2, 0)
        self.spin_x = QSpinBox()
        self.spin_x.setRange(0, 9999)
        self.spin_x.valueChanged.connect(self.on_spinbox_change)
        grp_cells_layout.addWidget(self.spin_x, 2, 1)

        grp_cells_layout.addWidget(QLabel("Y:"), 3, 0)
        self.spin_y = QSpinBox()
        self.spin_y.setRange(0, 9999)
        self.spin_y.valueChanged.connect(self.on_spinbox_change)
        grp_cells_layout.addWidget(self.spin_y, 3, 1)

        # Spinboxes Cols, Rows
        grp_cells_layout.addWidget(QLabel("Cols:"), 4, 0)
        self.spin_cols = QSpinBox()
        self.spin_cols.setRange(1, 100)
        self.spin_cols.setValue(1)
        self.spin_cols.valueChanged.connect(self.update_grid_visuals)
        grp_cells_layout.addWidget(self.spin_cols, 4, 1)

        grp_cells_layout.addWidget(QLabel("Rows:"), 5, 0)
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(1, 100)
        self.spin_rows.setValue(1)
        self.spin_rows.valueChanged.connect(self.update_grid_visuals)
        grp_cells_layout.addWidget(self.spin_rows, 5, 1)

        grp_cells.setLayout(grp_cells_layout)
        lp_layout.addWidget(grp_cells)

        # Grupo: Zoom
        grp_zoom = QGroupBox("Zoom")
        zoom_layout = QVBoxLayout()
        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom.setRange(10, 500) # 10% a 500%
        self.slider_zoom.setValue(100)
        self.slider_zoom.valueChanged.connect(self.on_zoom_change)
        zoom_layout.addWidget(self.slider_zoom)
        self.lbl_zoom_val = QLabel("100%")
        self.lbl_zoom_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_layout.addWidget(self.lbl_zoom_val)
        grp_zoom.setLayout(zoom_layout)
        lp_layout.addWidget(grp_zoom)

        # Botão Cut
        self.btn_cut = QPushButton("CUT IMAGE")
        self.btn_cut.setFixedHeight(40)
        self.btn_cut.setStyleSheet("background-color: #007acc; font-weight: bold; color: white;")
        self.btn_cut.clicked.connect(self.cut_image)
        lp_layout.addWidget(self.btn_cut)

        lp_layout.addStretch()
        content_layout.addWidget(left_panel)

        # 2. Painel Central (Canvas)
        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QColor(50, 50, 50))
        
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setStyleSheet("border: none;")
        content_layout.addWidget(self.view, 1)

        # Itens da cena
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        self.grid_item = GridOverlay()
        self.grid_item.positionChanged.connect(self.on_grid_moved_by_mouse)
        self.scene.addItem(self.grid_item)

        # 3. Painel Direito (Lista de Sprites)
        right_panel = QFrame()
        right_panel.setFixedWidth(160)
        right_panel.setStyleSheet("background-color: #444; border-left: 1px solid #222;")
        rp_layout = QVBoxLayout(right_panel)

        rp_layout.addWidget(QLabel("Sprites:"))
        self.list_widget = QListWidget()
        self.list_widget.setIconSize(self.list_widget.size()) 
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.setStyleSheet("QListWidget { background-color: #333; } QListWidget::item:selected { background-color: #007acc; }")
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setIconSize(QSize(32, 32))
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        rp_layout.addWidget(self.list_widget)

        self.btn_import = QPushButton("Import")
        self.btn_import.setFixedHeight(30)
        self.btn_import.setStyleSheet("background-color: #28a745; color: white; font-weight: bold;")
        self.btn_import.clicked.connect(self.import_sprites)
        self.btn_import.setEnabled(False)
        rp_layout.addWidget(self.btn_import)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.clear_list)
        rp_layout.addWidget(btn_clear)

        content_layout.addWidget(right_panel)

    # ------------------------------------------------------------------------
    # Lógica (Todas as funções estão corretamente indentadas dentro da classe)
    # ------------------------------------------------------------------------
    
    def update_grid_visuals(self):
        """Atualiza o visual da grade quando os inputs mudam."""
        rows = self.spin_rows.value()
        cols = self.spin_cols.value()
        subs = self.chk_subdivisions.isChecked()
        self.grid_item.update_grid(rows, cols, subs)

    def open_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.bmp *.jpg)")
        if file_path:
            try:
                self.current_image_pil = Image.open(file_path).convert("RGBA")
                self.update_canvas_image()
                # Reseta a grid para 0,0
                self.grid_item.setPos(0, 0)
                self.spin_x.setValue(0)
                self.spin_y.setValue(0)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def update_canvas_image(self):
        if self.current_image_pil:
            qim = self.pil_to_qimage(self.current_image_pil)
            pix = QPixmap.fromImage(qim)
            self.pixmap_item.setPixmap(pix)
            self.scene.setSceneRect(QRectF(pix.rect()))
            
            # Ajusta limites dos spinboxes
            w, h = self.current_image_pil.size
            self.spin_x.setRange(0, w)
            self.spin_y.setRange(0, h)

    def transform_image(self, mode):
        if not self.current_image_pil: return
        
        if mode == "rotate_90":
            self.current_image_pil = self.current_image_pil.rotate(-90, expand=True)
        elif mode == "flip_h":
            self.current_image_pil = self.current_image_pil.transpose(Image.FLIP_LEFT_RIGHT)
        
        self.update_canvas_image()

    def on_grid_moved_by_mouse(self, x, y):
        # Atualiza spinboxes sem disparar loop de sinal
        self.spin_x.blockSignals(True)
        self.spin_y.blockSignals(True)
        self.spin_x.setValue(x)
        self.spin_y.setValue(y)
        self.spin_x.blockSignals(False)
        self.spin_y.blockSignals(False)

    def on_spinbox_change(self):
        x = self.spin_x.value()
        y = self.spin_y.value()
        self.grid_item.setPos(x, y)

    def on_zoom_change(self, value):
        scale = value / 100.0
        self.lbl_zoom_val.setText(f"{value}%")
        self.view.resetTransform()
        self.view.scale(scale, scale)

    def cut_image(self):
        if not self.current_image_pil:
            return

        start_x = self.spin_x.value()
        start_y = self.spin_y.value()
        cols = self.spin_cols.value()
        rows = self.spin_rows.value()
        size = self.cell_size

        for c in range(cols):
            for r in range(rows):
                x = start_x + (c * size)
                y = start_y + (r * size)
                
                # Verifica limites da imagem
                if x + size > self.current_image_pil.width or y + size > self.current_image_pil.height:
                    continue

                # Crop
                box = (x, y, x + size, y + size)
                sprite = self.current_image_pil.crop(box)
                
                # Verifica se está vazia (transparente)
                if not self.chk_empty.isChecked():
                    if not sprite.getbbox(): 
                         continue

                self.add_sprite_to_list(sprite)

        if self.list_widget.count() > 0:
            self.btn_import.setEnabled(True)

    def add_sprite_to_list(self, pil_image):
        self.sliced_images.append(pil_image)
        
        # Converte para ícone
        qim = self.pil_to_qimage(pil_image)
        pix = QPixmap.fromImage(qim)
        
        icon = QIcon(pix)
        item = QListWidgetItem(icon, "")
        item.setSizeHint(QSize(40, 40)) 
        self.list_widget.addItem(item)
        self.list_widget.scrollToBottom()

    def clear_list(self):
        self.sliced_images.clear()
        self.list_widget.clear()
        self.btn_import.setEnabled(False)

    def import_sprites(self):
        if not self.sliced_images:
            return
        
        reply = QMessageBox.question(
            self, "Import", 
            f"Import {len(self.sliced_images)} sprites to the editor?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.sprites_imported.emit(self.sliced_images)
            self.close()

    @staticmethod
    def pil_to_qimage(pil_image):
        if pil_image.mode != "RGBA":
            pil_image = pil_image.convert("RGBA")
        data = pil_image.tobytes("raw", "RGBA")
        qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)
        return qimage

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SliceWindow()
    window.show()
    sys.exit(app.exec())
