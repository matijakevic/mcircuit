from PySide2.QtCore import QTimer
from PySide2.QtGui import QFont
from PySide2.QtWidgets import QApplication, QMainWindow, QWidget, QAction, QToolBar, QLabel, QTreeWidget, \
    QTreeWidgetItem, QDockWidget, QMenu, QTextEdit, QSpinBox
from version import format_version
from descriptors import *
from elements import *
from time import perf_counter


def make_title():
    return f'mcircuit {format_version()}'


ELEMENTS = {

}


class ElementTree(QTreeWidget):
    def __init__(self):
        super().__init__()

        self.setHeaderHidden(True)
        self.setColumnCount(1)

    def create_from_dict(self, d):
        for category in d:
            category_item = QTreeWidgetItem()
            category_item.setText(0, category)

            for elem_name in d[category]:
                it = QTreeWidgetItem()
                it.setText(0, elem_name)
                category_item.addChild(it)

            self.addTopLevelItem(category_item)


if __name__ == "__main__":
    app = QApplication()
    w = QMainWindow()
    w.setMinimumSize(640, 480)
    w.resize(1280, 720)

    debug = QTextEdit()
    debug.setReadOnly(True)
    debug_dw = QDockWidget()
    debug_dw.setWidget(debug)
    debug_dw.setWindowTitle('Debug')
    debug_dw.setVisible(False)
    w.addDockWidget(Qt.RightDockWidgetArea, debug_dw)

    menu = w.menuBar()

    file_menu = QMenu('File')
    file_menu.addAction('Open')
    file_menu.addSeparator()
    file_menu.addAction('Save')
    file_menu.addAction('Save as...')
    file_menu.addSeparator()
    file_menu.addAction('Exit')

    menu.addMenu(file_menu)

    view_menu = QMenu('View')
    view_menu.addAction(debug_dw.toggleViewAction())
    menu.addMenu(view_menu)

    elems = ElementTree()
    elems.create_from_dict(ELEMENTS)
    elems.expandAll()
    dw = QDockWidget()
    dw.setWidget(elems)
    dw.setWindowTitle('Elements')
    dw.setFeatures(QDockWidget.DockWidgetMovable |
                   QDockWidget.DockWidgetFloatable)
    w.addDockWidget(Qt.LeftDockWidgetArea, dw)

    sim = Simulator()
    g = NotGate(1)
    g.name = 'gate'
    sim.root = g
    t = QTimer(w)

    ed = SchematicEditor()
    w.setCentralWidget(ed)
    for i in range(10):
        ed.elements.append(NotElement(g))

    edd = None

    ticks = 0
    desired_freq = 1

    def _on_timer():
        global ticks
        if desired_freq < 60:
            sim.step()
            ticks += 1
        else:
            n = desired_freq // BURST_SIZE
            for _ in range(n):
                sim.burst()
            rem = desired_freq % BURST_SIZE
            for _ in range(rem):
                sim.step()
            ticks += n * BURST_SIZE + rem
        ed.update()

    t.timeout.connect(_on_timer)

    action = QAction('Simulate')
    action.setCheckable(True)

    spb = QSpinBox()
    spb.setValue(1)
    spb.setMinimum(1)
    spb.setMaximum(1000000000)

    def on_change_val(val):
        global desired_freq
        desired_freq = val
        if desired_freq < 60:
            t.start(1000 // desired_freq)
        else:
            t.start(1000 / 60)
    spb.valueChanged.connect(on_change_val)

    def _handle_sim_action():
        simulating = action.isChecked()
        if simulating:
            sim.init()
            debug.setText('<pre>{}</pre>'.format(sim.get_debug_info()))
            if desired_freq < 60:
                t.start(1000 // desired_freq)
            else:
                t.start(1000 / 60)
            benc_timer.start(1000)
        else:
            lbl.setText('')
            sim.cleanup()
            t.stop()
            benc_timer.stop()

    action.changed.connect(_handle_sim_action)
    toolbar = QToolBar()

    lbl = QLabel()

    benc_timer = QTimer(w)

    def _on_bench():
        global ticks
        lbl.setText(f'Frequency: {ticks} Hz')
        ticks = 0

    benc_timer.timeout.connect(_on_bench)

    toolbar.addAction(action)
    toolbar.addWidget(spb)
    lbl.setAlignment(Qt.AlignRight)
    toolbar.addWidget(lbl)
    w.addToolBar(toolbar)

    w.setWindowTitle(make_title())
    w.show()
    app.exec_()
