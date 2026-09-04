#!/usr/bin/env python3
"""Produit des cartes WebP depuis la grille native MFWAM Météo-France.

Les champs ne sont jamais interpolés depuis des points épars : la grille
FRANGP0025 (0,025°) native du GRIB2 est rééchantillonnée sur une image Web
Mercator couvrant la façade maritime française, puis le trait de côte est
ajouté dans une surcouche SVG indépendante.
"""

from __future__ import annotations

import json
import math
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


MAP_SCHEMA_VERSION = 1
MODULE_VERSION = "1.2.0"
DEFAULT_BOUNDS = {
    "south": 38.0,
    "west": -8.0,
    "north": 53.0,
    "east": 12.0,
}


def _iter_shapefile_parts(path: Path):
    """Lit les lignes/polygones ESRI Shapefile sans dépendance externe."""

    with path.open("rb") as handle:
        header = handle.read(100)
        if len(header) != 100 or struct.unpack_from(">i", header, 0)[0] != 9994:
            raise ValueError(f"En-tête Shapefile invalide : {path}")

        while True:
            record_header = handle.read(8)
            if not record_header:
                break
            if len(record_header) != 8:
                raise ValueError(f"Enregistrement Shapefile tronqué : {path}")

            _record_number, content_words = struct.unpack(">2i", record_header)
            content_size = content_words * 2
            content = handle.read(content_size)
            if len(content) != content_size:
                raise ValueError(f"Contenu Shapefile tronqué : {path}")
            if len(content) < 4:
                continue

            shape_type = struct.unpack_from("<i", content, 0)[0]
            if shape_type == 0:
                continue
            if shape_type not in {3, 5, 13, 15, 23, 25} or len(content) < 44:
                continue

            part_count, point_count = struct.unpack_from("<2i", content, 36)
            if part_count <= 0 or point_count <= 0:
                continue
            required_size = 44 + 4 * part_count + 16 * point_count
            if len(content) < required_size:
                raise ValueError(f"Géométrie Shapefile tronquée : {path}")

            part_starts = list(struct.unpack_from(f"<{part_count}i", content, 44))
            points_offset = 44 + 4 * part_count
            part_ends = part_starts[1:] + [point_count]
            for start, end in zip(part_starts, part_ends):
                if start < 0 or end > point_count or start >= end:
                    continue
                yield [
                    struct.unpack_from("<2d", content, points_offset + index * 16)
                    for index in range(start, end)
                ]


@dataclass(frozen=True)
class LayerSpec:
    key: str
    label: str
    unit: str
    field: str
    stops: tuple[tuple[float, str], ...]
    group: str = "Vent"
    decimals: int = 1
    transparent_below: float | None = None
    opacity: int = 235
    discrete: bool = False


LAYER_SPECS = (
    LayerSpec(
        "hauteur_significative",
        "Hauteur significative des vagues",
        "m",
        "swh_m",
        (
            (0, "#0b2e5c"), (0.5, "#134a8a"), (1, "#1c6cb0"),
            (1.5, "#2c93c9"), (2, "#3fbfc9"), (3, "#57cf8e"),
            (4, "#a8dc4e"), (5, "#f2d43d"), (6, "#f2a331"),
            (8, "#ea652b"), (10, "#d93435"), (13, "#8c1d4a"),
        ),
        group="Vent",
        decimals=1,
    ),
    LayerSpec(
        "hauteur_mer_du_vent",
        "Hauteur mer du vent",
        "m",
        "shww_m",
        (
            (0, "#0b2e5c"), (0.3, "#134a8a"), (0.6, "#1c6cb0"),
            (1, "#2c93c9"), (1.5, "#3fbfc9"), (2, "#57cf8e"),
            (3, "#a8dc4e"), (4, "#f2d43d"), (5, "#f2a331"),
            (7, "#ea652b"), (9, "#d93435"),
        ),
        group="Vent",
        decimals=1,
    ),
    LayerSpec(
        "periode_moyenne",
        "Période moyenne des vagues",
        "s",
        "mwp_s",
        (
            (0, "#3f1d69"), (2, "#354bab"), (4, "#3384c3"),
            (6, "#3cb9aa"), (8, "#b5d04d"), (10, "#efad3b"),
            (12, "#cf493e"), (16, "#8c1d4a"),
        ),
        group="Vent",
        decimals=1,
    ),
    LayerSpec(
        "periode_mer_du_vent",
        "Période mer du vent",
        "s",
        "mpww_s",
        (
            (0, "#3f1d69"), (1.5, "#354bab"), (3, "#3384c3"),
            (4.5, "#3cb9aa"), (6, "#b5d04d"), (8, "#efad3b"),
            (10, "#cf493e"), (13, "#8c1d4a"),
        ),
        group="Vent",
        decimals=1,
    ),
    LayerSpec(
        "hauteur_houle_totale",
        "Hauteur de la houle totale",
        "m",
        "shs_m",
        (
            (0, "#0b2e5c"), (0.3, "#134a8a"), (0.6, "#1c6cb0"),
            (1, "#2c93c9"), (1.5, "#3fbfc9"), (2, "#57cf8e"),
            (3, "#a8dc4e"), (4, "#f2d43d"), (5, "#f2a331"),
            (7, "#ea652b"), (9, "#d93435"),
        ),
        group="Houle",
        decimals=1,
    ),
    LayerSpec(
        "hauteur_houle_primaire",
        "Hauteur houle primaire",
        "m",
        "shps_m",
        (
            (0, "#0b2e5c"), (0.3, "#134a8a"), (0.6, "#1c6cb0"),
            (1, "#2c93c9"), (1.5, "#3fbfc9"), (2, "#57cf8e"),
            (3, "#a8dc4e"), (4, "#f2d43d"), (5, "#f2a331"),
            (7, "#ea652b"), (9, "#d93435"),
        ),
        group="Houle",
        decimals=1,
    ),
    LayerSpec(
        "hauteur_houle_secondaire",
        "Hauteur houle secondaire",
        "m",
        "shss_m",
        (
            (0, "#0b2e5c"), (0.2, "#134a8a"), (0.4, "#1c6cb0"),
            (0.7, "#2c93c9"), (1, "#3fbfc9"), (1.5, "#57cf8e"),
            (2, "#a8dc4e"), (3, "#f2d43d"), (4, "#f2a331"),
            (5, "#ea652b"), (7, "#d93435"),
        ),
        group="Houle",
        decimals=1,
    ),
    LayerSpec(
        "periode_houle_totale",
        "Période de la houle totale",
        "s",
        "mps_s",
        (
            (0, "#3f1d69"), (3, "#354bab"), (6, "#3384c3"),
            (9, "#3cb9aa"), (12, "#b5d04d"), (15, "#efad3b"),
            (18, "#cf493e"), (22, "#8c1d4a"),
        ),
        group="Houle",
        decimals=1,
    ),
    LayerSpec(
        "periode_houle_primaire",
        "Période houle primaire",
        "s",
        "mpps_s",
        (
            (0, "#3f1d69"), (3, "#354bab"), (6, "#3384c3"),
            (9, "#3cb9aa"), (12, "#b5d04d"), (15, "#efad3b"),
            (18, "#cf493e"), (22, "#8c1d4a"),
        ),
        group="Houle",
        decimals=1,
    ),
    LayerSpec(
        "periode_houle_secondaire",
        "Période houle secondaire",
        "s",
        "mpss_s",
        (
            (0, "#3f1d69"), (3, "#354bab"), (6, "#3384c3"),
            (9, "#3cb9aa"), (12, "#b5d04d"), (15, "#efad3b"),
            (18, "#cf493e"), (22, "#8c1d4a"),
        ),
        group="Houle",
        decimals=1,
    ),
    LayerSpec(
        "periode_pic",
        "Période de pic des vagues",
        "s",
        "pp1d_s",
        (
            (0, "#3f1d69"), (3, "#354bab"), (6, "#3384c3"),
            (9, "#3cb9aa"), (12, "#b5d04d"), (15, "#efad3b"),
            (18, "#cf493e"), (24, "#8c1d4a"),
        ),
        group="Houle",
        decimals=1,
    ),
)


def _hex_to_rgb(value: str) -> np.ndarray:
    clean = value.lstrip("#")
    return np.asarray(tuple(int(clean[index : index + 2], 16) for index in (0, 2, 4)))


def _mercator(latitude):
    radians = np.radians(np.clip(latitude, -85.0, 85.0))
    return np.log(np.tan(np.pi / 4.0 + radians / 2.0))


def _inverse_mercator(value):
    return np.degrees(2.0 * np.arctan(np.exp(value)) - np.pi / 2.0)


class WaveMapRenderer:
    """Rend les champs MFWAM pré-rééchantillonnés et le trait de côte."""

    def __init__(
        self,
        output_directory: Path,
        *,
        width: int = 2400,
        height: int = 2400,
        bounds: dict[str, float] | None = None,
        boundary_directory: Path | None = None,
    ) -> None:
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.width = int(width)
        self.height = int(height)
        self.bounds = dict(bounds or DEFAULT_BOUNDS)
        self.boundary_directory = (
            Path(boundary_directory) if boundary_directory is not None else None
        )
        self.steps: list[dict[str, Any]] = []
        self.available_layers: set[str] = set()
        self._coverage_mask = np.ones((self.height, self.width), dtype=bool)
        self._write_static_maps()

    def _image_from_field(self, field: np.ndarray, spec: LayerSpec) -> Image.Image:
        stop_values = np.asarray([item[0] for item in spec.stops], dtype=np.float32)
        stop_colours = np.asarray([_hex_to_rgb(item[1]) for item in spec.stops])
        finite_field = np.isfinite(field)
        clipped = np.clip(
            np.where(finite_field, field, stop_values[0]),
            stop_values[0],
            stop_values[-1],
        )
        upper = np.searchsorted(stop_values, clipped, side="right")
        upper = np.clip(upper, 1, len(stop_values) - 1)
        lower = upper - 1
        if spec.discrete:
            rgb = stop_colours[lower].astype(np.uint8)
        else:
            low_values = stop_values[lower]
            high_values = stop_values[upper]
            fraction = np.divide(
                clipped - low_values,
                high_values - low_values,
                out=np.zeros_like(clipped),
                where=(high_values != low_values),
            )
            rgb = (
                stop_colours[lower] * (1.0 - fraction[..., None])
                + stop_colours[upper] * fraction[..., None]
            ).astype(np.uint8)
        alpha = np.full(field.shape, spec.opacity, dtype=np.uint8)
        valid = self._coverage_mask & finite_field
        if spec.transparent_below is not None:
            valid &= field >= spec.transparent_below
        alpha[~valid] = 0
        return Image.fromarray(np.dstack((rgb, alpha)), mode="RGBA")

    def _pixel(self, latitude: float, longitude: float) -> tuple[int, int]:
        west = float(self.bounds["west"])
        east = float(self.bounds["east"])
        north_y = float(_mercator(float(self.bounds["north"])))
        south_y = float(_mercator(float(self.bounds["south"])))
        x = (longitude - west) / (east - west) * (self.width - 1)
        y = (north_y - float(_mercator(latitude))) / (north_y - south_y)
        y *= self.height - 1
        return int(round(x)), int(round(y))

    def _shapefile_svg_path(self, path: Path) -> str:
        if not path.is_file():
            return ""
        south = float(self.bounds["south"]) - 1
        north = float(self.bounds["north"]) + 1
        west = float(self.bounds["west"]) - 1
        east = float(self.bounds["east"]) + 1
        paths: list[str] = []
        for points in _iter_shapefile_parts(path):
            segment: list[tuple[float, float]] = []
            for longitude, latitude in points:
                if west <= longitude <= east and south <= latitude <= north:
                    segment.append(self._pixel(latitude, longitude))
                elif segment:
                    if len(segment) >= 2:
                        paths.append(
                            "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in segment)
                        )
                    segment = []
            if len(segment) >= 2:
                paths.append("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in segment))
        return " ".join(paths)

    def _write_static_maps(self) -> None:
        base = Image.new("RGB", (self.width, self.height), "#0a1f3d")
        base.save(self.output_directory / "fond.webp", "WEBP", quality=86, method=4)

        coastline_path = ""
        national_path = ""
        if self.boundary_directory is not None:
            coastline_path = self._shapefile_svg_path(
                self.boundary_directory / "ne_50m_coastline.shp",
            )
            national_path = self._shapefile_svg_path(
                self.boundary_directory / "ne_50m_admin_0_boundary_lines_land.shp",
            )
        svg = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width} '
            f'{self.height}" preserveAspectRatio="none" '
            'shape-rendering="geometricPrecision">\n'
            f'<path d="{national_path}" fill="none" stroke="#1a2230" '
            'stroke-opacity="0.55" stroke-width="1" stroke-linejoin="round" '
            'vector-effect="non-scaling-stroke"/>\n'
            f'<path d="{coastline_path}" fill="none" stroke="#e8ecf2" '
            'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" '
            'vector-effect="non-scaling-stroke"/>\n'
            '</svg>\n'
        )
        (self.output_directory / "frontieres.svg").write_text(svg, encoding="utf-8")

    def render_step(
        self,
        *,
        lead_hour: int,
        valid_time: datetime,
        fields: dict[str, np.ndarray],
    ) -> None:
        files: dict[str, str] = {}
        for spec in LAYER_SPECS:
            values = fields.get(spec.field)
            if values is None or not np.any(np.isfinite(values)):
                continue
            destination_directory = self.output_directory / spec.key
            destination_directory.mkdir(parents=True, exist_ok=True)
            destination = destination_directory / f"{lead_hour:03d}.webp"
            image = self._image_from_field(values, spec)
            image.save(destination, "WEBP", quality=86, method=5)
            files[spec.key] = f"maps/{spec.key}/{destination.name}"
            self.available_layers.add(spec.key)

        self.steps.append(
            {
                "lead_hour": int(lead_hour),
                "valid_time": valid_time.isoformat().replace("+00:00", "Z"),
                "files": files,
            }
        )

    def write_manifest(self, *, generated_at: str, run_time: str | None) -> dict[str, Any]:
        layers = {
            spec.key: {
                "label": spec.label,
                "unit": spec.unit,
                "group": spec.group,
                "decimals": spec.decimals,
                "discrete": spec.discrete,
                "stops": [{"value": value, "color": colour} for value, colour in spec.stops],
            }
            for spec in LAYER_SPECS
            if spec.key in self.available_layers
        }
        manifest = {
            "schema_version": MAP_SCHEMA_VERSION,
            "status": "ok",
            "module_version": MODULE_VERSION,
            "generated_at": generated_at,
            "run_time": run_time,
            "projection": "EPSG:3857",
            "bounds": self.bounds,
            "width": self.width,
            "height": self.height,
            "background": "maps/fond.webp",
            "overlay": "maps/frontieres.svg",
            "layers": layers,
            "steps": self.steps,
        }
        destination = self.output_directory / "index.json"
        with destination.open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        return manifest
