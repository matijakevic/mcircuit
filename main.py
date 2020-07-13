from PySide2.QtCore import QTimer
from PySide2.QtGui import QFont
from PySide2.QtWidgets import QApplication, QMainWindow, QWidget, QAction, QToolBar, QLabel, QTreeWidget, \
    QTreeWidgetItem, QDockWidget, QMenu, QTextEdit, QSpinBox
from version import format_version
from descriptors import *
from elements import *
from time import perf_counter
from serial import save, load


class MCircuit(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setMinimumSize(640, 480)
        self.setWindowTitle(self._make_title())

        self._simulator = Simulator()
        ng = NotGate(1)
        ng.name = 'gate'
        el = NotElement(ng)
        self._simulator.set_root(ng)

        self._desired_frequency = 1
        self._ticks = 0

        self._debug_editor = None
        self._debug_dock = None

        self._schematic_editor = SchematicEditor()
        self._schematic_editor.elements.append(el)
        self.setCentralWidget(self._schematic_editor)

        self._simulation_timer = QTimer()
        self._benchmark_timer = QTimer()

        self._simulate_action = QAction('Simulate')
        self._simulate_action.toggled.connect(self._on_simulate_action)
        self._simulate_action.setCheckable(True)

        self._benchmark_label = QLabel()

        self._setup_file_menu()
        self._setup_debug_view()
        self._setup_view_menu()
        self._setup_toolbar()

        self._simulation_timer.timeout.connect(self._on_simulation_tick)
        self._benchmark_timer.timeout.connect(self._on_benchmark_tick)

    def _setup_toolbar(self):
        toolbar = QToolBar()

        toolbar.addAction(self._simulate_action)
        toolbar.addSeparator()
        toolbar.addWidget(self._benchmark_label)

        self.addToolBar(toolbar)

    def _make_title(self):
        return f'mcircuit {format_version()}'

    def _on_simulation_tick(self):
        freq = self._desired_frequency
        if freq < 60:
            self._simulator.step()
            self._ticks += 1
        else:
            n = freq // BURST_SIZE
            for _ in range(n):
                self._simulator.burst()
            rem = freq % BURST_SIZE
            for _ in range(rem):
                self._simulator.step()
            self._ticks += n * BURST_SIZE + rem
        self._schematic_editor.update()

    def _on_benchmark_tick(self):
        self._benchmark_label.setText(f'Frequency: {self._ticks} Hz')
        self._ticks = 0

    def _setup_debug_view(self):
        editor = QTextEdit()
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

        self.menuBar().addMenu(menu)

    def _setup_file_menu(self):
        menu = QMenu('File')
        menu.addAction('Open')
        menu.addSeparator()
        menu.addAction('Save')
        menu.addAction('Save as...')
        menu.addSeparator()
        menu.addAction('Exit', self.close)

        self.menuBar().addMenu(menu)

    def _on_simulate_action(self):
        simulating = self._simulate_action.isChecked()
        simulator = self._simulator
        if simulating:
            simulator.init()
            self._debug_editor.setText(
                '<pre>{}</pre>'.format(simulator.get_debug_info()))
            if self._desired_frequency < 60:
                self._simulation_timer.start(1000 // self._desired_frequency)
            else:
                self._simulation_timer.start(1000 / 60)
            self._benchmark_timer.start(1000)
        else:
            self._benchmark_label.clear()
            simulator.cleanup()
            self._simulation_timer.stop()
            self._benchmark_timer.stop()


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
