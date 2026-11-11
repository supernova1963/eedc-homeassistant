<!-- anker: 48b-zaehlerstaende--sprung-in-home-assistant -->
### 4.8b Zählerstände – Sprung in Home Assistant <a name="48b-zaehlerstaende--sprung-in-home-assistant"></a>

eedc übernimmt die Langzeitstatistik von Home Assistant so, wie das Energie-Dashboard sie zeigt — ohne Obergrenze je
Stunde. Meldet ein Sensor kurz 0 (Wechselrichter nachts „nicht verfügbar“, Neustart) und springt danach in einer Stunde
auf seinen alten Stand zurück, hält Home Assistant das für einen neuen Zähler und bucht beim Zurückkehren den ganzen
Zählerstand als Zuwachs dieser Stunde. Dieser Sprung steht dann in Tag, Monat und Jahr und in der Stunde des
Tagesverlaufs — in eedc wie in Home Assistant. Geprüft werden die letzten 30 Tage.

**Was kein Befund ist.** Ein Zähler, der nach dem Zurücksetzen wieder hochzählt (ein neuer Zähler nach einem Tausch):
dort entsteht kein Sprung. Ein **Tageszähler** (PV-Tagesertrag, Verbrauchszähler „heute“), auch wenn seine erste helle
Stunde nach einem schwachen Vortag den Vortag schon fast erreicht. eedc erkennt ihn an zwei Merkmalen, eines genügt: Er
geht an mindestens zwei Tagen des Prüffensters in der ersten Statistikzeile seines Tages auf 0 — um Mitternacht oder, bei
einem nachts abgeschalteten Wechselrichter, in der ersten Stunde mit Werten. Oder sein Stand vor der 0 ist höchstens das
Dreifache seines größten Tageszuwachses im Prüffenster: ein Tageszähler kommt nie über einen Tag hinaus, ein
Gesamtzähler liegt weit darüber. Am Tageszähler ist nur der **Aussetzer** ein Befund: eine 0 mitten im Tag, auf die der
alte Stand in der unmittelbar nächsten Stunde zurückkommt — dann hat Home Assistant den Tag doppelt gebucht.

**Grenzen:** Ein Gesamtzähler mit weniger als drei Tagen eigener Historie und ein Monatszähler in seinen ersten drei
Tagen gelten als Tageszähler (ihr Sprung wäre entsprechend klein); ein Aussetzer über zwei oder mehr Stunden am
Tageszähler ist von einem Tagesbeginn nach einer Lücke nicht zu trennen und wird nicht gemeldet. Die Prüfung erkennt nur
dieses Muster (Rücksetzen und Rückkehr). Springt die Summe in Home Assistant ohne Rücksetzen, meldet weder sie noch die
Prüfung auf unmögliche Stundenwerte ([§4.7](#47-energieprofil--plausibilitaet)) an einem solchen Tag etwas.

---
