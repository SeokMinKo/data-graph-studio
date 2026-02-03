import sys, os
sys.path.insert(0, '.')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from data_graph_studio.ui.main_window import MainWindow

app = QApplication(sys.argv)
print("QApp created", flush=True)
win = MainWindow()
print(f"MainWindow created", flush=True)
win.show()
win.raise_()
win.activateWindow()
print(f"Window shown: visible={win.isVisible()}, size={win.width()}x{win.height()}", flush=True)

def load_data():
    print("Loading data...", flush=True)
    win._load_file('/tmp/test_data.csv')
    print("Load called", flush=True)

def take_screenshot():
    print("Taking screenshot...", flush=True)
    win.grab().save('/tmp/dgs_ui_test.png')
    os.system('screencapture -x /tmp/dgs_ui_screencap.png')
    print("Screenshots saved", flush=True)

QTimer.singleShot(2000, load_data)
QTimer.singleShot(7000, take_screenshot)
app.exec()
