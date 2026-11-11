<!-- anker: 433-speicher -->
#### 4.3.3 Speicher

Am Speicher prüft eedc die Kapazität, bei eingeschalteter Arbitrage die beiden erwarteten Preise, die monatliche Ladung
und — über die ganze Geschichte — ob Netzladung und Entladung zur Ladung passen. «Ladung» ist immer die gesamte Ladung
(PV und Netz), «Netzladung» ein Teil davon.

**Warum eedc für Arbitrage eine Angabe braucht:** Arbitrage lebt davon, dass dieselbe Kilowattstunde zu verschiedenen
Uhrzeiten verschieden viel kostet — und ein eedc-Tarif kennt keine Uhrzeit. Die beiden Preisfelder «Ø Ladepreis» und
«Ø Entladepreis» stehen im Formular des Speichers unter «Netzladung & Arbitrage», sobald «Arbitrage-fähig» an ist. Wer
einen dynamischen Tarif (Tibber, aWATTar, EPEX) angebunden hat: dort zieht eedc für die gemessenen Monate den
stundengenauen Preis vor; Prognose und Amortisation rechnen weiter mit den beiden Preisen am Speicher, deshalb fragt der
Checker sie trotzdem.
