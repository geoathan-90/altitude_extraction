import pandas as pd
import ezdxf
from pathlib import Path

INPUT = Path("data.txt")  
OUTPUT = Path("mikotomi.dxf")
OUTPUT2 = Path("mikotomi.csv")

def load_xy(path:Path):
    df = pd.read_csv(path, sep="\t", engine="python")

    dist_col=None
    for c in df.columns:
        name = str(c).lower() 
        if "distance" in name:
            dist_col = c
            break

    alt_col=None
    for c in df.columns:
        name=str(c).lower()
        if "altitude" in name:
            alt_col = c
            break

    x = pd.to_numeric(df[dist_col], errors="coerce") * 1000.0       # meters
    y = pd.to_numeric(df[alt_col],  errors="coerce") * 10.0         # altitude×10

    clean = pd.DataFrame({"x": x, "y": y}).dropna()

    return list(zip(clean["x"].astype(float), clean["y"].astype(float))), clean


pts, mikotomi = load_xy(INPUT)

mikotomi.to_csv(OUTPUT2, index=False)

# ---- Build DXF ----
doc = ezdxf.new("R2013")
doc.header["$INSUNITS"] = 6  # meters
msp = doc.modelspace()

# Layers
if "profile_polyline" not in doc.layers:
    doc.layers.add("profile_polyline", color=7)
if "profile_spline" not in doc.layers:
    doc.layers.add("profile_spline", color=3)

# Polyline (straight segments)
msp.add_lwpolyline(pts, dxfattribs={"layer": "profile_polyline"})

# True spline (degree 3) using fit points - kinda useless
#msp.add_spline(fit_points=pts, degree=3, dxfattribs={"layer": "profile_spline"})

doc.saveas(OUTPUT)
print(f"Wrote {OUTPUT.resolve()}")
