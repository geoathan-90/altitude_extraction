"""
kml_to_profile.py

Goal: Replace most of the manual QGIS + gpsvisualizer steps in README.md.

Inputs
  - A KML or KMZ exported from Google Earth that contains a LineString route.

Outputs
  - data_from_kml.tsv : tab-delimited table with columns:
        distance_km    altitude_m
    (main.py will auto-detect "distance" + "altitude" headers)

  - lengths_from_kml.csv : segment lengths (meters) between the KML vertices:
        length
    Optional:
      If you provide a names file, we will also output:
        name

Notes
  - Elevation lookup uses SRTM tiles via the optional dependency `srtm.py`.
    Install it with: pip install srtm.py
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from pyproj import Geod


KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}
WGS84_GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float


def _read_text_from_kml_or_kmz(path: Path) -> str:
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path, "r") as zf:
            # Heuristic: take the first .kml entry.
            kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError("KMZ did not contain a .kml file.")
            with zf.open(kml_names[0], "r") as f:
                return f.read().decode("utf-8", errors="replace")
    return path.read_text(encoding="utf-8", errors="replace")


def read_linestring_vertices(path: Path) -> List[LatLon]:
    """
    Extract the first LineString coordinate sequence from a KML/KMZ file.

    KML coordinate order is: lon,lat[,alt]
    """
    xml_text = _read_text_from_kml_or_kmz(path)
    root = ET.fromstring(xml_text)

    # Find first LineString/coordinates in the document.
    coords_el = root.find(".//kml:LineString/kml:coordinates", KML_NS)
    if coords_el is None or not coords_el.text:
        # Fallback: try without namespaces (some exporters strip them).
        coords_el = root.find(".//LineString/coordinates")
    if coords_el is None or not coords_el.text:
        raise ValueError("Could not find a LineString/coordinates element in the KML/KMZ.")

    raw = coords_el.text.strip()
    vertices: List[LatLon] = []

    for token in raw.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        lon = float(parts[0])
        lat = float(parts[1])
        vertices.append(LatLon(lat=lat, lon=lon))

    if len(vertices) < 2:
        raise ValueError("LineString has fewer than 2 coordinate vertices.")

    return vertices


def segment_lengths_m(vertices: Sequence[LatLon]) -> List[float]:
    out: List[float] = []
    for a, b in zip(vertices[:-1], vertices[1:]):
        _, _, dist_m = WGS84_GEOD.inv(a.lon, a.lat, b.lon, b.lat)
        out.append(float(dist_m))
    return out


def densify_vertices(vertices: Sequence[LatLon], spacing_m: float) -> List[LatLon]:
    """
    Create a new vertex list with approximately `spacing_m` between consecutive points.
    Uses geodesic interpolation segment-by-segment.
    """
    if spacing_m <= 0:
        raise ValueError("spacing_m must be > 0")

    dense: List[LatLon] = [vertices[0]]

    for a, b in zip(vertices[:-1], vertices[1:]):
        az12, _, dist_m = WGS84_GEOD.inv(a.lon, a.lat, b.lon, b.lat)
        dist_m = float(dist_m)

        if dist_m <= spacing_m:
            dense.append(b)
            continue

        steps = int(dist_m // spacing_m)

        for i in range(1, steps + 1):
            d = min(i * spacing_m, dist_m)
            lon_i, lat_i, _ = WGS84_GEOD.fwd(a.lon, a.lat, az12, d)
            dense.append(LatLon(lat=float(lat_i), lon=float(lon_i)))

        # Ensure exact end vertex is present (avoid duplicates).
        if dense[-1] != b:
            dense.append(b)

    # De-dup consecutive identical points (rare but can happen with tiny segments).
    deduped: List[LatLon] = [dense[0]]
    for p in dense[1:]:
        if p.lat != deduped[-1].lat or p.lon != deduped[-1].lon:
            deduped.append(p)

    return deduped


def cumulative_distances_m(points: Sequence[LatLon]) -> List[float]:
    out: List[float] = [0.0]
    running = 0.0
    for a, b in zip(points[:-1], points[1:]):
        _, _, dist_m = WGS84_GEOD.inv(a.lon, a.lat, b.lon, b.lat)
        running += float(dist_m)
        out.append(running)
    return out


def load_names_file(path: Path) -> List[str]:
    """
    Accept either:
      - one name per line, OR
      - a CSV with a header that includes a 'name' column.
    """
    txt = path.read_text(encoding="utf-8", errors="replace").strip()
    if not txt:
        return []

    # Heuristic: if it looks like CSV with commas and a header 'name'
    first_line = txt.splitlines()[0]
    if "," in first_line and "name" in first_line.lower():
        reader = csv.DictReader(io.StringIO(txt))
        names = [str(row.get("name", "")).strip() for row in reader]
        return [n for n in names if n]

    # Otherwise: one name per line
    return [line.strip() for line in txt.splitlines() if line.strip()]


def try_get_elevations_m(points: Sequence[LatLon], cache_dir: Optional[Path]) -> List[Optional[float]]:
    """
    Returns a list of elevations in meters (same length as `points`).

    If `srtm.py` is not installed, we return None for all points and print instructions.
    """
    try:
        import srtm  # type: ignore
    except Exception:
        print(
            "WARNING: 'srtm.py' is not installed, so elevations cannot be computed offline.\n"
            "Install it with: pip install srtm.py\n"
            "Then re-run this script.\n",
            file=sys.stderr,
        )
        return [None for _ in points]

    kwargs = {}
    if cache_dir is not None:
        kwargs["local_cache_dir"] = str(cache_dir)

    elevation_data = srtm.get_data(**kwargs)

    out: List[Optional[float]] = []
    for p in points:
        elev = elevation_data.get_elevation(p.lat, p.lon)  # meters or None
        out.append(None if elev is None else float(elev))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kml", required=True, type=Path, help="Input KML or KMZ exported from Google Earth.")
    ap.add_argument("--spacing-m", type=float, default=1.0, help="Point spacing along the path in meters (default: 1m).")
    ap.add_argument("--out-profile", type=Path, default=Path("data_from_kml.tsv"))
    ap.add_argument("--out-lengths", type=Path, default=Path("lengths_from_kml.csv"))
    ap.add_argument("--names", type=Path, default=None, help="Optional names file (one per segment, or CSV with 'name').")
    ap.add_argument("--srtm-cache", type=Path, default=Path(".cache_srtm"), help="SRTM tile cache directory.")
    args = ap.parse_args()

    vertices = read_linestring_vertices(args.kml)

    seg_lengths = segment_lengths_m(vertices)

    names: List[str] = []
    if args.names is not None and args.names.exists():
        names = load_names_file(args.names)

    # Write lengths CSV
    with args.out_lengths.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if names and len(names) == len(seg_lengths):
            writer.writerow(["length", "name"])
            for L, n in zip(seg_lengths, names):
                writer.writerow([L, n])
        else:
            writer.writerow(["length"])
            for L in seg_lengths:
                writer.writerow([L])

    # Densify for elevation/profile
    dense_points = densify_vertices(vertices, spacing_m=args.spacing_m)
    dist_m = cumulative_distances_m(dense_points)
    elev_m = try_get_elevations_m(dense_points, cache_dir=args.srtm_cache)

    # Write profile TSV
    # main.py looks for any column containing "distance" and any containing "altitude"
    with args.out_profile.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["distance_km", "altitude_m", "lat", "lon"])
        for p, d, e in zip(dense_points, dist_m, elev_m):
            if e is None:
                # Keep row but mark altitude empty; main.py currently drops NaNs.
                writer.writerow([d / 1000.0, "", p.lat, p.lon])
            else:
                writer.writerow([d / 1000.0, e, p.lat, p.lon])

    print(f"Wrote profile TSV -> {args.out_profile.resolve()}")
    print(f"Wrote lengths CSV  -> {args.out_lengths.resolve()}")
    print("If altitude_m is blank, install srtm.py and rerun.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
