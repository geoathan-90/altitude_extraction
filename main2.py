import pandas as pd
import ezdxf
from pathlib import Path

"""
1. Read a longitudinal profile from data.txt
   (distance along the line and altitude at each point).

2. Read a list of segment lengths and names from lengths.csv.
    a.Build "stations" from the lengths read (cumulative distances).

3. For each station:
    a. find the altitude at that distance on the profile.
    b. build vertical mark
    c. annotate with station name.

4. Write out:
   - mikotomi.csv   
   - mikotomi.dxf   
"""

# --- paths (files next to this script) ---
INPUT_PROFILE = Path("data.txt")       # longitudinal profile source
INPUT_LENGTHS = Path("lengths.csv")    # segment lengths + names
OUTPUT_DXF = Path("mikotomi.dxf")
OUTPUT_CSV = Path("mikotomi.csv")


# ---------------------------------------------------------
# 1. Load longitudinal profile (distance + altitude)
# ---------------------------------------------------------
def load_profile(path):

    df = pd.read_csv(path, sep="\t", engine="python")

    dist_col = None
    alt_col = None

    for col in df.columns:
        col_lower = str(col).lower()

        if "distance" in col_lower and dist_col is None:
            dist_col = col

        if "altitude" in col_lower and alt_col is None:
            alt_col = col

    if dist_col is None or alt_col is None:
        raise ValueError("Could not find distance/altitude columns in profile file.")

    clean = df[[dist_col, alt_col]].copy()  # Keep only the distance and altitude columns.

    #optional?
    clean = clean.dropna(subset=[dist_col, alt_col]) # Drop rows where either distance or altitude is missing.
    
    clean["distance_m"] = clean[dist_col] * 1000.0 # Convert distance from kilometers to meters.

    clean["altitude_x10"] = clean[alt_col] * 10.0 # Multiply altitude by 10 for desired mikotomi scale

    # Keep only the new columns and sort them by distance (just in case it's all unsorted)
    profile = clean[["distance_m", "altitude_x10"]].copy()
    profile = profile.sort_values("distance_m").reset_index(drop=True)

    return profile


# ---------------------------------------------------------
# 2. Load mark positions + names from lengths.csv
# ---------------------------------------------------------
def load_marks(path):

    df = pd.read_csv(path)

    # Sanity check: we expect at least 4 columns, including "name".
    if df.shape[1] < 4:
        raise ValueError("lengths.csv must have at least 4 columns (including 'name').")

    # 3rd column (index 2) is the segment length.
    length_col = df.columns[2]
    name_col = "name"

    # --- Build station_m as a cumulative sum, using a simple loop ---
    segment_lengths = df[length_col].tolist()

    station_values = []   # will hold cumulative distances
    running_total = 0.0

    for value in segment_lengths:
        # Try to convert each length to float (just in case).
        try:
            length_m = float(value)
        except ValueError:
            # If conversion fails, treat it as 0.0
            length_m = 0.0

        running_total += length_m
        station_values.append(running_total)

    # --- Build the list of names, turning NaN into empty strings ---
    name_values = []
    for value in df[name_col]:
        if pd.isna(value):
            name_values.append("")
        else:
            name_values.append(str(value))

    # Create the marks DataFrame.
    marks = pd.DataFrame(
        {
            "station_m": station_values,
            "name": name_values,
        }
    )

    return marks


# ---------------------------------------------------------
# 3. Helper: find altitude at a given station
# ---------------------------------------------------------
def get_altitude_at(profile, station_m):
    """
    Return altitude_x10 at the point on the profile whose distance_m
    is closest to the given station_m.

    Implementation note:
    We do this with a simple loop over all rows, and keep track of the
    row whose distance is closest to station_m.
    """

    best_distance_diff = None
    best_altitude = None

    # profile.iterrows() loops over the rows of the DataFrame.
    for _, row in profile.iterrows():
        distance_here = float(row["distance_m"])
        altitude_here = float(row["altitude_x10"])

        # How far is this row from the station we care about?
        current_diff = abs(distance_here - station_m)

        # If this is the first row, or if the difference is smaller,
        # remember this row as the "best" one.
        if best_distance_diff is None or current_diff < best_distance_diff:
            best_distance_diff = current_diff
            best_altitude = altitude_here

    return best_altitude


# ---------------------------------------------------------
# 4. Build vertical tick geometry for each mark
# ---------------------------------------------------------
def build_mark_geometry(profile, marks, tick_height=None):
    """
    For each mark (station) we:
      - find the altitude at that station
      - create a short vertical line (a "tick") centered on that altitude

    Returns:
      - segments        : list of line segments, each as ((x1, y1), (x2, y2))
      - marks_with_alt  : a copy of marks with:
                            * altitude_x10 at each station
                            * tick_height (same for all)
    """

    # Decide how tall the ticks are.
    # We keep this simple and just use a fixed value if none is given.
    if tick_height is None:
        tick_height = 500.0  # adjust this if you want taller/shorter ticks

    half_height = tick_height / 2.0

    segments = []    # list of ((x1, y1), (x2, y2))
    altitudes = []   # altitude_x10 for each station

    # Loop over every station and build a tick.
    for station_m in marks["station_m"]:
        # Find altitude at this station.
        altitude_here = get_altitude_at(profile, station_m)
        altitudes.append(altitude_here)

        # Bottom and top of the vertical tick.
        y1 = altitude_here - half_height
        y2 = altitude_here + half_height

        # Store as a segment.
        segments.append(
            (
                (float(station_m), float(y1)),
                (float(station_m), float(y2)),
            )
        )

    # Create a copy of marks and store altitude + tick height.
    marks_with_alt = marks.copy()
    marks_with_alt["altitude_x10"] = altitudes
    marks_with_alt["tick_height"] = tick_height

    return segments, marks_with_alt


# ---------------------------------------------------------
# 5. Build DXF: profile polyline + marks + labels
# ---------------------------------------------------------
def write_dxf(profile, mark_segments, marks_with_alt, path):
    """
    Create a DXF file with:
      - a polyline for the whole profile
      - a vertical tick line at each station
      - a text label (name) near each tick
    """

    # Create a new DXF document (AutoCAD 2010 version).
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()  # modelspace is where we draw things

    # --- Make sure the layers exist ---
    if "profile_polyline" not in doc.layers:
        doc.layers.add("profile_polyline", color=7)   # white
    if "profile_marks" not in doc.layers:
        doc.layers.add("profile_marks", color=1)      # red
    if "profile_mark_labels" not in doc.layers:
        doc.layers.add("profile_mark_labels", color=3)  # green

    # --- Draw the profile polyline ---
    # Build the list of (x, y) points using a simple loop.
    points = []
    for _, row in profile.iterrows():
        x = float(row["distance_m"])
        y = float(row["altitude_x10"])
        points.append((x, y))

    # Add the polyline to the DXF.
    msp.add_lwpolyline(points, dxfattribs={"layer": "profile_polyline"})

    # --- Draw each vertical tick mark ---
    for segment in mark_segments:
        (x1, y1), (x2, y2) = segment
        msp.add_line(
            (float(x1), float(y1)),
            (float(x2), float(y2)),
            dxfattribs={"layer": "profile_marks"},
        )

    # --- Add text labels at each mark ---
    if not marks_with_alt.empty:
        # Fixed text height in drawing units.
        # Change this if text looks too big or too small.
        text_height = 20.0

        # Tick height is the same for all rows; take it from the first one.
        tick_height = float(marks_with_alt["tick_height"].iloc[0])

        # Loop over each station row and place text.
        for _, row in marks_with_alt.iterrows():
            x = float(row["station_m"])
            y = float(row["altitude_x10"])
            name = str(row["name"])

            # Place the text a bit above the top of the tick.
            text_y = y + tick_height * 0.7

            msp.add_text(
                name,
                dxfattribs={
                    "layer": "profile_mark_labels",
                    "height": text_height,
                    "insert": (x, text_y),  # position of the text baseline
                },
            )

    # Save the DXF file to disk.
    doc.saveas(str(path))


# ---------------------------------------------------------
# 6. Main function that ties everything together
# ---------------------------------------------------------
def main():
    # 1) Load the longitudinal profile from data.txt
    profile = load_profile(INPUT_PROFILE)

    # Also save it to a CSV so you can inspect it easily in Excel.
    profile.to_csv(OUTPUT_CSV, index=False)

    # 2) Load the stations and their names from lengths.csv
    marks = load_marks(INPUT_LENGTHS)

    # 3) Build the tick segments and add altitude to marks.
    mark_segments, marks_with_alt = build_mark_geometry(profile, marks)

    # 4) Write the DXF drawing.
    write_dxf(profile, mark_segments, marks_with_alt, OUTPUT_DXF)

    print(f"Wrote profile CSV -> {OUTPUT_CSV.resolve()}")
    print(f"Wrote DXF with marks + labels -> {OUTPUT_DXF.resolve()}")


# This makes sure main() runs only when you execute this file directly.
if __name__ == "__main__":
    main()
