# altitude_extraction

1) go to Google Earth, create your path

2) save it as a KML or KMZ file

3) Open QGIS, create a project from that file (drag and drop that file into the screen)

4) Repurpose coordinates to EPSG:2100 by saving as geopackage (not as kml)

5) Toolbox -> add points along geometry (1m should be enough)

6) save the resulting layer as a KML with EPSG:4236 (or whatever) coordinates

7) import that KML into Google Earth again.

8) Save a new instance of it after importing.

9) Take that final KML file, go to gpsvisualizer/elevation, get the txt.

10) rename that file to "data.txt," drop it here.

11) run "python main.py"