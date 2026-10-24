OrbitDrop 0.30.0 · Daten- und Admin-Werkzeuge

- Prüfen & Bearbeiten für JSON, YAML, TOML, XML und JSONL, auch bei kaputter Syntax. Zeile/Spalte, markierte Fehlerzeile, Ausschnitt und Sprung zur Fehlerstelle.
- Einfache JSON-Korrekturvorschläge mit Vorher-/Nachher-Vorschau: fehlende Kommas/Doppelpunkte/Klammern und überflüssiges letztes Komma. Keine automatische Übernahme und kein Erraten von Werten. Doppelte Schlüssel werden gemeldet.
- Baumansicht, Suche, Pfad/Wert kopieren, formatieren, JSON kompakt und Schlüssel sortieren. Speichern als neue Datei; Originale bleiben erhalten.
- Passende Konvertierungen zwischen JSON/YAML/TOML/XML/CSV/TSV/JSONL mit Vorschau bei einzelnen Dateien. XML verwendet eine explizite Knotenstruktur; unpassende Umwandlungen werden abgewiesen.
- Textwerkzeuge: Zeichenkodierungen, Windows-/Linux-Zeilenumbrüche, Suchen/Ersetzen, Zeilennummern, Sortieren und Duplikate.
- CSV/TSV: Trennzeichen, Kodierung, Spaltenauswahl, Sortieren, Duplikate und JSON-Export ohne LibreOffice.
- Logs/JSONL: Streaming-Text-/ISO-Zeitfilter, letzte Zeilen, Vorschau und Export.
- SHA-256 für Dateien sowie Vergleich von zwei Text-/Binärdateien.
- X.509-Zertifikatsanzeige für PEM/CRT/CER/DER/PFX/P12: Details, SANs, Ablaufdatum und Fingerabdruck; Export öffentlicher Zertifikate als PEM/DER. Private Schlüssel werden nicht exportiert. Keine Vertrauens-/Sperrlistenprüfung.
- Alles lokal, neue Menüpunkte ausblendbar. Radialoptik und bestehende Medienfunktionen bleiben erhalten.

Syntaxprüfung ohne JSON-Schema/XSD. Editor maximal 8 MiB, 64 Ebenen/100000 Werte; Logs vollständig filtern bis 512 MiB oder letzte Zeilen aus 4 MiB. Kommentare und Schreibweisen können sich bei Formatwechseln ändern; Vorschau prüfen. YAML-Anker/Aliase/Sondertags und XML-DTDs/Entities werden nicht umgewandelt.

Windows-Paket enthält alle neuen Abhängigkeiten. Keine separate Python- oder OpenSSL-Installation nötig.
