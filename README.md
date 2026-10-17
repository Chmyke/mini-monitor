# Mini Monitor

Mon logiciel pour le petit écran USB du PC (Turing Smart Screen 3,5", 480x320), à la place du
logiciel fourni (TURZX UsbMonitor).

À gauche, ma consommation Claude : deux anneaux pour la session de 5 h et la semaine, avec le
temps restant avant la remise à zéro. À droite, le PC : carte graphique (température et
utilisation), processeur, mémoire, disque C: et réseau.

Les couleurs passent à l'ambre dès 75 % et au rouge dès 90 % (carte graphique : 75 °C et 85 °C).
Un « ? » gris signifie que le chiffre est inconnu : jamais de valeur périmée.

## Installer

```
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Lancer

```
.venv\Scripts\python -m minimonitor
```

Options : `--brightness 0-100`, `--port COM3`, `--preview image.png` (dessine une image avec les
vraies données, sans l'écran). Un seul programme peut parler à l'écran à la fois.

## Vérifier

```
powershell -ExecutionPolicy Bypass -File check.ps1
```

Affiche `CHECK OK` si tout va bien.
