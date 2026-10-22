OrbitDrop 0.22.3

## 0.22.3 – 22.10.2026

### Behoben
- Bereichstasten während des Ziehens werden zusätzlich über Windows-Eingabeereignisse in einem eigenen Hintergrundthread erkannt. Kurze Tastendrücke bleiben auch nach dem Loslassen bis zur nächsten Menüabfrage erhalten.
- Bereits gehaltene Bereichstasten öffnen beim Beginn einer neuen Mausgeste ebenfalls das Menü. Die Reihenfolge von Taste und Maustaste führt dadurch nicht mehr zu einem verlorenen Aufruf.
- Desktop-Unterfenster des Explorers werden berücksichtigt. Fehlgeschlagene Fensterabfragen sperren die Erkennung nicht mehr für ein Viertel einer Sekunde.
- Ein kurzes Ausbleiben des Vordergrundfensters lässt einen passenden Aufruf erneut prüfen und schließt einen sichtbaren Kreis nicht sofort. Bei einem erkannten fremden Fenster oder Spiel gilt die Sperre weiterhin sofort.

### Technisches
- Windows Raw Input wird ohne Tastatursperre oder Hooks verwendet. Nur die belegten Tasten und abgeleitete Bereichsereignisse bleiben kurz im Speicher; keine Texteingaben, Dateien oder Tastaturprotokolle werden gespeichert.
- Veraltete Ereignisse, gewechselte Fenster, losgelassene Maustaste, Pause und modale Dialoge dürfen keinen verspäteten Kreis öffnen.
- Die bisherige Abfrage bleibt als Rückfall erhalten. Windows-Pakete testen die Registrierung und das Beenden des Eingabefensters auch in EXE und installierter App.
