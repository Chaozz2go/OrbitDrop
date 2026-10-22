"""A release history that remains available while update checks are offline."""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QTextBrowser, QSplitter, QLabel
from editor_chrome import heading, EDITOR_STYLE, action_button
from app_version import VERSION
from changelog import local_entries, notes_for


class ChangelogDialog(QDialog):
    def __init__(self, parent=None, previous=None):
        super().__init__(parent)
        self.setWindowTitle('OrbitDrop · Änderungsverlauf'); self.setStyleSheet(EDITOR_STYLE); self.resize(950, 680)
        self.records = local_entries()
        layout = QVBoxLayout(self)
        subtitle = 'Installierte Version: ' + VERSION + ' · lokal gespeichert'
        if previous:
            subtitle = 'Aktualisiert von ' + previous + ' auf ' + VERSION
        heading(layout, 'Neuerungen & Änderungsverlauf', subtitle)
        self.query = QLineEdit(); self.query.setPlaceholderText('Version oder Änderung suchen …'); layout.addWidget(self.query)
        split = QSplitter(); layout.addWidget(split, 1)
        self.versions = QListWidget(); self.text = QTextBrowser(); self.text.setOpenExternalLinks(False)
        split.addWidget(self.versions); split.addWidget(self.text); split.setSizes([230, 650])
        self.versions.addItems([record['title'] for record in self.records])
        self.versions.currentRowChanged.connect(self.show_record); self.query.textChanged.connect(self.filter)
        if self.records:
            row = next((i for i, record in enumerate(self.records) if record['version'] == VERSION), 0)
            self.versions.setCurrentRow(row)
        else:
            self.text.setPlainText('Der lokale Änderungsverlauf fehlt. Die installierte App bleibt nutzbar.')
        row = QHBoxLayout(); layout.addLayout(row)
        label = QLabel('Auch ohne Internet lesbar. Wähle links eine Version, um ihre Änderungen zu sehen.'); label.setWordWrap(True); row.addWidget(label, 1)
        close = action_button('Schließen'); close.clicked.connect(self.accept); row.addWidget(close)

    def show_record(self, row):
        if row < 0:
            return
        record = self.records[row]
        self.text.setMarkdown('## ' + record['title'] + '\n\n' + record['body'])

    def filter(self, query):
        terms = query.casefold().split(); shown = []
        for i, record in enumerate(self.records):
            match = all(term in (record['title'] + ' ' + record['body']).casefold() for term in terms)
            self.versions.item(i).setHidden(not match)
            if match:
                shown.append(i)
        if not shown:
            self.versions.setCurrentRow(-1); self.text.setPlainText('Keine passenden Änderungen gefunden.')
        elif self.versions.currentRow() not in shown:
            self.versions.setCurrentRow(shown[0])
