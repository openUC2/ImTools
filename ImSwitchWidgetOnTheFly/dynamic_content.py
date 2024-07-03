
from PyQt5.QtWidgets import QLabel, QLineEdit

# Create and add widgets dynamically
label = QLabel("Enter your name:", parent_layout.parentWidget())
line_edit = QLineEdit(parent_layout.parentWidget())
parent_layout.addWidget(label)
parent_layout.addWidget(line_edit)
