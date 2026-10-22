# OrbitDrop · Änderungsverlauf

## 0.22.1 – 22.10.2026

### Behoben
- Die LibreOffice-Versionsprüfung nutzt unter Windows das Konsolenprogramm im Hintergrund, statt den GUI-Starter mit Versionsausgabe zu öffnen. Fehlt der Konsolenstarter, wird die Versionsabfrage übersprungen.
- Auch Office-Konvertierungen bevorzugen unter Windows den für Hintergrundaufrufe vorgesehenen Starter.

### Verbessert
- Fehlende optionale Dokumentkonverter lösen beim Start keine wiederkehrende Meldung mehr aus.
- „Konverter prüfen / einrichten“ erklärt die verfügbaren Funktionen und wofür LibreOffice und Pandoc benötigt werden. Technische Pfade, Versionen und Fehler stehen unter Details.
- Wenn Medienwerkzeuge fehlen oder nicht starten, nennt der Hinweis die betroffenen Funktionen und den Weg zur Einrichtung.

## 0.22.0 – 22.10.2026

### Neu
- Radiales Menü aus gleich großen, regelmäßigen Oktagonen für Startansicht, Konvertieren, Bearbeiten, Tools und Links.
- Kompakter innerer Ring mit festen Plätzen für häufige Aktionen. „Weitere“ erweitert das Menü nach außen; „Weniger“ klappt es wieder ein.
- Beim Ziehen öffnet kurzes Verweilen auf „Weitere“ den äußeren Ring. Ein anschließendes Ablegen darauf klappt ihn nicht versehentlich wieder ein.
- Bei sehr vielen Aktionen blättert nur der äußere Ring; die inneren Aktionen bleiben an ihrem Platz.
- Option „Mit erweitertem Oktagon-Menü starten“ in den Einstellungen.

### Verbessert
- Favoriten können einen inneren Platz erhalten; ausgeblendete Aktionen bleiben ausgeblendet.
- Bildschirmränder und Monitore mit negativen Koordinaten werden berücksichtigt. Bei wenig Platz öffnet „Weitere“ die Aktionssuche statt unlesbar kleiner zusätzlicher Kacheln.
- Neue Programmaufnahme und aktualisierte Offline-Anleitung zum Oktagon-Menü.

## 0.21.0 – 22.10.2026

### Neu
- Dauerhafter, durchsuchbarer Änderungsverlauf direkt im Updatefenster und in „Anleitung & Info“; auch ohne Internet lesbar.
- Nach einem Versionswechsel werden die Neuerungen einmal angezeigt. Übersprungene Versionen bleiben im Verlauf nachlesbar.
- Eigenständiges Offline-Handbuch mit Inhaltsverzeichnis, Suche, konkreten Beispielen, Formatübersicht und Bildern. Direkt aus der Hilfe öffnen oder als HTML-Datei speichern.
- Mehr praktische Hilfe zu Konvertierung, Bildbearbeitung, Schnitt, PDF/OCR, Downloads, Dateiaktionen und Fehlern.

### Verbessert
- Direkt per Bereichstaste oder Tray geöffnetes Konvertieren/Bearbeiten/Tools hat keinen unnötigen Zurück-Eintrag. Die Bereichstasten wechseln weiterhin zwischen diesen Hauptbereichen.
- Zurück erscheint erst nach einer tatsächlichen Menünavigation, etwa nach der manuellen Bereichsauswahl. Die aktuelle Dateiauswahl bleibt erhalten.
- Das Updatefenster zeigt bei fehlendem Internet weiterhin die lokalen Neuerungen. Es installiert weiterhin erst nach deiner Bestätigung.
- Reine Änderungen an README, Dokumentation oder Bildern lösen keinen Windows-Paketbau aus.
- Ein bereits veröffentlichtes Paket wird bei einem erneuten Workflow-Lauf unverändert beibehalten.

## 0.20.0 – 22.10.2026

### Neu
- Updateprüfung bei jedem Programmstart auf veröffentlichte stabile Releases in Chaozz2go/OrbitDrop; in Einstellungen und Updates abschaltbar.
- Spielschutz: Automatische Datei-Tastenzugänge gelten nur für Explorer, Desktop, OrbitDrop und unterstützte Dateimanager.
- Tray-Schalter „Tastenzugänge pausieren“, beispielsweise für Browser-Spiele.

### Verbessert
- Markierte Links werden aus unterstützten Browsern außerhalb des Vollbilds übernommen. Ein verspätetes Ergebnis öffnet nach einem Fensterwechsel keinen Kreis.
- Esc und der Pausenhinweis funktionieren auch bei pausierten Tastenzugängen.
- README mit Funktionsanleitung und Aufnahme des Kreismenüs.

## 0.19.0 – 21.10.2026

### Neu
- Frei belegbare Bereichstasten und unterstützte Tastenkombinationen mit Aufnahmefeld.
- Durchsuchbare Einstellungen zum Ausblenden einzelner Menüpunkte und ganzer Gruppen.
- Lokale, durchsuchbare Anleitung mit deiner aktuellen Tastenbelegung.
- AGPL-v3-Lizenz für den OrbitDrop-eigenen Code.

### Verbessert
- Ausgeblendete Favoriten erscheinen auch in der Aktionssuche nicht wieder.
- Wiederherstellung aller Menüpunkte bleibt über die Tray-Einstellungen erreichbar.
- Aufnahme von Umschalt-Ziffern und Nummernblocktasten unter Windows.

## 0.18.0 – 21.10.2026

### Neu
- YouTube-Playlists vor dem Download einlesen und alle oder einzelne Titel auswählen.
- Suche, Titeldauer und Verfügbarkeitsanzeige in der Playlist-Auswahl.

### Verbessert
- Gewählte Titel werden nacheinander geladen; ein Einzelfehler stoppt die übrigen nicht.
- Fertige Downloads bleiben beim Abbrechen erhalten.

## 0.17.1 – 21.10.2026

### Behoben
- Rechteckiger nativer Windows-Rahmen um das transparente Kreismenü entfernt.

## 0.17.0 – 21.10.2026

### Neu
- Windows-Setup und portables Paket ohne separat installierte Python-Laufzeit.
- FFmpeg/FFprobe sowie deutsche und englische OCR-Daten im Windows-Paket.
- Updateprüfung und Download mit SHA-256-Prüfung.
- Lokale Texterkennung für Bilder/PDFs und Export einer durchsuchbaren Scan-PDF.
- Audio-Lautheit normalisieren, Randstille entfernen und Fades setzen.

## Frühere Prototypen bis 0.16

- Radiales Konvertieren-/Bearbeiten-/Tools-Menü mit Dateiinhaltserkennung.
- Bildeditor, Zuschnitt, Drehung, Schwarzweiß/Bitmap und SVG-Vektorisierung.
- Video-/Audioschnitt mit Filmstreifen, Wellenformen, Abschnittslöschung, Zoom und Rückgängig.
- Komprimierung mit Größenanzeige, Zielgröße und Vorprüfung.
- Downloads über yt-dlp, gespeicherter Downloadordner und Auftragsverlauf.
- PDF-Seitenverwaltung, Stapel-Umbenennen und eigene Bildabläufe.
- Aktionssuche, Favoriten, Schnellaktionen, ZIP/Entpacken, Ablage und Datei-Tools.
