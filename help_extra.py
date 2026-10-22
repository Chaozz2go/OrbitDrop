"""Practical handbook sections shared by the in-app and standalone help."""
import html


def extra_sections(values):
    convert, edit, tools = (html.escape(values[name]) for name in ('convert_key', 'edit_key', 'files_key'))
    return [
        ('Beispiele Schritt für Schritt', f'''<h2>Ein Video kürzen und einen Teil entfernen</h2>
<ol><li>Video im Explorer ziehen, <b>{edit}</b> antippen und auf <b>Schneiden</b> ablegen.</li>
<li>Mit der Leertaste abspielen. Am Beginn des unerwünschten Teils pausieren und mit den Pfeiltasten frameweise die genaue Stelle finden.</li>
<li><b>C</b> drücken, zum Ende des Teils gehen und erneut <b>C</b> drücken.</li>
<li>Den Abschnitt zwischen beiden Marken anklicken und <b>Entf</b> drücken. Nur dieser Abschnitt wird ausgeschlossen.</li>
<li>Vorschau prüfen und exportieren. Die Ausgabe verbindet die behaltenen Bereiche; die Quelldatei bleibt erhalten.</li></ol>
<h2>Ein Foto zuschneiden und kleiner speichern</h2>
<ol><li>Foto ziehen → <b>{edit} → Bild bearbeiten</b>.</li><li>Ausschnitt mit der Maus wählen, bei Bedarf das Seitenverhältnis und die Ausgabegröße setzen.</li>
<li>Vorschau bzw. Originalvergleich prüfen und eine neue Datei exportieren.</li><li>Für ein bestimmtes Größenlimit die exportierte Datei ziehen → <b>{edit} → Komprimieren</b>. Ergebnisgröße in der Vorschau prüfen.</li></ol>
<h2>Aus einem Motiv eine Schwarzweiß-SVG machen</h2>
<ol><li>Bild ziehen → <b>{convert} → SVG Erweitert</b>.</li><li>Vorbereitung und Schwellwert so einstellen, dass wichtige Konturen erhalten bleiben. Glättung und Details in der Vorschau abstimmen.</li>
<li>Als SVG exportieren. Für ein einfaches Motiv kann <b>SVG Schnell</b> die Vorbereitung automatisch übernehmen.</li></ol>
<h2>Text aus einem eingescannten Schreiben kopieren</h2>
<ol><li>Bild oder PDF ziehen → <b>{edit} → Text erkennen</b>.</li><li>Deutsch, Englisch oder beide wählen. Fehlende Sprachdaten einmalig einrichten.</li>
<li>Text erkennen, Erkennungsfehler korrigieren und Text kopieren oder als TXT speichern.</li><li>Optional eine neue durchsuchbare Scan-PDF erzeugen. Die Seiten werden dabei neu gerendert; das Original behalten.</li></ol>
<h2>Mehrere Dateien einheitlich benennen</h2>
<ol><li>Dateien gemeinsam ziehen → <b>{tools} → Umbenennen</b>.</li><li><code>Urlaub_{{n}}</code>, Startnummer und Ziffernzahl einstellen.</li>
<li>Vorher-/Nachher-Liste prüfen und ausführen. Hier ändern sich die Originalnamen.</li><li>Falls nötig vor dem Schließen des Fensters <b>Letzte Umbenennung zurücknehmen</b> wählen.</li></ol>
<h2>Nur bestimmte Songs einer Playlist laden</h2>
<ol><li>Playlist-Link über <b>{tools} → Link einfügen</b> öffnen und Audio wählen.</li><li>Link prüfen, <b>Keine auswählen</b> wählen und nur gewünschte Titel anhaken.</li>
<li>Speicherordner prüfen und starten. Die Suche blendet Titel nur aus; markierte ausgeblendete Titel werden ebenfalls geladen.</li></ol>'''),
        ('Alle Formate & Grenzen', '''<h2>Welche Dateien kann ich umwandeln?</h2>
<p>Der Kreis zeigt die für die konkrete Auswahl und die installierten Konverter passenden Ziele. Die folgende Übersicht ist keine Zusage, dass jede Kombination möglich ist.</p>
<table border="1" cellpadding="7" cellspacing="0">
<tr><th>Bereich</th><th>Formate und Möglichkeiten</th></tr>
<tr><td>Bilder</td><td>JPG, PNG, WebP, HEIC, AVIF, TIFF, BMP sowie PDF-Ausgabe. Rasterbilder als SVG vektorisieren. Einzelbilder; keine Animationen oder mehrseitigen Bilder in der normalen Bildkonvertierung.</td></tr>
<tr><td>SVG</td><td>Als Bild/PDF rastern. Keine Skripte, eingebetteten Bilder oder externen Referenzen in der SVG-Eingabe.</td></tr>
<tr><td>Audio</td><td>MP3, M4A, WAV, FLAC, OGG, Opus, AIFF und WMA. Konkrete Ausgaben abhängig von verfügbaren FFmpeg-Encodern.</td></tr>
<tr><td>Video</td><td>MP4, MOV, MKV, WebM, AVI, WMV und GIF. Audioexport nur mit echter Tonspur; erstes Standbild als eigene Aktion. GIF-Ausgabe ohne Ton.</td></tr>
<tr><td>PDF</td><td>JPG/PNG als ZIP mit Seitenbildern; DOCX als extrahierter Text; PPTX als Seitenbilder; XLSX aus erkennbaren Tabellen; TXT, Markdown und EPUB aus Text.</td></tr>
<tr><td>Dokumente</td><td>DOCX, Markdown, TXT, EPUB; je nach Konverter RTF, DOC und HTML als Eingaben. PDF-Ausgabe über LibreOffice, bestimmte Text-/E-Book-Richtungen über Pandoc.</td></tr>
<tr><td>Präsentationen</td><td>PPT/PPTX → PDF bzw. JPG/PNG-Seitenbilder als ZIP. PPT nur Eingabe.</td></tr>
<tr><td>Tabellen</td><td>XLSX, ODS, CSV und TSV untereinander sowie PDF-Ausgabe; XLS nur Eingabe. CSV/TSV enthalten ein Blatt und bewahren keine Office-Formatierungen/Formeln.</td></tr>
<tr><td>Untertitel</td><td>SRT ↔ VTT sowie TXT ohne Zeitmarken. Erweiterte VTT-Stile und Positionierungen werden nicht vollständig übernommen.</td></tr>
<tr><td>Archive</td><td>ZIP, TAR und GZIP; RAR nur als Eingabe mit externem Decoder. GZIP-Ausgabe ist TAR.GZ. Keine Passwortarchive und kein 7z.</td></tr>
</table>
<h2>Was passiert mit meinen Originalen?</h2><p>Normale Konvertierungen und Bearbeitungen erzeugen neue Dateien. Vorhandene Namen bekommen Nummernzusätze. <b>Verschieben und Umbenennen ändern dagegen die Originale.</b> Die Ablage enthält nur Verweise. Abbruch räumt je nach Werkzeug unfertige Ausgaben auf; fertige Konvertierungen können erhalten bleiben. Bei einer Fehlermeldung die Auftragsdetails prüfen.</p>
<h2>Die Ausgabe sieht anders aus</h2><p>JPG unterstützt keine Transparenz. Audio-/Video-Neuencodierung kann Qualität kosten. PDF→DOCX rekonstruiert kein identisches Layout. Eine Scan-PDF rendert Seiten neu und übernimmt keine Formulare oder interaktiven Elemente. HDR, Farbräume, besondere Metadaten und Archiv-/NTFS-Rechte werden nicht originalgetreu garantiert.</p>
<h2>Datei erkannt, aber Aktion fehlt</h2><p>Konverter unter Tools prüfen. Mehrere ausgewählte Dateien brauchen ein gemeinsames Ziel. Ausgeblendete Menüpunkte erscheinen auch in der Aktionssuche nicht. Experimenteller Pages-Import hängt von LibreOffice und Dateiversion ab; kein Pages-Export. RTFD und Text Clippings werden nicht unterstützt.</p>'''),
    ]
