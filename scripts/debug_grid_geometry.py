#!/usr/bin/env python3
"""Diagnostic ponctuel : géométrie de grille exacte d'un message GRIB2 SP1."""
import sys
from eccodes import codes_get, codes_grib_new_from_file, codes_release

path = sys.argv[1]
keys = [
    "gridType", "Ni", "Nj",
    "latitudeOfFirstGridPointInDegrees", "longitudeOfFirstGridPointInDegrees",
    "latitudeOfLastGridPointInDegrees", "longitudeOfLastGridPointInDegrees",
    "jDirectionIncrementInDegrees", "iDirectionIncrementInDegrees",
    "iScansNegatively", "jScansPositively", "jPointsAreConsecutive",
    "scanningMode",
]
with open(path, "rb") as handle:
    gid = codes_grib_new_from_file(handle)
    short_name = codes_get(gid, "shortName")
    print("shortName:", short_name)
    for key in keys:
        try:
            print(f"{key}: {codes_get(gid, key)}")
        except Exception as exc:
            print(f"{key}: <erreur {exc}>")
    codes_release(gid)
