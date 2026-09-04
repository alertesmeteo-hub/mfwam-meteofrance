#!/usr/bin/env python3
"""Construit les cartes MFWAM 0,025° (vagues) pour la façade française.

La chaîne lit directement les paquets GRIB2 ouverts de Météo-France publiés
sur data.gouv.fr (grille FRANGP0025, un seul groupe SP1 par échéance
regroupant tous les paramètres vagues). Seules quatre variables sont
extraites dans cette première version : hauteur significative, hauteur et
période de la mer du vent, période moyenne des vagues.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import shutil
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import requests
from eccodes import (
    codes_get,
    codes_get_double_array,
    codes_grib_new_from_file,
    codes_release,
)
from scipy.ndimage import distance_transform_edt, map_coordinates

from mfwam_maps import DEFAULT_BOUNDS, WaveMapRenderer


LOGGER = logging.getLogger("mfwam.france")
PIPELINE_VERSION = "1.2.1"
DATASET_API = (
    "https://www.data.gouv.fr/api/1/datasets/"
    "paquets-de-modele-de-vagues-mfwam-resolution-0-025deg/"
)
DATASET_PAGE = (
    "https://www.data.gouv.fr/datasets/"
    "paquets-de-modele-de-vagues-mfwam-resolution-0-025deg"
)
DEFAULT_CURRENT_METADATA_URL = (
    "https://raw.githubusercontent.com/alertesmeteo-hub/mfwam-meteofrance/data/index.json"
)
USER_AGENT = "alertes-meteo.com/mfwam-meteofrance-france/1.0"

MAP_WIDTH = 2400
MAP_HEIGHT = 2400

# shortName GRIB2 -> nom de champ interne, vérifié par lecture directe d'un
# fichier SP1 réel (les tables eccodes par défaut ne connaissent pas tous
# les noms courts officiels Météo-France : SHS/MPS s'appellent "shts"/"mpts"
# côté GRIB2, pas "shs"/"mps"). Les directions (MWD, MDWW, MDS, MDPS, MDSS)
# et le vent (WIND=10si, DWI=10wdir) ne sont pas encore exploités.
FIELD_BY_SHORTNAME = {
    "swh": "swh_m",
    "shww": "shww_m",
    "mpww": "mpww_s",
    "mwp": "mwp_s",
    "shts": "shs_m",
    "mpts": "mps_s",
    "pp1d": "pp1d_s",
}

# La houle primaire et secondaire (MDPS/MPPS/SHPS/MDSS/MPSS/SHSS) est un
# paramètre local Météo-France : eccodes ne lui connaît pas de shortName
# ("unknown") et il faut l'identifier par (discipline, category, number).
# Vérifié par lecture directe d'un fichier SP1 réel du 2026-09-04.
# Indice Benjamin-Feir, hauteur maximale individuelle et sa période
# n'apparaissent dans aucun message du paquet ouvert SP1 : non publiables.
FIELD_BY_LOCAL_PARAMETER = {
    (10, 0, 195): "mpps_s",
    (10, 0, 192): "shps_m",
    (10, 0, 197): "mpss_s",
    (10, 0, 193): "shss_m",
}

RESOURCE_RE = re.compile(
    r"^vague-surcote-MFWAM__0025__SP1__(?P<lead>\d{3})H__(?P<run>.+)\.grib2$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Resource:
    lead: int
    run_text: str | None
    title: str
    url: str | None
    size: int | None
    local_path: Path | None = None


class IncompleteRunError(RuntimeError):
    """Le catalogue distant ne contient pas encore un run MFWAM cohérent."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="build/mfwam-national",
        help="Dossier de publication à produire",
    )
    parser.add_argument(
        "--resource-directory",
        help="Dossier local de GRIB2 SP1 pour les tests hors ligne",
    )
    parser.add_argument(
        "--current-metadata-url",
        default=DEFAULT_CURRENT_METADATA_URL,
        help="index.json actuellement publié, pour éviter un run identique",
    )
    parser.add_argument(
        "--catalog-attempts",
        type=int,
        default=4,
        help="Nombre de lectures du catalogue data.gouv.fr si un run est incomplet",
    )
    parser.add_argument(
        "--catalog-retry-seconds",
        type=int,
        default=60,
        help="Attente entre deux lectures du catalogue incomplet (défaut : 60 s)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force la reconstruction même si ce run est déjà publié",
    )
    return parser.parse_args()


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_run_text(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def safe_get(gid: int, key: str, default: Any = None) -> Any:
    try:
        return codes_get(gid, key)
    except Exception:
        return default


def grib_datetime(gid: int, date_key: str, time_key: str) -> datetime | None:
    date_value = safe_get(gid, date_key)
    time_value = safe_get(gid, time_key)
    if date_value is None or time_value is None:
        return None
    try:
        return datetime.strptime(
            f"{int(date_value):08d}{int(time_value):04d}", "%Y%m%d%H%M"
        ).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def api_resources(session: requests.Session) -> list[Resource]:
    response = session.get(
        DATASET_API,
        params={"_": int(time.time())},
        headers={"Cache-Control": "no-cache"},
        timeout=(15, 90),
    )
    response.raise_for_status()
    payload = response.json()
    resources: list[Resource] = []
    for item in payload.get("resources") or []:
        title = str(item.get("title") or "")
        match = RESOURCE_RE.match(title)
        if not match:
            continue
        resources.append(
            Resource(
                lead=int(match.group("lead")),
                run_text=match.group("run"),
                title=title,
                url=str(item.get("url") or ""),
                size=int(item.get("filesize") or 0) or None,
            )
        )
    if not resources:
        raise RuntimeError("Aucune ressource MFWAM 0,025° trouvée sur data.gouv.fr")
    return resources


def local_resources(directory: Path) -> list[Resource]:
    resources: list[Resource] = []
    for path in sorted(directory.glob("*.grib2")):
        match = RESOURCE_RE.match(path.name)
        if not match:
            continue
        resources.append(
            Resource(
                lead=int(match.group("lead")),
                run_text=match.group("run"),
                title=path.name,
                url=None,
                size=path.stat().st_size,
                local_path=path.resolve(),
            )
        )
    if not resources:
        raise RuntimeError(f"Aucun GRIB2 MFWAM reconnu dans {directory}")
    return resources


def choose_resources(
    resources: Iterable[Resource],
) -> tuple[dict[int, Resource], datetime | None]:
    resources = list(resources)
    grouped: dict[str, dict[int, Resource]] = defaultdict(dict)
    for resource in resources:
        grouped[resource.run_text or "local"][resource.lead] = resource

    candidates: list[tuple[datetime, str, dict[int, Resource]]] = []
    for run_text, selection in grouped.items():
        # Un run MFWAM cohérent doit au moins couvrir +01 h à +24 h sans trou.
        leads = sorted(selection)
        if not leads or leads[0] != 1:
            continue
        contiguous = 0
        for lead in leads:
            if lead != contiguous + 1:
                break
            contiguous = lead
        if contiguous < 24:
            continue
        parsed = parse_run_text(None if run_text == "local" else run_text)
        candidates.append((parsed or datetime.min.replace(tzinfo=timezone.utc), run_text, selection))
    if not candidates:
        inventories = [
            f"{run_text}: {len(selection)} échéance(s)"
            for run_text, selection in sorted(grouped.items())
        ]
        raise IncompleteRunError(
            "Catalogue MFWAM en cours de synchronisation : aucun run ne couvre "
            f"encore +01 h à +24 h sans trou (par run : {'; '.join(inventories) or 'aucune ressource'})"
        )
    _date, run_text, selection = max(candidates, key=lambda item: item[0])
    return selection, parse_run_text(None if run_text == "local" else run_text)


def wait_for_complete_remote_run(
    session: requests.Session,
    attempts: int,
    retry_seconds: int,
) -> tuple[dict[int, Resource], datetime | None] | None:
    last_error: IncompleteRunError | None = None
    for attempt in range(1, attempts + 1):
        discovered = api_resources(session)
        try:
            return choose_resources(discovered)
        except IncompleteRunError as exc:
            last_error = exc
            if attempt < attempts:
                LOGGER.warning(
                    "%s. Nouvelle vérification dans %s s (%s/%s).",
                    exc,
                    retry_seconds,
                    attempt,
                    attempts,
                )
                if retry_seconds:
                    time.sleep(retry_seconds)

    LOGGER.warning(
        "%s. Aucune donnée ne sera écrasée ; le prochain passage du workflow "
        "réessaiera automatiquement.",
        last_error,
    )
    return None


def already_published(url: str, run_time: datetime | None) -> bool:
    if not url or run_time is None:
        return False
    try:
        response = requests.get(url, timeout=(10, 30), headers={"User-Agent": USER_AGENT})
        if response.status_code != 200:
            return False
        payload = response.json()
        model = payload.get("model") or {}
        return (
            payload.get("status") == "ok"
            and model.get("run_time") == iso_utc(run_time)
            and model.get("pipeline_version") == PIPELINE_VERSION
        )
    except (requests.RequestException, ValueError, TypeError):
        return False


def download_resource(session: requests.Session, resource: Resource, destination: Path) -> None:
    if resource.local_path is not None:
        shutil.copy2(resource.local_path, destination)
        return
    if not resource.url:
        raise RuntimeError(f"Adresse de téléchargement absente : {resource.title}")
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with session.get(
                resource.url,
                stream=True,
                timeout=(20, 180),
                headers={"User-Agent": USER_AGENT},
            ) as response:
                response.raise_for_status()
                with destination.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=2 * 1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            if resource.size and destination.stat().st_size != resource.size:
                raise RuntimeError(
                    f"Taille inattendue pour {resource.title} : "
                    f"{destination.stat().st_size} au lieu de {resource.size}"
                )
            return
        except (requests.RequestException, OSError, RuntimeError) as error:
            last_error = error
            destination.unlink(missing_ok=True)
            if attempt < 3:
                LOGGER.warning("Téléchargement à retenter (%s/3) : %s", attempt, resource.title)
                time.sleep(2**attempt)
    raise RuntimeError(f"Téléchargement impossible : {resource.title}") from last_error


def mask_missing(values: np.ndarray, missing_value: Any) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    invalid = ~np.isfinite(result) | (np.abs(result) > 1.0e20)
    try:
        missing = float(missing_value)
    except (TypeError, ValueError):
        missing = math.nan
    if math.isfinite(missing):
        invalid |= np.isclose(result, missing, rtol=0.0, atol=1.0e-9)
    result[invalid] = np.nan
    return result


class GridGeometry:
    """Décrit la grille régulière lat/lon lue dans le premier message GRIB2."""

    def __init__(self, gid: int) -> None:
        self.ni = int(safe_get(gid, "Ni", 0))
        self.nj = int(safe_get(gid, "Nj", 0))
        self.lat_first = float(safe_get(gid, "latitudeOfFirstGridPointInDegrees", 0))
        lon_first = float(safe_get(gid, "longitudeOfFirstGridPointInDegrees", 0))
        self.lon_first = (lon_first + 180.0) % 360.0 - 180.0
        self.lat_last = float(safe_get(gid, "latitudeOfLastGridPointInDegrees", 0))
        self.j_increment = float(safe_get(gid, "jDirectionIncrementInDegrees", 0.025))
        self.i_increment = float(safe_get(gid, "iDirectionIncrementInDegrees", 0.025))
        # Signe de l'incrément en latitude : la grille MFWAM balaie
        # généralement du nord vers le sud (première ligne = latitude max).
        self.lat_step = -self.j_increment if self.lat_first > self.lat_last else self.j_increment
        if self.ni <= 1 or self.nj <= 1:
            raise RuntimeError("Grille MFWAM invalide (Ni/Nj)")

    def row_column(self, latitude: np.ndarray, longitude: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        row = (latitude - self.lat_first) / self.lat_step
        column = (longitude - self.lon_first) / self.i_increment
        return row, column


class MapSampler:
    """Rééchantillonne la grille régulière MFWAM sur la carte Web Mercator."""

    def __init__(self, width: int, height: int, bounds: dict[str, float]) -> None:
        self.width = int(width)
        self.height = int(height)
        target_latitudes = _inverse_mercator(
            np.linspace(
                _mercator(np.asarray(float(bounds["north"]))),
                _mercator(np.asarray(float(bounds["south"]))),
                self.height,
            )
        )
        target_longitudes = np.linspace(float(bounds["west"]), float(bounds["east"]), self.width)
        self._target_latitudes = target_latitudes
        self._target_longitudes = target_longitudes

    def bind(self, geometry: GridGeometry) -> None:
        rows, columns = geometry.row_column(
            self._target_latitudes[:, None], self._target_longitudes[None, :]
        )
        self.row_grid = np.broadcast_to(rows, (self.height, self.width))
        self.column_grid = np.broadcast_to(columns, (self.height, self.width))
        self.coverage = (
            (self.row_grid >= 0)
            & (self.row_grid <= geometry.nj - 1)
            & (self.column_grid >= 0)
            & (self.column_grid <= geometry.ni - 1)
        )
        self.geometry = geometry

    def extract(self, gid: int) -> np.ndarray:
        values = mask_missing(
            codes_get_double_array(gid, "values"), safe_get(gid, "missingValue")
        ).reshape(self.geometry.nj, self.geometry.ni)
        invalid = ~np.isfinite(values)

        # L'interpolation bilinéaire (order=1) mélange les valeurs NaN de la
        # terre dans les cellules de mer voisines : le masque terre/mer
        # obtenu directement à partir de cette interpolation « dilate » la
        # zone transparente d'environ une cellule native (2,7 km) au-delà du
        # vrai trait de côte, ce qui décale visiblement les couleurs par
        # rapport au tracé du littoral. On sépare donc deux échantillonnages :
        # les valeurs (comblées par plus proche voisin pour éviter toute
        # contamination NaN, puis interpolées en bilinéaire pour rester
        # lisses) et le masque de validité (échantillonné au plus proche
        # voisin, sans mélange, pour rester fidèle à la résolution native).
        if invalid.any() and not invalid.all():
            fill_indexes = distance_transform_edt(
                invalid, return_distances=False, return_indices=True
            )
            filled_values = values[tuple(fill_indexes)]
        else:
            filled_values = values

        sampled = map_coordinates(
            filled_values,
            [self.row_grid, self.column_grid],
            order=1,
            mode="constant",
            cval=np.nan,
            prefilter=False,
        ).astype(np.float32, copy=False)
        sampled_invalid = map_coordinates(
            invalid.astype(np.float32),
            [self.row_grid, self.column_grid],
            order=0,
            mode="constant",
            cval=1.0,
            prefilter=False,
        )
        sampled[sampled_invalid >= 0.5] = np.nan
        sampled[~self.coverage] = np.nan
        return sampled


def _mercator(latitude):
    radians = np.radians(np.clip(latitude, -85.0, 85.0))
    return np.log(np.tan(np.pi / 4.0 + radians / 2.0))


def _inverse_mercator(value):
    return np.degrees(2.0 * np.arctan(np.exp(value)) - np.pi / 2.0)


def parse_grib_file(
    path: Path,
    map_sampler: MapSampler,
    lead_hour: int,
) -> dict[str, Any]:
    map_values: dict[str, np.ndarray] = {}
    run_time: datetime | None = None
    valid_time: datetime | None = None
    observed_lead: int | None = None
    geometry: GridGeometry | None = None

    with path.open("rb") as handle:
        while True:
            gid = codes_grib_new_from_file(handle)
            if gid is None:
                break
            try:
                short_name = str(safe_get(gid, "shortName", "")).lower()
                field = FIELD_BY_SHORTNAME.get(short_name)
                if field is None:
                    parameter_key = (
                        int(safe_get(gid, "discipline", -1)),
                        int(safe_get(gid, "parameterCategory", -1)),
                        int(safe_get(gid, "parameterNumber", -1)),
                    )
                    field = FIELD_BY_LOCAL_PARAMETER.get(parameter_key)
                run_time = run_time or grib_datetime(gid, "dataDate", "dataTime")
                valid_time = valid_time or grib_datetime(gid, "validityDate", "validityTime")
                end_step = safe_get(gid, "endStep")
                if end_step is not None:
                    observed_lead = int(end_step)
                if field is None:
                    continue
                if geometry is None:
                    geometry = GridGeometry(gid)
                    map_sampler.bind(geometry)
                map_values[field] = map_sampler.extract(gid)
            finally:
                codes_release(gid)

    if "swh_m" not in map_values:
        raise RuntimeError(f"Hauteur significative absente de l'échéance +{lead_hour:03d} h")
    if observed_lead is not None and observed_lead != lead_hour:
        raise RuntimeError(
            f"Échéance GRIB incohérente : +{observed_lead} h au lieu de +{lead_hour} h"
        )
    if valid_time is None and run_time is not None:
        valid_time = run_time + timedelta(hours=lead_hour)
    if valid_time is None:
        raise RuntimeError(f"Date de validité absente à +{lead_hour:03d} h")
    return {
        "lead_hour": lead_hour,
        "run_time": run_time,
        "valid_time": valid_time,
        "map_values": map_values,
    }


def build_product(
    resources: dict[int, Resource],
    session: requests.Session,
    working_directory: Path,
    run_hint: datetime | None,
) -> Path:
    result_directory = working_directory / "result"
    downloads = working_directory / "downloads"
    result_directory.mkdir(parents=True)
    downloads.mkdir(parents=True)

    map_sampler = MapSampler(MAP_WIDTH, MAP_HEIGHT, DEFAULT_BOUNDS)
    map_renderer = WaveMapRenderer(
        result_directory / "maps",
        width=MAP_WIDTH,
        height=MAP_HEIGHT,
        bounds=DEFAULT_BOUNDS,
        boundary_directory=Path(__file__).resolve().parents[1] / "config" / "natural-earth",
    )

    model_run = run_hint
    source_bytes = 0
    leads = sorted(resources)

    for position, lead in enumerate(leads, start=1):
        resource = resources[lead]
        destination = downloads / f"SP1-{lead:03d}H.grib2"
        try:
            LOGGER.info(
                "Téléchargement +%03d h (%.1f Mo)", lead, (resource.size or 0) / 1e6
            )
            download_resource(session, resource, destination)
            source_bytes += destination.stat().st_size
            LOGGER.info("Décodage et cartes MFWAM %s/%s : +%03d h", position, len(leads), lead)
            step = parse_grib_file(destination, map_sampler, lead)
            model_run = model_run or step["run_time"]
            map_renderer.render_step(
                lead_hour=lead,
                valid_time=step["valid_time"],
                fields=step["map_values"],
            )
        finally:
            destination.unlink(missing_ok=True)

    generated_at = iso_utc(datetime.now(timezone.utc))
    assert generated_at is not None
    run_time = iso_utc(model_run)
    map_manifest = map_renderer.write_manifest(generated_at=generated_at, run_time=run_time)

    model = {
        "name": "MFWAM France 0,025°",
        "provider": "Météo-France",
        "dataset": "Paquets de modèle de vagues MFWAM résolution 0,025°",
        "domain": "FRANGP0025",
        "resolution_degrees": 0.025,
        "resolution_km": 2.5,
        "run_time": run_time,
        "pipeline_version": PIPELINE_VERSION,
        "source_url": DATASET_PAGE,
        "source_size_bytes": source_bytes,
        "license": "Licence Ouverte 2.0",
    }
    index = {
        "schema_version": 1,
        "status": "ok",
        "generated_at": generated_at,
        "model": model,
        "coverage": {"label": "Façade maritime française (53N 38N 8W 12E)"},
        "maps": {
            "status": "ok",
            "module_version": map_manifest["module_version"],
            "manifest": "maps/index.json",
            "layers": len(map_manifest["layers"]),
            "steps": len(map_manifest["steps"]),
        },
    }
    with (result_directory / "index.json").open("w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    LOGGER.info(
        "Produit MFWAM prêt : %s couches, %s échéances",
        len(map_manifest["layers"]),
        len(map_manifest["steps"]),
    )
    return result_directory


def safe_output_directory(path: Path) -> Path:
    resolved = path.resolve()
    forbidden = {Path("/").resolve(), Path.cwd().resolve(), Path.home().resolve()}
    if resolved in forbidden or len(resolved.parts) < 3:
        raise RuntimeError(f"Dossier de sortie dangereux : {resolved}")
    return resolved


def publish_result(source: Path, destination: Path) -> None:
    target = safe_output_directory(destination)
    temporary = target.with_name(target.name + ".new")
    if temporary.exists():
        shutil.rmtree(temporary)
    shutil.copytree(source, temporary)
    if target.exists():
        shutil.rmtree(target)
    temporary.replace(target)


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    if not 1 <= args.catalog_attempts <= 20:
        raise ValueError("catalog-attempts doit être compris entre 1 et 20")
    if not 0 <= args.catalog_retry_seconds <= 600:
        raise ValueError("catalog-retry-seconds doit être compris entre 0 et 600")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    if args.resource_directory:
        discovered = local_resources(Path(args.resource_directory))
        resources, run_hint = choose_resources(discovered)
    else:
        selection = wait_for_complete_remote_run(
            session, args.catalog_attempts, args.catalog_retry_seconds
        )
        if selection is None:
            return 0
        resources, run_hint = selection
    LOGGER.info("Run MFWAM sélectionné : %s (%s échéances)", iso_utc(run_hint) or "GRIB local", len(resources))
    if not args.force and not args.resource_directory and already_published(
        args.current_metadata_url, run_hint
    ):
        LOGGER.info("Ce run MFWAM est déjà publié ; aucune reconstruction nécessaire")
        return 0

    with tempfile.TemporaryDirectory(prefix="mfwam-france-build-") as temporary:
        result = build_product(resources, session, Path(temporary), run_hint)
        publish_result(result, Path(args.output_dir))
    LOGGER.info("Fichiers prêts dans %s", args.output_dir)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        LOGGER.exception("Échec de la mise à jour MFWAM France")
        raise SystemExit(1)
