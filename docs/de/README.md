# Anleitung für Ausbilder

*Deutsche Anleitung zu `bonsai-btk`. Stand: 0.2.0 in Vorbereitung.*

## Worum es geht

Das Add-on ergänzt Bonsai um Werkzeuge für die Ausbildung zum Bautechnischen Konstrukteur. Dazu gehören Fangen wie im CAD, Maßketten und Höhenkoten nach DIN 1356, Schraffuren als echte Linien und ein Geländemodell aus amtlichen Geodaten. Modelliert wird weiter nativ in IFC. Das Add-on bringt Werkzeuge mit, kein zweites Datenmodell.

Die Oberfläche ist englisch, wie Bonsai selbst. Eine deutsche Sprachdatei kann folgen.

Projektvorlage und Zeichenstil liegen im Schwester-Repository [native-ifc-template](https://github.com/modelllogik/native-ifc-template).

## Abnahmekriterium dieser Anleitung

Sie ist gelungen, wenn Sie ein Werkzeug **ohne Rückfrage** im Unterricht einsetzen können.
Wenn das nicht klappt, ist die Anleitung unvollständig. Bitte melden Sie die Stelle als Issue, gern auf Deutsch.

## Die Werkzeuge

Alle Werkzeuge liegen in der Seitenleiste des 3D-Fensters (Taste N), Reiter **BTK**: im Kasten *Dimensions* das Zeichnen, im Kasten *Site* das Gelände.

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

## Gelände: Kasten *Site*

Die Gelände-Werkzeuge bauen die Umgebung eines Gebäudes aus amtlichen Geodaten auf, vom echten Gelände bis zum Pappmodell auf dem Tisch. Alles, was sie anlegen, hängt an einem Leerobjekt *BTK_Site_Origin*. Verschiebt man den Projektnullpunkt, wandert alles mit, ohne neu gerechnet zu werden.

**Daten.** Für Bayern gibt es Gelände (DGM1), Luftbilder (DOP), 3D-Gebäude (LoD2) und Einzelbäume kostenlos im OpenData-Portal [geodaten.bayern.de](https://geodaten.bayern.de) unter CC BY 4.0. Die Daten kommen in Kacheln von 1 km. Das Add-on liest je Ebene eine GeoTIFF-Datei, mehrere Kacheln setzt man vorher zusammen, etwa in QGIS mit dem GDAL-Werkzeug *Merge*. Andere Länder bieten ähnliche Daten an. Das Bezugssystem muss projiziert und metrisch sein, etwa ETRS89 / UTM.

### Aufbau des Kastens

Oben im Kasten *Site* schaltet man zwischen *Terrain* und *Cardboard Model* um, blendet Luftbild, Bäume und Wiese ein oder aus und wählt die Kamera; der Knopf daneben schaut durch sie hindurch. Darunter folgen sieben Schritte in der Reihenfolge, in der man arbeitet. Ein Häkchen im Kopf zeigt, dass ein Schritt erledigt ist. Feineinstellungen liegen jeweils zugeklappt unter *Settings*.

### Die sieben Schritte

1. **Project Origin:** Rechtswert, Hochwert und Höhe ±0,00 des Projekts, dazu die Drehung als Abszisse und Ordinate, so wie sie in der IfcMapConversion steht. *From IFC* übernimmt die Werte aus der geladenen IFC, *To IFC* schreibt sie hinein, mit True North. Der Knopf mit dem Fadenkreuz legt den Nullpunkt auf den 3D-Cursor. Sobald das Gelände steht, zeigt die **Spiegelprobe**, ob seine Drehung zur Drehung in der IFC passt. Unter *Check Values and North* stehen die Prüfwerte, die Meridiankonvergenz und der Knopf für das Add-on *Sun Position*.
2. **Terrain:** Bei *Terrain* das DGM wählen, bei *Orthophoto* das Luftbild, dann *Load Terrain*. Das Gelände erscheint mit Luftbild, dazu kommen Sonne und Himmel.
3. **Buildings:** Hier erfährt das Werkzeug, wo das eigene Haus steht. Die Bauteile des IFC-Hauses auswählen und *Selection as Building* drücken. Davon hängt dreierlei ab: Bäume und Wiese unter dem Haus verschwinden, im Pappmodell steht das Haus auf seiner Schicht, und die Kameras in Schritt 6 richten sich auf das Haus aus. Gelände, Grundstück und andere Geländeelemente zählen nie als Gebäude, auch wenn sie mit ausgewählt sind; der Knopf meldet, wie viele er weggelassen hat. Darunter lädt man unter *Surroundings (LoD2)* die Nachbargebäude aus einer CityGML-Datei. Gebäude, die das eigene Haus berühren (etwa der Altbestand auf dem Grundstück), werden ausgeblendet.
4. **Vegetation:** Bäume aus dem GeoPackage der Einzelbäume (schnell) oder aus einem Oberflächenmodell (nDOM/DOM, langsam). Im Gelände erscheinen Fichten, Laubbäume und Büsche, im Pappmodell Modellbaum-Kegel. Eigene Baummodelle legt man in die Sammlungen unter *BTK_Site_Tree_Species*. Darunter die Wiese: Gras und Steine nach den Farben des Luftbilds, dicht nahe der aktiven Kamera und weiter weg dünner. In der Ansicht erscheint nur ein Zehntel davon, damit Blender flüssig bleibt.
5. **Cardboard Model:** Schichthöhe wählen und den Knopf mit dem Pfeil drücken. Es entstehen Pappschichten nach den Höhenlinien, mit Grundplatte, Tisch, Licht und Kamera. Die Pappfarbe ist einstellbar, von Graupappe bis Kork.
6. **Cameras:** *Find* sucht eine Kamera in Augenhöhe und ein Schrägluftbild, in denen kein Rand der Geländekachel zu sehen ist, und schaut gleich durch sie hindurch. *Check* prüft die aktive Kamera. Ohne markiertes Haus zielen die Kameras auf den 3D-Cursor.
7. **Terrain to IFC:** Ein Ausschnitt um das Haus wird als IfcGeographicElement (TERRAIN) im IfcSite angelegt. Die Geometrie bleibt nordlagerichtig, die Drehung steht in der Platzierung. Danach die IFC speichern; die Spiegelprobe im IFC muss bestanden sein.

**Pappmodell und IFC:** Im Pappmodell steht das Haus auf seiner Schicht, also leicht versetzt. Dieser Versatz gilt nur für die Ansicht: Wer im Pappmodell speichert, behält die Platzierungen in der IFC unverändert. Das Haus selbst verschiebt man aber nur in der Variante *Terrain*.

## Geplant

- **Später:** Schraffur als Linien, Maßzahlen in deutscher Schreibweise, Höhenkote, Dachneigung

## Lizenz

Diese Anleitung steht unter CC BY 4.0. Sie dürfen sie für Ihren Unterricht anpassen und weitergeben, mit Namensnennung.
