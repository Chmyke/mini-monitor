# Mini Monitor

*[English version](README.md) · [Site](https://mickaelmancini.com/mini-monitor/)*

Un petit tableau de bord sobre pour l'écran USB de 3,5" vendu sous les noms **Turing Smart
Screen** ou **UsbMonitor**, écrit pour remplacer le logiciel du fabricant. À gauche, la
**consommation de ton abonnement Claude** ; à droite, le PC.

![Mini Monitor sur l'écran de 3,5" : deux anneaux pour la session de 5 h et la semaine Claude, puis carte graphique, processeur, mémoire, disque et réseau](docs/screen-fr.webp)

- **Claude en vedette.** Deux anneaux pour la session de 5 h et la semaine, avec le temps restant
  avant chaque remise à zéro. Ambre dès 75 %, rouge dès 90 %.
- **Le PC d'un coup d'œil.** Température et charge de la carte graphique (NVIDIA), processeur,
  mémoire, disque C: et réseau, chacun avec une fine barre. Les valeurs glissent vers chaque
  nouvelle mesure au lieu de sauter.
- **Honnête.** Une valeur inconnue s'affiche « ? » en gris, jamais un chiffre périmé.
- **Léger.** Environ 2 % d'un cœur. Le lien USB est lent (1,2 s pour un écran complet) : l'image
  est dessinée en mémoire et seules les zones qui ont changé sont envoyées.
- **Deux langues.** Français par défaut, anglais avec `--lang en`.

## Matériel

Testé sur le Turing Smart Screen 3,5" vendu sous le nom *UsbMonitor* (USB `1A86:5722`, série
`USB35INCHIPSV2`), en paysage. Les autres tailles et révisions ne sont pas encore gérées.

## Prérequis

- Windows 10 ou 11 (les polices sont lues dans `C:\Windows\Fonts`).
- Python 3.11 ou plus récent.
- Pour la carte graphique : une carte NVIDIA et son pilote. Sinon la ligne affiche « ? ».
- Pour les anneaux Claude : un abonnement Claude connecté avec
  [Claude Code](https://claude.com/claude-code) (`claude auth login`). Les anneaux lisent le jeton
  que Claude Code range dans `~/.claude/.credentials.json`.

## Installer

```
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Lancer

Ferme d'abord le logiciel du fabricant : un seul programme peut parler à l'écran à la fois.

```
.venv\Scripts\python -m minimonitor
```

| Option | Effet |
|---|---|
| `--lang fr\|en` | langue de l'écran (`fr` par défaut) |
| `--brightness 0-100` | rétroéclairage (60 par défaut) |
| `--port COM3` | port série (détecté par défaut) |
| `--preview image.png` | dessine une image avec les vraies données, sans l'écran |
| `--demo dossier` | écrit l'image et l'animation de démonstration (valeurs inventées) |

## Démarrer avec Windows

```
powershell -ExecutionPolicy Bypass -File install-startup.ps1
```

Ce script crée une tâche planifiée, *Mini Monitor*, lancée à l'ouverture de session, sans fenêtre
ni droits administrateur (options : `-Lang en`, `-Brightness 40` ; `-Uninstall` la retire). Elle
résiste au débranchement de l'écran, à une réinitialisation USB et à la mise en veille : l'écran
est rouvert toutes les quelques secondes puis redessiné en entier. Une deuxième copie attend
quelques secondes puis renonce, puisqu'un seul programme peut parler à l'écran.

Le journal est dans `%LOCALAPPDATA%\MiniMonitor\minimonitor.log` (connexions, coupures,
renouvellements du jeton, images lentes ; jamais un jeton).

## Vie privée

Toutes les 5 minutes, Mini Monitor envoie une requête, `GET https://api.anthropic.com/api/oauth/usage`,
avec ton jeton Claude. Peu avant son expiration, il le renouvelle comme le fait Claude Code
(`POST https://platform.claude.com/v1/oauth/token`) et réécrit les nouveaux jetons dans
`~/.claude/.credentials.json`, de façon atomique, sans toucher au reste du fichier. Les jetons ne
sont jamais affichés ni journalisés. Rien d'autre ne sort du PC.

Ces adresses sont celles de Claude Code ; elles ne sont pas documentées et peuvent changer : les
anneaux afficheraient alors « ? ». Si le renouvellement lui-même expire, reconnecte-toi avec
`claude auth login`.

## Vérifier

```
powershell -ExecutionPolicy Bypass -File check.ps1
```

Affiche `CHECK OK` si tout va bien.

## Crédits et licence

Le protocole série de l'écran vient de
[turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python), de
Matthieu Houdebine (GPL-3.0) ; Mini Monitor utilise son propre petit pilote. Licence
[GPL-3.0 ou ultérieure](LICENSE).
