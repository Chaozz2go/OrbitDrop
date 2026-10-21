# OrbitDrop: Ausbau für Windows

Stand 0.11.0. Eigenständige Oberfläche und Implementierung, inspiriert vom schnellen Drag-and-drop-Konzept. Die folgende Liste beschreibt geplante Arbeit, keine bereits zugesicherten Funktionen.

## Erledigt in diesem Schritt

- Bereichsauswahl → alle passenden Optionen im Kreis; abgerundete Flächen, Symbole, Hinweise und mehrere Ringe bei langen Listen.
- Ein Bildeditor mit Ausschnitt, Drehung, Farbkorrektur, Originalvergleich und Ausgabegröße.
- Gemeinsamer Stil für Bild-, Schwarzweiß-, Bitmap- und SVG-Dialoge.

## Als Nächstes: Bildwerkzeuge

- Beschriftungen: Text, Pfeile, Formen, Markierungen und Rückgängig.
- Manuelles Schwärzen/Unschärfe mit verschiebbaren Bereichen; automatische Gesichts-/Texterkennung separat prüfen.
- Neue Leinwand mit Hintergrund, Rand, Schatten und abgerundeten Bildecken; anschließend Collagen und Mehrbild-PDF.
- Komprimieren mit Qualitätsvorschau und optionalem Zielvolumen. Zielgrößen sind format- und inhaltsabhängig, daher nicht pauschal garantieren.
- Metadaten ansehen/bearbeiten/entfernen mit ExifTool; beschreibbare Felder je Dateityp prüfen.

## Danach: Video und Audio

- Vorhandenen Schnitteditor weiterverwenden; keine zweite Schnittimplementierung für Downloads.
- Video-Ausschnitt, Tempo mit Tonhöhenkorrektur, Stummschalten, gezielte PNG-Standbilder und Zusammenfügen.
- Schwärzungsbereiche mit Zeitspannen und tatsächlicher Exportvorschau.
- Audiowellenform, Lautheitsnormalisierung, Mono/Stereo, Pieptonbereiche und Visualisierung als Video.

## Danach: PDF und Windows-Integration

- Visuelle Seitenverwaltung: verschieben, drehen, duplizieren und entfernen.
- Lokale OCR für gescannte PDFs; Office-Exportqualität und Einschränkungen klar anzeigen.
- Windows-Teilen statt AirDrop; nicht als identisches Apple-Protokoll darstellen.
- Explorer-Drag-and-drop, Mehrfachauswahl, mehrere Monitore und unterschiedliche DPI auf Windows testen.
- Tastatursteuerung für den Kreis ergänzen; globale Tasten dürfen normale Explorer-Bedienung nicht stören.
- EXE/Installer mit gebündelter Laufzeit und geprüft verfügbaren Konvertern. Noch kein Windows-Build aus der Linux-Testumgebung.

## Plattformgrenzen

Apple-Pages-Export gehört zunächst nicht zum Zielumfang. Vorhandene Importmöglichkeiten sind von der Datei und LibreOffice abhängig. Offline-Verarbeitung gilt für Konvertierungen und Editoren; Downloads benötigen naturgemäß Internet. Ein Dateityp darf nur Aktionen anbieten, deren Backend verfügbar und für diese Auswahl geeignet ist.
