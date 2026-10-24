# Audio verbessern · Ausbauvorschlag
Stand: 24. Oktober 2026. **Erste Etappe in Version 0.31.0 umgesetzt:** Profile (ohne Telefon-Effekt), einfacher und zehnbandiger EQ, Kompressor, De-Esser, kurze A/B-Vorschau und eigene Profile. Die übrigen Punkte bleiben Vorschläge für weitere Etappen.

## Bedienung
Ein Fenster mit Profilwahl, kurzer Erklärung, Stärke-Regler und Hörvorschau. Erweiterte Einstellungen bleiben aufklappbar. Effekte einzeln deaktivieren, zurücksetzen und eigene Profile speichern. Profile sind veränderbare Ausgangspunkte für die jeweilige Aufnahme.

Vorher/Nachher am selben gewählten Ausschnitt (z. B. 10–30 Sekunden), mit optional angeglichener Wiedergabelautstärke. Kurze Vorschauen im Hintergrund berechnen, alte Ergebnisse verwerfen und Analysen zwischenspeichern. Vollständiger Export als neue Datei. Die Lautheitsmessung des ganzen Programms kann von der kurzen Vorschau abweichen.

## Eigene vorgeschlagene Profile
| Profil | Zweck |
| --- | --- |
| Podcast · natürlich | Klarheit, wenig Rumpeln, sanfte Kompression, optionale S-Laut-Absenkung |
| Stimme · warm | Dezente Wärme, weichere Höhen, moderate Dynamik |
| Radio · Moderation | Präsenter und dichter, stärkere Kompression mit Spitzenreserve |
| Interview / Besprechung | Verständlichkeit, gleichmäßige Pegel, optionale dezente Rauschminderung |
| Hörbuch / Vorlesen | Natürlicher, wenig ermüdender Sprachklang |
| Musik · sanft | Breite Klangkorrekturen; Sprachfilter und Gate standardmäßig aus |
| Telefon / altes Radio · Effekt · später | Bewusst eingeschränktes Frequenzband als Kreativeffekt |

Radio-Klang und Rundfunk-Lautheit getrennt einstellen. Ein Lautheitswert alleine erzeugt keinen Moderationsklang. Keine pauschale Sender-/Plattformkonformität versprechen.

## Funktionen
- Equalizer: einfache Regler für Bass, Wärme, Klarheit und Höhen; erweitert zehn Bänder, dB-Anzeigen, Kurve und Flat-Reset.
- Hoch-/Tiefpass gegen Rumpeln bzw. unerwünschte Randbereiche.
- Kompressor für gleichmäßigere Sprache. Einfach Stärke, erweitert Threshold, Ratio, Attack/Release und weicher Übergang.
- De-Esser gegen störende S-/Sch-Laute, separat abschaltbar.
- Dezente klassische FFT-Rauschminderung, möglichst mit auswählbarer reiner Rauschstelle; entferntes Geräusch vorhörbar. Starke Bearbeitung kann hörbare Artefakte erzeugen; unregelmäßiger Verkehrslärm oder einzelne Schläge sind damit nicht zuverlässig entfernbar.
- Optionaler 50/60-Hz-Brummfilter samt Oberwellen.
- Optionaler sanfter Expander, um Pausen leiser zu machen, statt Wörter hart abzuschneiden. Standardmäßig aus.
- Lautheits- und Spitzenmessung, Normalisierung und True-Peak-Prüfung; diese Ausgabeziele unabhängig vom Klangprofil.
- Bewusste Kanalwahl: Mono/Stereo, links/rechts bei einseitigen Aufnahmen.
- Vorhandene Fades und Randstille-Entfernung mit Sicherheitsabstand behalten; interne Sprechpausen erhalten.
- WAV/FLAC/MP3 behalten, optional AAC/M4A; Samplerate, Kanäle und Bitrate wählbar.

## Lautheit
Apple empfiehlt etwa −16 LKFS (±1 dB) und begrenzten True Peak; EBU R 128 nennt −23 LUFS für Rundfunk. Diese Ziele dürfen nicht mit der Klangfarbe verwechselt werden. Ein oft genanntes separates Mono-Ziel von −19 LUFS steht nicht als eigene Vorgabe auf der hier geprüften Apple-Seite.

## Technik und Etappen
Auf dem enthaltenen FFmpeg aufbauen. Klassische Bausteine: equalizer, highpass, lowpass, bandreject, acompressor, deesser, afftdn, agate, loudnorm, alimiter und pan. Verfügbare Filter vor Nutzung im jeweiligen Build prüfen. Kein KI-Modell erforderlich.

Vorgeschlagene Kette: Randstille planen → Rumpeln/Brummen → dezente Rauschminderung → EQ → Kompressor → De-Esser → Lautheitsmessung/Normalisierung → Spitzenbegrenzung → Kodierung und Ergebnisprüfung. Einen Sample-Peak-Limiter nicht als alleinige True-Peak-Konformitätsprüfung behandeln.

Erste Etappe: Profile, EQ, Kompressor, De-Esser, A/B-Vorschau und eigene Profile. Zweite Etappe: Rausch-/Brummminderung, Expander, Kanäle und weitere Messanzeigen. Zusätzliche kreative Effekte erst bei Bedarf.

## Primärquellen
- https://ffmpeg.org/ffmpeg-filters.html
- https://www.audacityteam.org/manual/effects/eq-and-filters/
- https://www.audacityteam.org/manual/effects/volume-and-compression/compressor/
- https://www.audacityteam.org/manual/effects/noise-removal-and-repair/noise-reduction/
- https://podcasters.apple.com/support/893-audio-requirements
- https://tech.ebu.ch/publications/r128
