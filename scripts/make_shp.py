# -*- coding: utf-8 -*-
"""arcpy (Python 2.7) step: XY table -> shapefile in WGS84."""
import os
import sys
import arcpy

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else r"D:\Workspace\bjbus"
csv_path = os.path.join(HERE, "for_arcpy.csv")
out_dir = HERE
shp_name = "xueyuanlubeikou_60min.shp"

sr = arcpy.SpatialReference(4326)
arcpy.env.workspace = out_dir
arcpy.env.overwriteOutput = True

try:
    arcpy.Delete_management(os.path.join(out_dir, shp_name))
except Exception:
    pass

lyr = "reach_lyr"
arcpy.MakeXYEventLayer_management(csv_path, os.path.join(HERE, "for_arcpy.csv") and "LON", "LAT", lyr, sr)
print("layer count:", int(arcpy.GetCount_management(lyr).getOutput(0)))
arcpy.FeatureClassToFeatureClass_conversion(lyr, out_dir, shp_name)
full = os.path.join(out_dir, shp_name)
print("written:", full, int(arcpy.GetCount_management(full).getOutput(0)))
print("extent:", arcpy.Describe(full).extent.XMin, arcpy.Describe(full).extent.YMin,
      arcpy.Describe(full).extent.XMax, arcpy.Describe(full).extent.YMax)
print("spatial ref:", arcpy.Describe(full).spatialReference.name)
