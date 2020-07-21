from PySide2.QtCore import QTimer
from PySide2.QtGui import QFont
from PySide2.QtWidgets import QApplication, QMainWindow, QWidget, QAction, QToolBar, QLabel, QTreeWidget, \
    QTreeWidgetItem, QDockWidget, QMenu, QTextEdit, QSpinBox, QDialog, QFormLayout, QVBoxLayout, QGroupBox, QCheckBox, \
    QHBoxLayout, QSizePolicy
from version import format_version
from descriptors import *
from elements import *
from schematic import SchematicEditor
from simulator import Simulator, BURST_SIZE
from time import perf_counter
from serial import save, load


class MCircuit(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setMinimumSize(1280, 720)
        self.setWindowTitle(self._make_title())

        self._simulator = Simulator()
        ng = NotGate(1)
        ng.name = 'gate'
        c = Composite()
        c.add_child(ng)
        c.name = 'root'
        c.connect('gate', 'out', 'gate', 'in')
        self._simulator.set_root(c)

        self._ticks = 0

        self._debug_editor = None
        self._debug_dock = None

        self._simulation_editor = None
        self._simulation_dock = None
        self._desired_frequency_spinbox = None

        self._schematic_editor = SchematicEditor(self._simulator)
        el = NotElement(ng)
        self._schematic_editor.add_element(el)
        self.setCentralWidget(self._schematic_editor)

        self._simulation_timer = QTimer()
        self._benchmark_timer = QTimer()

        self._simulate_action = QAction('Simulate')
        self._simulate_action.toggled.connect(self._on_simulate_action)
        self._simulate_action.setCheckable(True)

        self._setup_simulation_view()
        self._setup_file_menu()
        self._setup_debug_view()
        self._setup_view_menu()
        self._setup_toolbar()

        self._simulation_timer.timeout.connect(self._on_simulation_tick)
        self._benchmark_timer.timeout.connect(self._on_benchmark_tick)

    def _setup_toolbar(self):
        toolbar = QToolBar()

        toolbar.addAction(self._simulate_action)

        self.addToolBar(toolbar)

    def _make_title(self):
        return f'mcircuit {format_version()}'

    def _on_simulation_tick(self):
        freq = self._desired_frequency_spinbox.value() // 60
        n = freq // BURST_SIZE
        for _ in range(n):
            self._simulator.burst()
        rem = freq % BURST_SIZE
        for _ in range(rem):
            self._simulator.step()
        self._ticks += n * BURST_SIZE + rem
        self._schematic_editor.update()

    def _on_benchmark_tick(self):
        self._benchmark_label.setText(f'{self._ticks} Hz')
        self._ticks = 0

    def _setup_simulation_view(self):
        editor = QWidget()
        editor.setMinimumWidth(200)
        layout = QFormLayout(editor)
        self._desired_frequency_spinbox = QSpinBox()
        self._desired_frequency_spinbox.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._desired_frequency_spinbox.setMinimum(60)
        self._desired_frequency_spinbox.setMaximum(1000000000)
        self._benchmark_label = QLabel('0 Hz')
        layout.addRow('Target frequency:', self._desired_frequency_spinbox)
        layout.addRow('Frequency:', self._benchmark_label)
        self._simulation_editor = editor

        dock = QDockWidget()
        dock.setWidget(editor)
        dock.setWindowTitle('Simulation')
        self._simulation_dock = dock

        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _setup_debug_view(self):
        editor = QTextEdit()
        editor.setMinimumWidth(400)
        editor.setReadOnly(True)
        self._debug_editor = editor

        dock = QDockWidget()
        dock.setWidget(editor)
        dock.setWindowTitle('Debug')
        dock.setVisible(False)
        self._debug_dock = dock

        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _setup_view_menu(self):
        menu = QMenu('View')

        menu.addAction(self._debug_dock.toggleViewAction())
        menu.addAction(self._simulation_dock.toggleViewAction())

        self.menuBar().addMenu(menu)

    def _setup_file_menu(self):
        menu = QMenu('File')
        menu.addAction('Open')
        menu.addSeparator()
        menu.addAction('Save')
        menu.addAction('Save as...')
        menu.addSeparator()
        menu.addAction('Settings', self._on_settings_action)
        menu.addSeparator()
        menu.addAction('Exit', self.close)

        self.menuBar().addMenu(menu)

    def _on_settings_action(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Settings')
        dialog.setMinimumSize(320, 160)

        main_layout = QVBoxLayout()
        dialog.setLayout(main_layout)

        group_visual = QGroupBox('Visual')
        group_rendering = QGroupBox('Rendering')
        main_layout.addWidget(group_visual)
        main_layout.addWidget(group_rendering)

        def generic_setter(obj, prop):
            def f(value):
                setattr(obj, prop, value)
            return f

        visual_layout = QHBoxLayout()
        group_visual.setLayout(visual_layout)
        show_grid_checkbox = QCheckBox('Show grid')
        show_grid_checkbox.setChecked(self._schematic_editor.grid_shown)
        show_grid_checkbox.stateChanged.connect(
            generic_setter(self._schematic_editor, 'grid_shown'))
        visual_layout.addWidget(show_grid_checkbox)

        rendering_layout = QHBoxLayout()
        group_rendering.setLayout(rendering_layout)
        antialias_checkbox = QCheckBox('Antialiasing')
        antialias_checkbox.setChecked(self._schematic_editor.antialiased)
        antialias_checkbox.stateChanged.connect(
            generic_setter(self._schematic_editor, 'antialiased'))
        rendering_layout.addWidget(antialias_checkbox)

        dialog.show()

    def _on_simulate_action(self):
        simulating = self._simulate_action.isChecked()
        simulator = self._simulator
        if simulating:
            simulator.init()
            self._on_simulation_tick()
            self._debug_editor.setText('-' * 30)
            self._debug_editor.append('LLVM model translation')
            self._debug_editor.append('-' * 30)
            self._debug_editor.append(
                '<pre>{}</pre>'.format(simulator.get_debug_info()))
            self._simulation_timer.start(1000 // 60)
            self._benchmark_timer.start(1000)
        else:
            self._benchmark_label.setText('0 Hz')
            simulator.cleanup()
            self._simulation_timer.stop()
            self._benchmark_timer.stop()
            self._ticks = 0
        # TODO: We can allow changing frequencies at runtime, but not needed for now.
        self._desired_frequency_spinbox.setEnabled(not simulating)


if __name__ == "__main__":
    app = QApplication()
    instance = MCircuit()

    """ elems = ElementTree()
    elems.create_from_dict(ELEMENTS)
    elems.expandAll()
    dw = QDockWidget()
    dw.setWidget(elems)
    dw.setWindowTitle('Elements')
    dw.setFeatures(QDockWidget.DockWidgetMovable |
                   QDockWidget.DockWidgetFloatable)
    w.addDockWidget(Qt.LeftDockWidgetArea, dw) """

    """ sim = Simulator()
    g = NotGate(1)
    g.name = 'gate'
    sim.root = g
    t = QTimer(w)

    ed =
    ed.elements.append(NotElement(g)) """

    instance.show()
    app.exec_()
