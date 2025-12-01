import pandas as pd
import ezdxf
from pathlib import Path

# --- paths ---
INPUT_PROFILE = Path("data.txt")       # longitudinal profile source
INPUT_LENGTHS = Path("lengths.csv")    # marks: we will use the 3rd column
OUTPUT_DXF = Path("mikotomi.dxf")
OUTPUT_CSV = Path("mikotomi.csv")


# ---------------------------------------------------------
# 1. Load longitudinal profile (distance + altitude)
# ---------------------------------------------------------
def load_profile(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t", engine="python")

    # Find the distance and altitude columns by name
    dist_col = next(c for c in df.columns if "distance" in str(c).lower())
    alt_col = next(c for c in df.columns if "altitude" in str(c).lower())

    clean = df[[dist_col, alt_col]].copy()
    clean = clean.dropna(subset=[dist_col, alt_col])

    # distance is in km -> convert to meters
    clean["distance_m"] = clean[dist_col] * 1000.0

    # scale altitude to make the DXF nicer (same as your previous logic)
    clean["altitude_x10"] = clean[alt_col] * 10.0

    profile = clean[["distance_m", "altitude_x10"]].copy()
    profile = profile.sort_values("distance_m").reset_index(drop=True)
    return profile


# ---------------------------------------------------------
# 2. Load mark positions from lengths.csv (3rd column)
# ---------------------------------------------------------
def load_mark_stations(path: Path) -> pd.Series:
    """
    Reads lengths.csv and returns a Series of *cumulative* station distances in meters.
    The 3rd column is interpreted as segment lengths (in meters), and we take cumsum.
    """
    df = pd.read_csv(path)

    if df.shape[1] < 3:
        raise ValueError("lengths.csv must have at least 3 columns.")

    length_col = df.columns[2]  # 3rd column: segment length in meters

    # Convert to float and build cumulative distances:
    # [60.19, 225.00, 310.00, ...]  ->  [60.19, 285.19, 595.19, ...]
    segment_lengths = df[length_col].astype(float)
    stations_m = segment_lengths.cumsum()
    stations_m.name = "station_m"
    return stations_m


# ---------------------------------------------------------
# 3. Find the altitude on the profile at each station
# ---------------------------------------------------------
def get_altitude_at(profile: pd.DataFrame, station_m: float) -> float:
    """
    Return altitude_x10 at the point on the profile whose distance_m is
    closest to station_m.
    """
    diff = (profile["distance_m"] - station_m).abs()
    idx = diff.idxmin()
    return float(profile.loc[idx, "altitude_x10"])


def build_mark_segments(
    profile: pd.DataFrame,
    stations_m: pd.Series,
    tick_height: float | None = None,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """
    Returns a list of segments [((x1,y1),(x2,y2)), ...] for short vertical
    marks centered on the profile line at each station.
    """
    if tick_height is None:
        # 2% of total vertical range as a small mark
        v_range = profile["altitude_x10"].max() - profile["altitude_x10"].min()
        tick_height = 250 #v_range * 0.02 if v_range > 0 else 20.0

    half_h = tick_height / 2.0
    segments = []

    for s in stations_m:
        y = get_altitude_at(profile, s)
        segments.append(((s, y - half_h), (s, y + half_h)))

    return segments


# ---------------------------------------------------------
# 4. Build DXF: profile polyline + marks
# ---------------------------------------------------------
def write_dxf(profile: pd.DataFrame,
              mark_segments: list[tuple[tuple[float, float], tuple[float, float]]],
              path: Path) -> None:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Layers
    if "profile_polyline" not in doc.layers:
        doc.layers.add("profile_polyline", color=7)
    if "profile_marks" not in doc.layers:
        doc.layers.add("profile_marks", color=1)

    # Profile polyline (distance_m vs altitude_x10)
    pts = list(
        zip(
            profile["distance_m"].astype(float),
            profile["altitude_x10"].astype(float),
        )
    )
    msp.add_lwpolyline(pts, dxfattribs={"layer": "profile_polyline"})

    # Vertical marks at stations from lengths.csv
    for (x1, y1), (x2, y2) in mark_segments:
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": "profile_marks"})

    doc.saveas(path)


# ---------------------------------------------------------
# 5. Main
# ---------------------------------------------------------
def main():
    # Load longitudinal section
    profile = load_profile(INPUT_PROFILE)
    profile.to_csv(OUTPUT_CSV, index=False)

    # Load stations from 3rd column of lengths.csv
    stations = load_mark_stations(INPUT_LENGTHS)

    # Build short vertical marks at those stations
    mark_segments = build_mark_segments(profile, stations)

    # Write DXF
    write_dxf(profile, mark_segments, OUTPUT_DXF)

    print(f"Wrote profile CSV -> {OUTPUT_CSV.resolve()}")
    print(f"Wrote DXF with marks -> {OUTPUT_DXF.resolve()}")


if __name__ == "__main__":
    main()
