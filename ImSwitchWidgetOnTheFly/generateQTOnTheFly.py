import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QFileDialog, QTabWidget, QVBoxLayout
from PyQt5.uic import loadUiType

class DynamicTabLoader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        
    def initUI(self):
        self.setWindowTitle("Dynamic Tab Loader")
        
        # Create central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Create a layout for the central widget
        self.layout = QVBoxLayout(self.central_widget)
        
        # Create QTabWidget
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        # Create Tab 1 with a button
        self.tab1 = QWidget()
        self.tab1_layout = QVBoxLayout(self.tab1)
        self.load_button = QPushButton("Load Python File", self.tab1)
        self.load_button.clicked.connect(self.load_python_file)
        self.tab1_layout.addWidget(self.load_button)
        self.tabs.addTab(self.tab1, "Tab 1")
        
        # Create Tab 2 which will be dynamically populated
        self.tab2 = QWidget()
        self.tab2_layout = QVBoxLayout(self.tab2)
        self.tabs.addTab(self.tab2, "Tab 2")
        
    def load_python_file(self):
        # Open file dialog to select a Python file
        file_dialog = QFileDialog()
        python_file, _ = file_dialog.getOpenFileName(self, "Open Python File", "", "Python Files (*.py)")
        
        if python_file:
            # Execute the Python file and add its widgets to Tab 2
            self.execute_python_file(python_file)
    
    def execute_python_file(self, file_path):
        # Clear the existing layout
        for i in reversed(range(self.tab2_layout.count())): 
            widget = self.tab2_layout.itemAt(i).widget()
            if widget is not None: 
                widget.setParent(None)
        
        # Create a local scope dictionary to execute the file
        local_scope = {"parent_layout": self.tab2_layout}
        with open(file_path, "r") as file:
            exec(file.read(), {}, local_scope)

# Sample dynamic Python file content (for testing purposes)
sample_python_file_content = """
from PyQt5.QtWidgets import QLabel, QLineEdit

# Create and add widgets dynamically
label = QLabel("Enter your name:", parent_layout.parentWidget())
line_edit = QLineEdit(parent_layout.parentWidget())
parent_layout.addWidget(label)
parent_layout.addWidget(line_edit)
"""

if __name__ == '__main__':
    app = QApplication(sys.argv)
    mainWin = DynamicTabLoader()
    mainWin.show()
    
    # Write the sample Python file content to a temporary file for testing
    with open("dynamic_content.py", "w") as file:
        file.write(sample_python_file_content)
    
    sys.exit(app.exec_())

