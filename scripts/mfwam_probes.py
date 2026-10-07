"""Grilles de valeurs (« probes ») des champs de vagues, lues par la carte marine du site.

Format identique aux grilles AROME : fichier gzip, en-tête « HKV1 » (largeur, hauteur, minimum, maximum),
puis un entier non signé 16 bits par cellule (65535 = pas de valeur). Les lignes suivent la projection
Web Mercator du manifeste des cartes, comme les images.
"""

from __future__ import annotations

import gzip
import struct
from pathlib import Path

import numpy as np

# Clé de la grille publiée -> champ interne lu dans le GRIB2.
PROBE_FIELDS = {
    "hs": "swh_m",  # hauteur significative (m)
    "tp": "mwp_s",  # période moyenne (s)
    "tp_pic": "pp1d_s",  # période de pic (s)
    "dir": "mwd_deg",  # direction moyenne d'où viennent les vagues (° vrais)
    "wind_h": "shww_m",  # hauteur de la mer du vent (m)
    "wind_tp": "mpww_s",
    "wind_dir": "wvdir_deg",
    "swell_h": "shs_m",  # hauteur de la houle totale (m)
    "swell_tp": "mps_s",
    "swell_dir": "swdir_deg",
}

# Champs lus uniquement pour les grilles de valeurs (pas de carte image) : directions.
PROBE_ONLY_FIELDS = {"mwd_deg", "wvdir_deg", "swdir_deg"}
DIRECTION_FIELDS = {"mwd_deg", "wvdir_deg", "swdir_deg"}


def write_hkv(path: Path, values: np.ndarray) -> bool:
    """Écrit une grille HKV1 compressée ; renvoie False si le champ est entièrement vide."""
    finite = np.isfinite(values)
    if not finite.any():
        return False
    vmin = float(values[finite].min())
    vmax = float(values[finite].max())
    if vmax - vmin < 1e-6:
        vmax = vmin + 1.0
    raw = np.full(values.shape, 65535, dtype="<u2")
    raw[finite] = np.rint((values[finite] - vmin) / (vmax - vmin) * 65534).astype("<u2")
    height, width = values.shape
    header = b"HKV1" + struct.pack("<HHff", width, height, vmin, vmax)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb", compresslevel=9) as handle:
        handle.write(header + raw.tobytes())
    return True


def write_step_probes(maps_directory: Path, lead_hour: int, fields: dict[str, np.ndarray]) -> dict[str, str]:
    """Écrit les grilles d'une échéance ; renvoie {clé: chemin relatif} pour le manifeste."""
    written: dict[str, str] = {}
    for key, field_name in PROBE_FIELDS.items():
        values = fields.get(field_name)
        if values is None:
            continue
        relative = f"maps/values/{key}/{lead_hour:03d}.hkv.gz"
        if write_hkv(maps_directory.parent / relative, values):
            written[key] = relative
    return written
