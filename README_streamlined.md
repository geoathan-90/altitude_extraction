# altitude_extraction (streamlined workflow)

This is a proposed update to reduce switching between Google Earth, QGIS, and gpsvisualizer.

## Recommended workflow (Google Earth + Python only)

1) In Google Earth, draw your path as a LineString (the same as before).
   Export it as KML or KMZ.

2) In Codespaces, run the KML pre-processor:

   python kml_to_profile.py --kml your_path.kml --spacing-m 1

   Outputs:
     - data_from_kml.tsv
     - lengths_from_kml.csv

   Notes:
     - Elevations are looked up from SRTM tiles (offline after download/caching).
       Install the dependency once:
         pip install srtm.py

3) Run the DXF generator:

   python main_updated.py

   Notes:
     - If lengths_from_kml.csv has no "name" column, the marks will be numbered 1..N automatically.

## Alternative workflow (keep QGIS, but automate it)

If you still prefer the QGIS tools, consider running them via the QGIS Processing Executor (`qgis_process`)
instead of clicking in the GUI. QGIS supports running Processing algorithms from the command line in headless mode.

This may still be heavier to install/run in Codespaces and is less friendly for future deployment to Render,
so the Python-only workflow above is the preferred long-term direction.
