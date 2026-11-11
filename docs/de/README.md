# Anleitung für Ausbilder

*Deutsche Anleitung zu `bonsai-btk`. Stand: 0.3.0.*

## Worum es geht

Das Add-on ergänzt Bonsai um Werkzeuge für die Ausbildung zum Bautechnischen Konstrukteur. Dazu gehören Fangen wie im CAD, Maßketten und Höhenkoten nach DIN 1356, Schraffuren als echte Linien und ein Geländemodell aus amtlichen Geodaten. Modelliert wird weiter nativ in IFC. Das Add-on bringt Werkzeuge mit, kein zweites Datenmodell.

Die Oberfläche ist englisch, wie Bonsai selbst. Eine deutsche Sprachdatei kann folgen.

Projektvorlage und Zeichenstil liegen im Schwester-Repository [native-ifc-template](https://github.com/modelllogik/native-ifc-template).

## Abnahmekriterium dieser Anleitung

Sie ist gelungen, wenn Sie ein Werkzeug **ohne Rückfrage** im Unterricht einsetzen können.
Wenn das nicht klappt, ist die Anleitung unvollständig. Bitte melden Sie die Stelle als Issue, gern auf Deutsch.

## Vorher: Blender und Bonsai

Das Add-on läuft in Blender und setzt Bonsai voraus. Wer beides noch nicht kennt oder installiert hat, beginnt mit Abschnitt 0 der Anleitung zur Projektvorlage: [Vorbereitung: Blender und Bonsai](https://github.com/modelllogik/native-ifc-template/blob/main/docs/de/README.md#0--vorbereitung-blender-und-bonsai). Dort stehen Download, Installation, die Prüfung und die ersten Handgriffe in Blender.

## Installieren und aktualisieren

Das Add-on kommt aus einem eigenen Erweiterungs-Repository. Die Adresse trägt man einmal ein, danach installiert und aktualisiert Blender es wie jede andere Erweiterung.

1. *Edit → Preferences → System → Network:* **Allow Online Access** einschalten.
2. *Edit → Preferences → Get Extensions → Repositories* (oben rechts) → **+** → **Add Remote Repository**, mit dieser Adresse:

   ```
   https://github.com/modelllogik/bonsai-btk/releases/latest/download/index.json
   ```

   Wer möchte, setzt das Häkchen bei *Check for Updates on Startup*.
3. In *Get Extensions* nach **BTK Tools for Bonsai** suchen und *Install* drücken. Bonsai muss installiert und eingeschaltet sein.

**Aktualisieren:** Gibt es eine neue Fassung, zeigt *Get Extensions* einen Knopf *Update* (nach *Check for Updates* im Menü ⌄ oder beim Start). Die alte Fassung vorher **nicht** deinstallieren.

**Bisher über *Install from Disk* installiert?** Dann liegt die alte Fassung im Repository *User Default*. Sie dort einmal deinstallieren, **Blender neu starten** und dann wie oben aus dem neuen Repository installieren. Zwei Kopien derselben Erweiterung in zwei Repositorys kommen sich in die Quere.

**Ohne Internetzugang** (etwa in einem abgeschotteten Netz): die Zip aus dem [neuesten Release](https://github.com/modelllogik/bonsai-btk/releases/latest) laden und über *Get Extensions → ⌄ → Install from Disk…* installieren. Eine neuere Zip ins **selbe** Repository installieren und Blender neu starten. Auf neue Fassungen muss man dann selbst achten.

## Die Werkzeuge

Alle Werkzeuge liegen in der Seitenleiste des 3D-Fensters (Taste N), Reiter **BTK**: im Kasten *Dimensions* das Bemaßen, im Kasten *Drawing* Zeichnungen und Blätter, im Kasten *Site* das Gelände.

Die Zeichenwerkzeuge arbeiten in einer aktiven Zeichnung im IFC Object Mode.

### Maßkette: *Dimension from Points*

1. Knopf drücken. Die Maus springt ins 3D-Bild. Bauteilecken anklicken. Punkt 1 → Punkt 2 legt die Richtung fest, jeder weitere Punkt wird senkrecht auf die Maßlinie gelegt. *M* springt zur nächsten Ecke in der Nähe, die *Rücktaste* nimmt den letzten Punkt zurück.
2. *Enter*: Die Maus bestimmt Seite und Abstand im Raster 5 mm auf dem Blatt. Alternativ den Abstand in mm tippen. Außerhalb der Außenkante beginnt die erste Kette ab der Außenkante, jede weitere parallele Kette liegt 10 mm weiter außen.
3. *Klick* oder *Enter* legt die Kette als Bonsai-Bemaßung in der aktiven Zeichnung an. *Esc* bricht ab, es entsteht nichts.

Ändert sich der Maßstab der Zeichnung, rücken die so angelegten Ketten nach, damit ihr Abstand auf dem Blatt gleich bleibt.

### Schnittpunktfang: Taste *S*

Beim Punktefangen schaltet *S* auf den Schnittpunkt zweier Kanten um: erste Kante anklicken, zweite Kante anklicken. Übernommen wird der Schnittpunkt der beiden Geraden, auch über die Kantenenden hinaus. Während des Fangs zeigt das Bild die Spurlinien. So wird zum Beispiel der Traufpunkt bemaßt, an dem sich Außenkante Mauerwerk und Außenkante Dachaufbau schneiden. *Rücktaste* nimmt die erste Kante zurück, *S* schaltet ab.

### Maß umdrehen: *Flip Dimension*

Kehrt die Punktreihenfolge der gewählten Maßketten um, die Maßzahlen drehen sich mit. Nach DIN 1356 liest man waagerechte Ketten von links nach rechts und senkrechte von unten nach oben.

## Zeichnungen und Blätter: Kasten *Drawing*

Bonsai schreibt jede Zeichnung als SVG-Datei. Die Knöpfe im Kasten *Drawing* bearbeiten diese Datei nach DIN 1356-1 nach, bauen daraus Blätter und drucken sie. Voraussetzung ist der Zeichenstil aus [native-ifc-template](https://github.com/modelllogik/native-ifc-template), eingerichtet mit dessen `scripts/install_style.py`. Zum Ausprobieren eignet sich das Mustermodell dort (`examples/example_house.ifc`); es bringt 19 Zeichnungen und Blätter mit.

### *Update Drawing*

Erzeugt die aktive Zeichnung mit Bonsais *Create Drawing* und bearbeitet sie nach:
- Schraffuren als echte Linien statt SVG-Muster, auf die Schnittfläche beschnitten. So bleiben sie im PDF Vektoren. Dazu das Holzkreuz.
- Fugen gleichen Materials verschwinden, etwa zwischen zwei Mauerwerkswänden. Tragende Schichten liegen oben, damit ihr Umriss durchgeht.
- Schichtaufbauten erscheinen ab 1:100 als eine Fläche.
- Fenster und Türen in der schmalen Linie, das Glas als eine Linie.
- Treppen im Grundriss: Der Lauf bis zur Schnittlinie durchgezogen, darüber gestrichelt, Lauflinie mit Kreis und Pfeil, Steigungsangabe im Geschoss des Antritts.
- Dachumriss und First im Grundriss gepunktet.
- Brüstungshöhen (BRH) an den Fenstern im Grundriss.

Ein zweiter Lauf ändert nichts mehr.

### *Layers On/Off* und *Rotate*

Beide wirken auf die gewählten Bauteile und erneuern danach die Zeichnung:
- *Layers On/Off* zeichnet sie in jedem Maßstab mit Schichten oder als eine Fläche. Mit *Strg* zurück auf automatisch.
- *Rotate* dreht ihre Schraffur um 15°.

Beides steht als Eigenschaft in der IFC (`EPset_BTK_Hatching.Layers`, `EPset_BTK_Hatching.Rotation`) und bleibt damit erhalten.

### *Update Sheet* und *Print Sheet (PDF)*

*Update Sheet* nimmt das Blatt, das in Bonsais Blattliste gewählt ist:
1. Es erzeugt und bearbeitet jede Zeichnung darauf.
2. Es setzt eine Legende der geschnittenen Materialien links neben den Plankopf, auf Grundriss-Blättern zusätzlich den Nordpfeil. Jedes Kästchen zeigt das Material so, wie es gezeichnet ist: ein Stahlprofil schwarz, ein Blech nur umrandet. Kommt beides vor, ist das Kästchen schwarz.
3. Bonsai baut das Blatt.

Fehlt die Layout-Datei des Blatts, wie beim frisch geöffneten Mustermodell, legt Bonsai sie an, sobald die Zeichnungen erzeugt sind.

*Print Sheet (PDF)* speichert das gewählte Blatt als PDF, über [Inkscape](https://inkscape.org). Vorher wird das Blatt aktualisiert, das lässt sich im Dialog abwählen. Der Weg über Inkscape ist nötig, weil Browser Schraffuren beim Drucken in Pixel umwandeln. Inkscape muss installiert sein. Das Add-on sucht es selbst; findet es Inkscape nicht, trägt man den Pfad in den Einstellungen des Add-ons ein (*Edit → Preferences → Add-ons → BTK Tools for Bonsai*).

### Vorschau im Browser

*Preview Drawing* und *Preview Sheet* aktualisieren die Zeichnung bzw. das Blatt und zeigen es im Browser. Die Seite lädt sich nach jedem weiteren Update selbst neu.

Auf der Blattseite lassen sich Zeichnung, Titel, Legende und Nordpfeil verschieben:
- Ziehen am blauen Rahmen bewegt die Zeichnung samt Titel, Ziehen am Titelrahmen nur den Titel.
- Raster 5 mm, mit *Alt* frei; die Pfeiltasten verschieben um 5 mm, mit *Alt* um 1 mm.
- Zwei Hilfslinien (magenta) fangen an Kanten der Zeichnungen. Sie gibt es nur im Browser.
- Mausrad = Zoom, Doppelklick = ganzes Blatt.

*Apply* schreibt die neuen Lagen in die Layout-Datei des Blatts und baut es neu. Die vorige Fassung liegt danach in `layouts/_backup/`, je Blatt die letzten fünf. *Discard* verwirft die Änderungen. An der IFC ändert sich dabei nichts. *Print* öffnet eine Druckseite im Blattformat zum Ansehen, *PDF* das Blatt über Inkscape für den richtigen Druck.

Der Vorschau-Server ist nur auf dem eigenen Rechner erreichbar (127.0.0.1), Port 8765. Ist der Port belegt, stellt man in den Einstellungen des Add-ons einen anderen ein. *Stop Preview* (das Kreuz neben der Adresse) beendet den Server.

### Bekannte Einschränkung

Wände mit Schichtvorrang an ihren Anschlüssen kann IfcOpenShell 0.9 nicht neu berechnen ([#10054](https://github.com/IfcOpenShell/IfcOpenShell/issues/10054)). Das betrifft etwa die Außenwände des Mustermodells: Mauerwerk stumpf gestoßen, WDVS herumgeführt. Wer eine solche Wand in Bonsai verschiebt oder ändert, bekommt eine Fehlermeldung. Gezeichnet werden sie trotzdem richtig. Eine Korrektur ist vorgeschlagen ([PR #10071](https://github.com/IfcOpenShell/IfcOpenShell/pull/10071)); das Add-on umgeht den Fehler nicht.

## Gelände: Kasten *Site*

Die Gelände-Werkzeuge bauen die Umgebung eines Gebäudes aus amtlichen Geodaten auf, vom echten Gelände bis zum Pappmodell auf dem Tisch. Alles, was sie anlegen, hängt an einem Leerobjekt *BTK_Site_Origin*. Verschiebt man den Projektnullpunkt, wandert alles mit, ohne neu gerechnet zu werden.

**Daten.** Für Bayern gibt es Gelände (DGM1), Luftbilder (DOP), 3D-Gebäude (LoD2) und Einzelbäume kostenlos im OpenData-Portal [geodaten.bayern.de](https://geodaten.bayern.de) unter CC BY 4.0. Die Daten kommen in Kacheln von 1 km. Das Add-on liest je Ebene eine GeoTIFF-Datei, mehrere Kacheln setzt man vorher zusammen, etwa in QGIS mit dem GDAL-Werkzeug *Merge*. Andere Länder bieten ähnliche Daten an. Das Bezugssystem muss projiziert und metrisch sein, etwa ETRS89 / UTM.

### Aufbau des Kastens

Oben im Kasten *Site* schaltet man zwischen *Terrain* und *Cardboard Model* um, blendet Luftbild, Bäume und Wiese ein oder aus und wählt die Kamera; der Knopf daneben schaut durch sie hindurch. Darunter folgen sieben Schritte in der Reihenfolge, in der man arbeitet. Ein Häkchen im Kopf zeigt, dass ein Schritt erledigt ist. Feineinstellungen liegen jeweils zugeklappt unter *Settings*.

### Die sieben Schritte

1. **Project Origin:** Rechtswert, Hochwert und Höhe ±0,00 des Projekts, dazu die Drehung als Abszisse und Ordinate, so wie sie in der IfcMapConversion steht. Unter *H Datum* steht der Höhenbezug als EPSG-Code, in Deutschland `EPSG:7837` für DHHN2016; er geht als VerticalDatum in die IFC. *From IFC* übernimmt die Werte aus der geladenen IFC, *To IFC* schreibt sie hinein, mit True North. Der Knopf mit dem Fadenkreuz legt den Nullpunkt auf den 3D-Cursor. Sobald das Gelände steht, zeigt die **Spiegelprobe**, ob seine Drehung zur Drehung in der IFC passt. Unter *Check Values and North* stehen die Prüfwerte, die Meridiankonvergenz und der Knopf für das Add-on *Sun Position*.
2. **Terrain:** Bei *Terrain* das DGM wählen, bei *Orthophoto* das Luftbild, dann *Load Terrain*. Das Gelände erscheint mit Luftbild, dazu kommen Sonne und Himmel.
3. **Buildings:** Hier erfährt das Werkzeug, wo das eigene Haus steht. Die Bauteile des IFC-Hauses auswählen und *Selection as Building* drücken. Davon hängt dreierlei ab: Bäume und Wiese unter dem Haus verschwinden, im Pappmodell steht das Haus auf seiner Schicht, und die Kameras in Schritt 6 richten sich auf das Haus aus. Gelände, Grundstück und andere Geländeelemente zählen nie als Gebäude, auch wenn sie mit ausgewählt sind; der Knopf meldet, wie viele er weggelassen hat. Darunter lädt man unter *Surroundings (LoD2)* die Nachbargebäude aus einer CityGML-Datei. Gebäude, die das eigene Haus berühren (etwa der Altbestand auf dem Grundstück), werden ausgeblendet.
4. **Vegetation:** Bäume aus dem GeoPackage der Einzelbäume (schnell) oder aus einem Oberflächenmodell (nDOM/DOM, langsam). Im Gelände erscheinen Fichten, Laubbäume und Büsche, im Pappmodell Modellbaum-Kegel. Eigene Baummodelle legt man in die Sammlungen unter *BTK_Site_Tree_Species*. Darunter die Wiese: Gras und Steine nach den Farben des Luftbilds, dicht nahe der aktiven Kamera und weiter weg dünner. In der Ansicht erscheint nur ein Zehntel davon, damit Blender flüssig bleibt.
5. **Cardboard Model:** Schichthöhe wählen und den Knopf mit dem Pfeil drücken. Es entstehen Pappschichten nach den Höhenlinien, mit Grundplatte, Tisch, Licht und Kamera. Die Pappfarbe ist einstellbar, von Graupappe bis Kork.
6. **Cameras:** *Find* sucht eine Kamera in Augenhöhe und ein Schrägluftbild, in denen kein Rand der Geländekachel zu sehen ist, und schaut gleich durch sie hindurch. *Check* prüft die aktive Kamera. Ohne markiertes Haus zielen die Kameras auf den 3D-Cursor.
7. **Terrain to IFC:** Ein Ausschnitt um das Haus wird als IfcGeographicElement (TERRAIN) im IfcSite angelegt. Die Geometrie bleibt nordlagerichtig, die Drehung steht in der Platzierung. Danach die IFC speichern; die Spiegelprobe im IFC muss bestanden sein.

**Pappmodell und IFC:** Im Pappmodell steht das Haus auf seiner Schicht, also leicht versetzt. Dieser Versatz gilt nur für die Ansicht: Wer im Pappmodell speichert, behält die Platzierungen in der IFC unverändert. Das Haus selbst verschiebt man aber nur in der Variante *Terrain*.

## Geplant

- **Später:** Maßzahlen in deutscher Schreibweise, Höhenkote, Dachneigung, Schriftgröße je Maßstab, Geländelinie im Schnitt

## Lizenz

Diese Anleitung steht unter CC BY 4.0. Sie dürfen sie für Ihren Unterricht anpassen und weitergeben, mit Namensnennung.
