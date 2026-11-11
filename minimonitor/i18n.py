# SPDX-License-Identifier: GPL-3.0-or-later
"""Screen texts and units, per language."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Texts:
    session: str
    model: str  # first ring when the plan has a model limit whose name is unknown
    week: str
    usage: str
    memory: str
    disk: str
    network: str
    gigabytes: str
    kilobytes_per_s: str
    megabytes_per_s: str
    day: str  # suffix in "3j 22h" / "3d 22h"
    decimal: str


FR = Texts(
    session="SESSION 5 H", model="MODÈLE", week="SEMAINE", usage="utilisation", memory="Mémoire", disk="Disque",
    network="Réseau", gigabytes="Go", kilobytes_per_s="Ko/s", megabytes_per_s="Mo/s", day="j",
    decimal=",",
)

EN = Texts(
    session="5 H SESSION", model="MODEL", week="WEEK", usage="usage", memory="Memory", disk="Disk",
    network="Network", gigabytes="GB", kilobytes_per_s="kB/s", megabytes_per_s="MB/s", day="d",
    decimal=".",
)

LANGUAGES = {"fr": FR, "en": EN}
