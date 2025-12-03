import pandas as pd
import ezdxf
from pathlib import Path
from typing import List, Tuple


# --- paths ---
INPUT_PROFILE = Path("data.txt")       # longitudinal profile source
INPUT_LENGTHS = Path("lengths.csv")    # segment lengths + names
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

    # scale altitude to make the DXF nicer (same as before)
    clean["altitude_x10"] = clean[alt_col] * 10.0

    profile = clean[["distance_m", "altitude_x10"]].copy()
    profile = profile.sort_values("distance_m").reset_index(drop=True)
    return profile


# ---------------------------------------------------------
# 2. Load mark positions + names from lengths.csv
# ---------------------------------------------------------
def load_marks(path: Path) -> pd.DataFrame:
    """
    Reads lengths.csv and returns a DataFrame with:
      - station_m: cumulative station distances in meters
      - name: label for each station (from the last column)

    Assumptions:
      - 3rd column = segment length in meters (e.g. 60.19, 225, 310, ...)
      - last column = name (label) for that station
    """
    df = pd.read_csv(path)

    if df.shape[1] < 4:
        raise ValueError("lengths.csv must have at least 4 columns (including 'name').")

    length_col = df.columns[2]   # 3rd column: segment length in meters
    name_col = "name"    # last column: label

    segment_lengths = df[length_col].astype(float)
    stations_m = segment_lengths.cumsum()

    marks = pd.DataFrame(
        {
            "station_m": stations_m,
            "name": df[name_col].astype(str).fillna(""),
        }
    )

    return marks


# ---------------------------------------------------------
# 3. Altitude + mark geometry
# ---------------------------------------------------------
def get_altitude_at(profile: pd.DataFrame, station_m: float) -> float:
    """
    Return altitude_x10 at the point on the profile whose distance_m is
    closest to station_m.
    """
    diff = (profile["distance_m"] - station_m).abs()
    idx = diff.idxmin()
    return float(profile.loc[idx, "altitude_x10"])


def build_mark_geometry(
    profile: pd.DataFrame,
    marks: pd.DataFrame,
    tick_height: float | None = None,
) -> Tuple[List[Tuple[Tuple[float, float], Tuple[float, float]]], pd.DataFrame]:
    """
    For each mark, compute:
      - short vertical segment ((x1,y1),(x2,y2))
      - altitude_x10 at that x

    Returns:
      segments: list of ((x1,y1),(x2,y2))
      marks_with_alt: marks DataFrame with extra 'altitude_x10' and 'tick_height'
    """
    if tick_height is None:
        # 2% of total vertical range as a small mark
        v_range = profile["altitude_x10"].max() - profile["altitude_x10"].min()
        tick_height = 500 #v_range * 0.02 if v_range > 0 else 20.0

    half_h = tick_height / 2.0
    segments: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []

    altitudes = []
    for station_m in marks["station_m"]:
        y = get_altitude_at(profile, station_m)
        altitudes.append(y)
        segments.append(((station_m, y - half_h), (station_m, y + half_h)))

    marks_with_alt = marks.copy()
    marks_with_alt["altitude_x10"] = altitudes
    marks_with_alt["tick_height"] = tick_height

    return segments, marks_with_alt


# ---------------------------------------------------------
# 4. Build DXF: profile polyline + marks + labels
# ---------------------------------------------------------
def write_dxf(
    profile: pd.DataFrame,
    mark_segments: List[Tuple[Tuple[float, float], Tuple[float, float]]],
    marks_with_alt: pd.DataFrame,
    path: Path,
) -> None:
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Layers
    if "profile_polyline" not in doc.layers:
        doc.layers.add("profile_polyline", color=7)
    if "profile_marks" not in doc.layers:
        doc.layers.add("profile_marks", color=1)
    if "profile_mark_labels" not in doc.layers:
        doc.layers.add("profile_mark_labels", color=3)

    # Profile polyline (distance_m vs altitude_x10)
    pts = list(
        zip(
            profile["distance_m"].astype(float),
            profile["altitude_x10"].astype(float),
        )
    )
    msp.add_lwpolyline(pts, dxfattribs={"layer": "profile_polyline"})

    # Vertical marks
    for (x1, y1), (x2, y2) in mark_segments:
        msp.add_line((x1, y1), (x2, y2), dxfattribs={"layer": "profile_marks"})

    # Labels at each mark
    if not marks_with_alt.empty:
        v_range = profile["altitude_x10"].max() - profile["altitude_x10"].min()
        # Reasonable default text height relative to the profile size
        text_height = 20 #v_range * 0.015 if v_range > 0 else 20.0

        tick_height = float(marks_with_alt["tick_height"].iloc[0])

        for _, row in marks_with_alt.iterrows():
            x = float(row["station_m"])
            y = float(row["altitude_x10"])
            name = str(row["name"])

            # Place text slightly above the top of the tick
            text_y = y + tick_height * 0.7

            # Older ezdxf versions: just set the insert point directly
            msp.add_text(
                name,
                dxfattribs={
                    "layer": "profile_mark_labels",
                    "height": text_height,
                    "insert": (x, text_y),  # position of the text baseline
                },
            )

    doc.saveas(path)


# ---------------------------------------------------------
# 5. Main
# ---------------------------------------------------------
def main():
    # Load longitudinal section
    profile = load_profile(INPUT_PROFILE)
    profile.to_csv(OUTPUT_CSV, index=False)

    # Load stations + names from lengths.csv
    marks = load_marks(INPUT_LENGTHS)

    # Build short vertical marks at those stations
    mark_segments, marks_with_alt = build_mark_geometry(profile, marks)

    # Write DXF
    write_dxf(profile, mark_segments, marks_with_alt, OUTPUT_DXF)

    print(f"Wrote profile CSV -> {OUTPUT_CSV.resolve()}")
    print(f"Wrote DXF with marks + labels -> {OUTPUT_DXF.resolve()}")


if __name__ == "__main__":
    main()
