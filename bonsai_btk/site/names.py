# SPDX-FileCopyrightText: 2026 Andràs Marghescu and contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Names of everything the site tools create in a Blender file, in one place.

The tools find their objects again by these names, so they are part of the file format.
"""

# objects
ORIGIN = "BTK_Site_Origin"            # empty that carries the project origin transform
TERRAIN = "BTK_Terrain"
TERRAIN_IFC = "BTK_Terrain_IFC"
BASE_PLATE = "BTK_Base_Plate"
TABLE = "BTK_Table"
MODEL_CAMERA = "BTK_Model_Camera"
MODEL_TREES = "BTK_Model_Trees"
MODEL_TREES_POINTS = "BTK_Model_Trees_Points"
SUN = "BTK_Sun"
CAMERA_EYE = "BTK_Camera_Eye_Level"
CAMERA_AERIAL = "BTK_Camera_Aerial"
MEADOW_OBJECT = "BTK_Meadow"
TREE_CONE = "BTK_Model_Tree_Cone"
TREE_SHRUB = "BTK_Model_Tree_Shrub"
LAYER_PREFIX = "BTK_Layer_"           # contour layers, followed by the level, e.g. BTK_Layer_1350

# collections
COL_TERRAIN = "BTK_Site_Terrain"
COL_BOARD = "BTK_Site_Cardboard_Model"
COL_LAYERS = "BTK_Site_Contour_Layers"
COL_TREES = "BTK_Site_Model_Trees"
COL_TREE_ASSETS = "BTK_Site_Model_Tree_Assets"
COL_LIGHT = "BTK_Site_Light"
COL_CAMERAS = "BTK_Site_Cameras"
COL_MEADOW = "BTK_Site_Meadow"
COL_LOD2 = "BTK_Site_Surroundings_LoD2"
COL_BUILDINGS = "BTK_Site_Buildings"  # objects in here count as buildings
COL_SPECIES = "BTK_Site_Tree_Species"
COL_CONIFERS = "BTK_Site_Conifers"
COL_BROADLEAVES = "BTK_Site_Broadleaves"
COL_SHRUBS = "BTK_Site_Shrubs"
COL_SCATTER_ASSETS = "BTK_Site_Scatter_Assets"
COL_GRASS = "BTK_Site_Grass"
COL_STONES = "BTK_Site_Stones"

# materials, worlds, node groups
MAT_TERRAIN = "BTK_Terrain"
MAT_BOARD = "BTK_Cardboard"
MAT_TABLE = "BTK_Table"
MAT_MODEL_TREE = "BTK_Model_Tree"
MAT_TERRAIN_IFC = "BTK_Terrain_IFC"
MAT_LOD2_ROOF = "BTK_LoD2_Roof"
MAT_LOD2_WALL = "BTK_LoD2_Wall"
MAT_LOD2_GROUND = "BTK_LoD2_Ground"
WORLD_SKY = "BTK_Sky"
WORLD_MODEL = "BTK_Model_World"
NG_TREES = "BTK_Model_Trees"
NG_MEADOW = "BTK_Meadow"

# nodes looked up by name
NODE_ORTHO = "BTK_Orthophoto"
NODE_TERRAIN_COLOUR = "BTK_Terrain_Colour"
NODE_BOARD_COLOUR = "BTK_Cardboard_Colour"
NODE_ON_BOARD = "BTK_On_Cardboard"
NODE_NATURAL = "BTK_Natural"
NODE_BROADLEAF_SHARE = "BTK_Broadleaf_Share"
NODE_TERRAIN = "BTK_Terrain"
NODE_RADIUS = "BTK_Radius"
NODE_GRASS_DENSITY = "BTK_Grass_Density"
NODE_STONE_DENSITY = "BTK_Stone_Density"
NODE_SEED = "BTK_Seed"

# custom properties on the scene
SC_ORIGIN = "btk_site_origin"          # scene origin in map coordinates (E, N)
SC_EPSG = "btk_site_epsg"
SC_BOARD = "btk_site_cardboard"        # levels of the cardboard model
SC_TERRAIN_WORLD = "btk_site_terrain_world"
SC_IFC_TERRAIN = "btk_site_ifc_terrain"  # GlobalId of the terrain element

# custom properties on objects
OB_BUILDING = "btk_building"
OB_DZ_ACTIVE = "btk_dz_active"         # offset currently applied (m)
OB_LOD2 = "btk_lod2"
OB_LOD2_HIDDEN = "btk_lod2_hidden"

# custom properties on materials
MAT_ORTHO_IMAGE = "btk_ortho_image"    # orthophoto taken out of the image node while switched off

# point attributes
AT_HEIGHT = "height"
AT_DZ_BOARD = "dz_cardboard"
AT_EDGE = "edge"
AT_HIDDEN = "hidden"
AT_UNDER_BUILDING = "btk_under_building"   # on the terrain mesh: 1 under buildings
AT_ORTHO_COLOUR = "ortho_col"

# things the tools create, re-attached when the origin changes
CREATED_OBJECTS = (TERRAIN, BASE_PLATE, TABLE, MODEL_CAMERA, MODEL_TREES)
CREATED_COLLECTIONS = (COL_LAYERS, COL_LOD2)

DEFAULT_EPSG = 25832                   # used when the data carries no EPSG code
