# Drittanbieter in OrbitDrop

Der Paketbau sammelt die von den installierten Python-Distributionen gelieferten LICENSE-, COPYING-, COPYRIGHT- und NOTICE-Dateien unter `third-party` im Programmpaket. `packages.txt` und `build-packages.txt` dokumentieren Versionen. FFmpeg-Lizenzdateien liegen neben den Medienprogrammen unter `bin`, die OCR-Datenlizenz unter `tessdata`.

Wichtige Projekte und Originalquellen:

- Python: https://www.python.org/ — Python Software Foundation License.
- PySide6/Qt: https://doc.qt.io/qtforpython-6/licenses.html — LGPLv3/GPLv3 bzw. kommerzielle Lizenz; Qt-Komponenten haben eigene Bedingungen.
- PyMuPDF/MuPDF: https://pymupdf.io/licensing — AGPLv3 bzw. kommerzielle Lizenz.
- FFmpeg: https://www.ffmpeg.org/legal.html — Bedingungen hängen von der konkreten Buildkonfiguration ab; verwendetes Windows-Paket von https://www.gyan.dev/ffmpeg/builds/ . GPL-Komponenten sind möglich.
- Tesseract-Sprachdaten: https://github.com/tesseract-ocr/tessdata_fast — Apache 2.0. Verwendeter Datenstand ist in `ocr_data.py` festgehalten.
- PyInstaller: https://pyinstaller.org/ — GPL mit Ausnahme für erzeugte Anwendungspakete.
- Weitere Python-Pakete: Lizenztexte und Paketmetadaten im Verzeichnis `third-party`.

Diese Sammlung vergibt keine zusätzliche Lizenz für den OrbitDrop-eigenen Code. Vor einer öffentlichen Binärveröffentlichung muss eine zu den verwendeten Abhängigkeiten passende Projektlizenz festgelegt und die vollständige Weitergabe der nötigen Quellen und Hinweise sichergestellt werden. Der automatische Release-Upload bleibt bis dahin ausgeschaltet.
