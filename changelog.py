"""Installed release history: read local data only, including in frozen builds."""
from pathlib import Path
import re
import sys


def resource_path(name):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / name


def entries(text):
    headings = list(re.finditer(r'^## (.+)$', text, re.MULTILINE))
    result = []
    for i, match in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        title = match[1].strip()
        version = re.match(r'(\d+\.\d+\.\d+)(?:\s|$)', title)
        result.append({'title': title, 'version': version[1] if version else None,
                       'body': text[match.end():end].strip()})
    return result


def local_entries():
    try:
        return entries(resource_path('CHANGELOG.md').read_text(encoding='utf-8'))
    except OSError:
        return []


def notes_for(version, records=None):
    for record in local_entries() if records is None else records:
        if record['version'] == version:
            return '## ' + record['title'] + '\n\n' + record['body'] + '\n'
    return 'Für Version ' + version + ' ist kein lokaler Änderungseintrag vorhanden.'
