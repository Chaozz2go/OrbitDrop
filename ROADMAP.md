# OrbitDrop: Ausbau für Windows

Stand 0.20.0. Eigenständige Oberfläche und Implementierung, inspiriert vom schnellen Drag-and-drop-Konzept. Die folgende Liste beschreibt geplante Arbeit, keine bereits zugesicherten Funktionen.

## Erledigt in diesem Schritt

- Frei belegbare unterstützte Tasten/Kombinationen, gemeinsame Menü-Sichtbarkeit und durchsuchbares lokales Handbuch mit aktueller Belegung.

- Shift → Konvertieren, Strg → Bearbeiten, Alt → Tools; alle passenden Optionen im Kreis; abgerundete Flächen, Symbole, Hinweise und mehrere Ringe bei langen Listen.
- Ein Bildeditor mit Ausschnitt, Drehung, Farbkorrektur, Originalvergleich und Ausgabegröße.
- Aktionssuche mit kontextabhängigen Aktionen, Favoriten und Dateiauswahl; im Kreis per Rechtsklick erreichbar.
- Stapel-Umbenennen mit Vorschau, Konfliktprüfung und Rücknahme im offenen Fenster.
- Gespeicherte Bildabläufe mit geordneten Schritten und neuer Ausgabe. Audio-/Videoabläufe bleiben offen.
- Komprimieren mit aktueller Größe, Zielgrößenregler, technischer Audio-/Video-Prüfung und verlustfreier PDF-Probe.
- Windows-x64-Setup und portables Paket mit gebündelter Laufzeit, FFmpeg/FFprobe und OCR-Sprachdaten; native Windows-Tests für EXE und Installation.
- Optionale tägliche Updateprüfung und geprüfte Setup-Downloads; öffentliche Releases stehen bis zur Projektlizenz noch aus.
- Lokale OCR für Bilder/PDFs und Audio-Werkzeuge für Lautheit, Randstille und Fades.
- Gemeinsamer Schnittstudio-Stil für alle Programmfenster, inklusive Bild-/Video-/Audiobearbeitung, Hilfsfenster und Dateiablage.

## Als Nächstes: Bildwerkzeuge

- Erledigt: manuelle Schwärzungen, Text, Pfeile, Rahmen, Verschieben und Rückgängig/Wiederholen. Noch offen: automatische Gesichts-/Texterkennung und weitere Formen.
- Noch offen: Unschärfe-/Mosaikbereiche; sichere deckende Schwärzungen sind vorhanden.
- Neue Leinwand mit Hintergrund, Rand, Schatten und abgerundeten Bildecken; anschließend Collagen und Mehrbild-PDF.
- Erledigt: Bild-/Video-/Audio-/PDF-Komprimierung mit überprüftem Größenlimit; unerreichbare Ziele werden gemeldet. Bildvorschau und benannte Komprimierungsrezepte sind vorhanden.
- Metadaten ansehen/bearbeiten/entfernen mit ExifTool; beschreibbare Felder je Dateityp prüfen.

## Danach: Video und Audio

- Vorhandenen Schnitteditor weiterverwenden; keine zweite Schnittimplementierung für Downloads.
- Video-Ausschnitt, Tempo mit Tonhöhenkorrektur, Stummschalten, gezielte PNG-Standbilder und Zusammenfügen.
- Video-Schwärzungsbereiche mit Zeitspannen und tatsächlicher Exportvorschau.
- Erledigt: echte Wellenformen in Video- und Audioschnitt, gemeinsame Abschnittsauswahl, Entf zum Entfernen und Wiederherstellen. Erledigt: Timeline-Zoom, gemeinsames Scrollen und Schnitt-Rückgängig/Wiederholen. Erledigt: Lautheitsnormalisierung im Dialog Audio verbessern. Noch offen: mehrere Tonspuren, Kanalbearbeitung, Pieptonbereiche und Visualisierung als Video.

## Danach: PDF und Windows-Integration

- Erledigt: visuelle Seitenverwaltung mit Verschieben, Drehen, Duplizieren, Entfernen und neuer PDF-Ausgabe.
- Erledigt: lokale OCR für Bilder und gescannte PDFs. Weiter offen: Office-Exportqualität verbessern.
- Windows-Teilen statt AirDrop; nicht als identisches Apple-Protokoll darstellen.
- Explorer-Drag-and-drop, Mehrfachauswahl, mehrere Monitore und unterschiedliche DPI auf Windows testen.
- Tastatursteuerung für den Kreis ergänzen; globale Tasten dürfen normale Explorer-Bedienung nicht stören.
- Erledigt: EXE/Installer mit gebündelter Laufzeit, FFmpeg und OCR; Windows-Baufolge prüft das portable Programm und eine echte Installation. Weitere manuelle Explorer-/DPI-/Monitor-Tests bleiben offen.

## Plattformgrenzen

Apple-Pages-Export gehört zunächst nicht zum Zielumfang. Vorhandene Importmöglichkeiten sind von der Datei und LibreOffice abhängig. Offline-Verarbeitung gilt für Konvertierungen und Editoren; Downloads benötigen naturgemäß Internet. Ein Dateityp darf nur Aktionen anbieten, deren Backend verfügbar und für diese Auswahl geeignet ist.
