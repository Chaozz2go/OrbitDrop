# Drittanbieter in OrbitDrop

Der Paketbau sammelt die von den installierten Python-Distributionen gelieferten LICENSE-, COPYING-, COPYRIGHT- und NOTICE-Dateien unter `third-party` im Programmpaket. `packages.txt` und `build-packages.txt` dokumentieren Versionen. FFmpeg-Lizenzdateien liegen neben den Medienprogrammen unter `bin`, die OCR-Datenlizenz unter `tessdata`.

Wichtige Projekte und Originalquellen:

- Python: https://www.python.org/ — Python Software Foundation License.
- PySide6/Qt: https://doc.qt.io/qtforpython-6/licenses.html — LGPLv3/GPLv3 bzw. kommerzielle Lizenz; Qt-Komponenten haben eigene Bedingungen.
- PyMuPDF/MuPDF: https://pymupdf.io/licensing — AGPLv3 bzw. kommerzielle Lizenz.
- FFmpeg: https://www.ffmpeg.org/legal.html — Bedingungen hängen von der konkreten Buildkonfiguration ab; verwendetes Windows-Paket von https://www.gyan.dev/ffmpeg/builds/ . GPL-Komponenten sind möglich.
- Tesseract-Sprachdaten: https://github.com/tesseract-ocr/tessdata_fast — Apache 2.0. Verwendeter Datenstand ist in `ocr_data.py` festgehalten.
- PyInstaller: https://pyinstaller.org/ — GPL mit Ausnahme für erzeugte Anwendungspakete.
- pyzipper: https://github.com/danifus/pyzipper — MIT; AES-ZIP über PyCryptodome/PyCryptodomex (BSD/Public Domain, mit eigenen Drittanbieterhinweisen).
- Optionales 7-Zip: https://www.7-zip.org/ — nicht im OrbitDrop-Paket enthalten; Installation aus offizieller winget-Quelle nur auf Anforderung.
- ruamel.yaml: https://yaml.dev/ — MIT; sichere YAML-Verarbeitung ohne Objektkonstruktion aus eigenen Tags.
- simplejson: https://github.com/simplejson/simplejson — MIT/Academic Free License; JSON mit Dezimalzahlen.
- Tomli-W/Tomli: https://github.com/hukkin/tomli-w und https://github.com/hukkin/tomli — MIT.
- cryptography: https://cryptography.io/ — Apache 2.0/BSD; eingebettete Kryptobibliotheken mit eigenen Lizenzhinweisen.
- Weitere Python-Pakete: Lizenztexte und Paketmetadaten im Verzeichnis `third-party`.

Der OrbitDrop-eigene Code steht unter GNU AGPL Version 3 (AGPL-3.0-only), siehe die Datei LICENSE im Paket/Repository. Diese Lizenz ersetzt keine Bedingungen der einzelnen Abhängigkeiten. Vor einer öffentlichen Binärveröffentlichung muss die vollständige Weitergabe der jeweils nötigen Quellen und Hinweise geprüft sein. Automatisch erzeugte Binärpakete bleiben zunächst unveröffentlichte Release-Entwürfe.
