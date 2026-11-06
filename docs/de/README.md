# Anleitung für Ausbilder

*Deutsche Anleitung zu `bonsai-btk`. Stand: 0.1.0 in Vorbereitung.*

## Worum es geht

Das Add-on ergänzt Bonsai um Werkzeuge für die Ausbildung zum Bautechnischen Konstrukteur. Dazu gehören Fangen wie im CAD, Maßketten und Höhenkoten nach DIN 1356, Schraffuren als echte Linien und ein Geländemodell aus amtlichen Geodaten. Modelliert wird weiter nativ in IFC. Das Add-on bringt Werkzeuge mit, kein zweites Datenmodell.

Die Oberfläche ist englisch, wie Bonsai selbst. Eine deutsche Sprachdatei kann folgen.

Projektvorlage und Zeichenstil liegen im Schwester-Repository [native-ifc-template](https://github.com/modelllogik/native-ifc-template).

## Abnahmekriterium dieser Anleitung

Sie ist gelungen, wenn Sie ein Werkzeug **ohne Rückfrage** im Unterricht einsetzen können.
Wenn das nicht klappt, ist die Anleitung unvollständig. Bitte melden Sie die Stelle als Issue, gern auf Deutsch.

## Die Werkzeuge

Alle Werkzeuge liegen in der Seitenleiste des 3D-Fensters (Taste N), Reiter **BTK**, Kasten *Dimensions*. Sie arbeiten in einer aktiven Zeichnung im IFC Object Mode.

### Maßkette: *Dimension from Points*

1. Knopf drücken. Die Maus springt ins 3D-Bild. Bauteilecken anklicken. Punkt 1 → Punkt 2 legt die Richtung fest, jeder weitere Punkt wird senkrecht auf die Maßlinie gelegt. *M* springt zur nächsten Ecke in der Nähe, die *Rücktaste* nimmt den letzten Punkt zurück.
2. *Enter*: Die Maus bestimmt Seite und Abstand im Raster 5 mm auf dem Blatt. Alternativ den Abstand in mm tippen. Außerhalb der Außenkante beginnt die erste Kette ab der Außenkante, jede weitere parallele Kette liegt 10 mm weiter außen.
3. *Klick* oder *Enter* legt die Kette als Bonsai-Bemaßung in der aktiven Zeichnung an. *Esc* bricht ab, es entsteht nichts.

Ändert sich der Maßstab der Zeichnung, rücken die so angelegten Ketten nach, damit ihr Abstand auf dem Blatt gleich bleibt.

### Schnittpunktfang: Taste *S*

Beim Punktefangen schaltet *S* auf den Schnittpunkt zweier Kanten um: erste Kante anklicken, zweite Kante anklicken. Übernommen wird der Schnittpunkt der beiden Geraden, auch über die Kantenenden hinaus. Während des Fangs zeigt das Bild die Spurlinien. So wird zum Beispiel der Traufpunkt bemaßt, an dem sich Außenkante Mauerwerk und Außenkante Dachaufbau schneiden. *Rücktaste* nimmt die erste Kante zurück, *S* schaltet ab.

### Maß umdrehen: *Flip Dimension*

Kehrt die Punktreihenfolge der gewählten Maßketten um, die Maßzahlen drehen sich mit. Nach DIN 1356 liest man waagerechte Ketten von links nach rechts und senkrechte von unten nach oben.

## Geplant

- **0.2.0:** Geländemodell: Gelände und Luftbild aus GeoTIFF, Pappschichtenmodell, Bäume, Projektnullpunkt und Georeferenz mit Spiegelprobe
- **Später:** Schraffur als Linien, Maßzahlen in deutscher Schreibweise, Höhenkote, Dachneigung

## Lizenz

Diese Anleitung steht unter CC BY 4.0. Sie dürfen sie für Ihren Unterricht anpassen und weitergeben, mit Namensnennung.
