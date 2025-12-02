# altitude_extraction

1) go to Google Earth, create your path

2) save it as a KML or KMZ file

3) Open QGIS, create a project from that file (drag and drop that file into the screen)

4) Repurpose coordinates to EPSG:2100 by saving as geopackage (not as kml)

4a) Toolbox -> Points to path, create a line layer

4b) Toolbox -> Explode lines (ie break up the line in segments)

4c) Toolbox -> Add geometry attributes (ie length) to the exploded lines

4d) Save what's produced as "lengths.csv"

4e) Make sure to add a "name" column somewhere with the tower names

4f) drop the csv here

5) Back to the original unexploded line layer from step 4a
    Toolbox -> add points along geometry (1m should be enough)

6) save the resulting layer as a KML with EPSG:4326  coordinates (this might actually be optional, but better be safe)

7) import that KML into Google Earth again.

8) Save a new instance of it after importing.

9) Take that final KML file, go to gpsvisualizer/elevation, get the txt.

10) rename that file to "data.txt," drop it here.

11) run "python main.py"