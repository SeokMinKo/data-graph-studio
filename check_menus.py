"""Check all menu items and their connections"""
from data_graph_studio.ui.main_window import MainWindow
from PySide6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
win = MainWindow()

print('=== DGS Menu Structure Check ===\n')

for action in win.menuBar().actions():
    menu = action.menu()
    if menu:
        menu_name = action.text().replace('&', '')
        print(f'[{menu_name}]')
        
        for sub_action in menu.actions():
            if sub_action.isSeparator():
                print('  ─────────')
            elif sub_action.menu():
                sub_name = sub_action.text().replace('&', '')
                print(f'  {sub_name} >')
                for sub_sub in sub_action.menu().actions():
                    name = sub_sub.text().replace('&', '')
                    shortcut = sub_sub.shortcut().toString() if sub_sub.shortcut() else ''
                    sc_str = f' ({shortcut})' if shortcut else ''
                    check = ' [v]' if sub_sub.isCheckable() else ''
                    print(f'    - {name}{sc_str}{check}')
            else:
                name = sub_action.text().replace('&', '')
                shortcut = sub_action.shortcut().toString() if sub_action.shortcut() else ''
                sc_str = f' ({shortcut})' if shortcut else ''
                check = ' [v]' if sub_action.isCheckable() else ''
                print(f'  - {name}{sc_str}{check}')
        print()

app.quit()
