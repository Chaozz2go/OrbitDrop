OrbitDrop 0.28.0 · Schnellere Vorschauen und verständliche Ladeanzeigen

- Der Bildeditor öffnet vor dem Laden großer Bilder. Laden, Ausrichtung und Vorschauaufbereitung laufen im Hintergrund; Schließen bricht den Vorgang ab. Währenddessen bleiben noch nicht verfügbare Bearbeitungen gesperrt.
- Bild, Video und Audio zeigen die aktuelle Ladephase. Prozentwerte erscheinen nur bei messbarem Fortschritt: Videoleiste mit Anzahl fertiger Bilder, Audio anhand der verarbeiteten Spur. Das Öffnen und Vorbereiten zeigt einen unbestimmten Ladebalken.
- Der Videoeditor verwendet einen Decoder weiter. Aufeinanderfolgende Vorwärtsschritte nutzen bereits dekodierte Bildfolgen; echte Zeitstempel bleiben die Grundlage, auch bei variabler Bildrate. Große Videoframes werden vor der RGB-Vorschau verkleinert.
- Die Videoleiste verwendet einen gemeinsamen Decoder statt die Datei für jedes Bild neu zu öffnen. Konvertierte Vorschaubilder werden beim Zeichnen wiederverwendet; beim Zoomen entstehen keine übergroßen Zwischenbilder.
- Videoleisten und Audiowellenformen bleiben in einem auf 32 MiB begrenzten Sitzungscache. Pfad, Dateigröße, Änderungszeit und Vorschauparameter bestimmen die Gültigkeit. Geänderte Dateien werden neu berechnet; Originalbilder und vollständige Videos werden nicht im Cache gehalten.
- Separate begrenzte Vorschau-Worker verhindern, dass Vorschauen hinter der Export-Warteschlange warten. Update-Installation berücksichtigt auch aktive Vorschauarbeiten.
- Anleitung, Einstellungen und Update-Seite im Dashboard werden erst beim ersten Zugriff aufgebaut und danach wiederverwendet.
- Das Radialmenü behält Optik, Positionierung und Eingabeverhalten. Keine Änderung an der Exportqualität.
