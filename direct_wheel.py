"""Action labels and hints shared by the native octagon menu and settings."""
NAMES={'TEXT ERKENNEN':'Text erkennen','AUDIO VERBESSERN':'Audio verbessern','UPDATES':'Updates','AKTIONSSUCHE':'Aktion suchen','BILDABLÄUFE':'Bildabläufe','PDF SEITEN':'PDF-Seiten','UMBENENNEN':'Umbenennen','KOMPRIMIEREN':'Komprimieren','MARKIEREN':'Schwärzen &\nBeschriften','SCHNELLAKTIONEN':'Schnellaktionen','BILD EDITOR':'Bild bearbeiten','ZURÜCK':'Zurück','ZUSCHNEIDEN':'Zuschneiden','SCHWARZWEISS':'Schwarz\nweiß','GRÖSSE':'Bildgröße','90° LINKS':'90° links','90° RECHTS':'90° rechts','BITMAP':'Bitmap','SVG SCHNELL':'SVG\nSchnell','SVG ERWEITERT':'SVG\nErweitert','PDF VERBINDEN':'PDFs\nverbinden','PDF TEILEN':'PDF\nteilen','LINK LADEN':'Link\neinfügen','EINSTELLUNGEN':'Einstellungen','STANDBILD':'Standbild','AUFTRÄGE':'Aufträge','DEBUGGING':'Debugging','HILFE':'Anleitung &\nInfo','KONVERTER':'Konverter','VERSCHIEBEN':'Verschieben','KOPIEREN':'Kopieren','TERMINAL':'Terminal','EXPLORER':'Explorer','ABLAGE':'Ablage','ENTPACKEN':'Entpacken','SCHNEIDEN':'Schneiden','PFAD':'Pfad','ZIP':'ZIP','AUDIO LADEN':'Audio\nladen','VIDEO LADEN':'Video\nladen'}

def geometry(w):
    from octagon_menu import geometry as octagon_geometry
    return octagon_geometry(w)


def paint_direct(w):
    from octagon_menu import paint
    paint(w)


def action_hint(key):
    category,label=key.split(':',1)
    hints={'KOMPRIMIEREN':'Qualität, Bildgröße und maximale Dateigröße einstellen','MARKIEREN':'Schwärzungen, Pfeile, Text und Rahmen in ein Bild einzeichnen','SCHNELLAKTIONEN':'Eigene Rezepte und Startvorlagen verwalten','ZURÜCK':'Zum vorherigen Menü · die Datei bleibt ausgewählt','BILD EDITOR':'Farben, Ausschnitt, Drehung und Bildgröße mit Vorschau','ZUSCHNEIDEN':'Ausschnitt im Bild wählen und als neue Datei speichern','BITMAP':'Schwarzweiß-Bitmap mit Vorschau und Schwellwertregler','SVG SCHNELL':'Automatisch vorbereiten und in echte Vektorpfade umwandeln','SVG ERWEITERT':'Konturen, Farben und Glättung mit Vorschau einstellen','SCHWARZWEISS':'Graustufen oder zwei Farben mit Vorschau','SCHNEIDEN':'Abspielen, Schnittmarken setzen und Abschnitte entfernen','KOPIEREN':'Dateien in die Zwischenablage kopieren','VERSCHIEBEN':'Zielordner wählen und Originale dorthin verschieben','TERMINAL':'Terminal im enthaltenden Ordner öffnen','ABLAGE':'Dateien in der schwebenden Ablage parken','ENTPACKEN':'Archiv in einen neuen Unterordner entpacken','EINSTELLUNGEN':'Formate ausblenden und OrbitDrop anpassen'}
    if label in hints:return hints[label]
    if category=='format':return 'Neue Kopie als '+label+' speichern'
    if category=='download':return 'Download-Einstellungen und Speicherort wählen'
    return NAMES.get(label,label).replace('\n',' ')
