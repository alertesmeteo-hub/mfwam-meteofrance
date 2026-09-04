#!/usr/bin/env python3
"""Diagnostic ponctuel : liste tous les messages GRIB2 d'un fichier SP1 MFWAM."""
import sys
from eccodes import codes_get, codes_grib_new_from_file, codes_release

path = sys.argv[1]
with open(path, "rb") as handle:
    index = 0
    while True:
        gid = codes_grib_new_from_file(handle)
        if gid is None:
            break
        index += 1
        def g(key, default="?"):
            try:
                return codes_get(gid, key)
            except Exception:
                return default
        print(
            f"{index:3d} shortName={g('shortName')!r:12} name={g('name')!r} "
            f"discipline={g('discipline')} category={g('parameterCategory')} "
            f"number={g('parameterNumber')} typeOfLevel={g('typeOfLevel')} "
            f"level={g('level')}"
        )
        codes_release(gid)
