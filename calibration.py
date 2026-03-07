# -*- coding: utf-8 -*-

# https://github.com/jessica-herrmann/vesselprint | Skylar-Scott Lab

# Last updated: 11.25.25

############################################################### Import: Dependencies ######################################################################

# Python libraries
import pandas as pd
import numpy as np
import os
import argparse
import matplotlib.pyplot as plt
import random
import matplotlib.cm as cm
from mpl_toolkits import mplot3d
import math
from prompt_toolkit.shortcuts.utils import print_container
import plotly.express as px
import plotly
import plotly.graph_objects as go
import time
import copy

# Initialize random number generator
random.seed(0)

###################################################################### Argument Parser ######################################################################

parser = argparse.ArgumentParser(description="Specify whether the print involves 2 inks (multimaterial) and whether to include tolerancing.")
parser.add_argument('--network_file', help='Path to .txt file containing network coordinates', type=str, required=True)
parser.add_argument('--inletoutlet_file', help='Path to .txt file containing inlet and outlet coordinates', type=str, required=True)
parser.add_argument('--multimaterial', help='Multimaterial? (1=yes, 0=no)', type=int, required=True)
parser.add_argument('--tolerance_flag', help='Include tolerance? (1=yes, 0=no)', type=float, required=True, default=0)
parser.add_argument('--tolerance', help='Specify amount of tolerance (0 is none)', type=float, required=False, default=0)
parser.add_argument('--nozzle_diameter', help='Outer diameter of nozzle (mm)', type=float, required=True)
parser.add_argument('--container_x', help='Dimensions of container in x (mm)', type=float, required=False, default=50)
parser.add_argument('--container_y', help='Dimensions of container in y (mm)', type=float, required=False, default=50)
parser.add_argument('--num_decimals', help='number of decimals places for rounding output values', type=int, required=True)
parser.add_argument('--speed_calc', help='Compute print speeds for changing radii? (1=yes, 0=no)', type=int, required=True)
parser.add_argument('--plots', help='Generate plots? (1=yes, 0=no)', type=int, required=True)
parser.add_argument('--downsample', help='Downsample network at end? (1=yes, 0=no)', type=int, required=True)
parser.add_argument('--downsample_factor', help='By what factor should xcavate downsample?', type=int, required=False, default=1)
parser.add_argument('--flow', help='volumetric flow rate of the ink (mm^3/s), experimentally determined', type=float, required=False, default = 0.1272265034574846)
parser.add_argument('--scale_factor', help='Factor by which to scale the network', type=float, required=False, default=1)
parser.add_argument('--top_padding', help='Amount of space to leave above network (mm)', type=float, required=False, default=0)
parser.add_argument('--dwell_start', help='Time to dwell at start of vessel segment (s)', type=float, required=False, default=0.08)
parser.add_argument('--dwell_end', help='Time to dwell at end of vessel segment (s)', type=float, required=False, default=0.08)
parser.add_argument('--container_height', help='Height of print container (mm)', type=float, required=True)
parser.add_argument('--resting_pressure', help='Extrusion pressure for non-active nozzle during multimaterial (psi)', type=float, required=False, default=0)
parser.add_argument('--active_pressure', help='Extrusion pressure for active nozzle during multimaterial (psi)', type=float, required=False, default=5)
parser.add_argument('--print_speed', help='Print speed (feed rate) for constant radii (mm/s)', type=float, required=False, default=1)
parser.add_argument('--jog_speed', help='Custom jog speed (mm/s)', type=float, required=False, default=5)
parser.add_argument('--jog_speed_lift', help='Custom +z jog speed for initial nozzle lift (mm/s)', type=float, required=False, default=0.25)
parser.add_argument('--initial_lift', help='Distance over which to use reduced jog speed when lifting nozzle (mm)', type=float, required=False, default=0.5)
parser.add_argument('--jog_translation', help='Jog speed for translating between nozzles in multimaterial (mm/s)', type=float, required=False, default=10)
# Offset variables (for multimaterial printing)
parser.add_argument('--offset_x', help='Distance between the printhead nozzles in x, i.e. x-offset (mm)', type=float, required=False, default=103)
parser.add_argument('--offset_y', help='Distance between the printhead nozzles in y, i.e. y-offset (mm)', type=float, required=False, default=0.5)
parser.add_argument('--front_nozzle', help='1 if venous nozzle (right printhead) is in front of arterial (left printhead), meaning it is physically closer to the user; 2 if behind', type=int, required=False, default=1)
parser.add_argument('--amount_up', help='Amount above container_height by which to raise nozzles in z-direction before translating between print passes or between active/inactive nozzles (mm)', type=float, required=True, default=10)
# Custom printer axes
parser.add_argument('--printhead_1', help='Name of the printhead holding the arterial ink', type=str, required=False, default='Aa')
parser.add_argument('--printhead_2', help='Name of the printhead holding the venous ink', type=str, required=False, default='Ab')
parser.add_argument('--axis_1', help='Name of the printer axis (z-axis) holding the arterial ink', type=str, required=False, default='A')
parser.add_argument('--axis_2', help='Name of the printer axis (z-axis) holding the venous ink', type=str, required=False, default='B')
# Custom nodal closure
parser.add_argument('--close_sm', help="Providing an additional gap closure file (single material)? 1 = Yes, 0 = No", type=int, required=False, default=0)
parser.add_argument('--close_mm', help="Providing an additional gap closure file (multimaterial)? 1 = Yes, 0 = No", type=int, required=False, default=0)
parser.add_argument('--num_overlap', help='Number of nodes by which to overlap segments (for gap closure)', type=int, required=False, default=0)
# Custom gcode files
parser.add_argument('--custom', help='Providing custom G-code? 1=Yes, 0=No', type=int, required=True)
# Positive Ink Displacement vs pressure-based custom printer
parser.add_argument('--printer_type', help='Type of custom printer? 1=Positive Ink Displacement-based, 0=Pressure-based', type=int, required=True, default=0)
# Positive Ink Displacement parameters
parser.add_argument('--positiveInk_start', help='Extrusion start value for positive ink displacement-based printing (mm)', type=float, required=False, default=0)
parser.add_argument('--positiveInk_end', help='Extrusion stop value (mm) for positive ink displacement-based printing (mm)', type=float, required=False, default=0)
parser.add_argument('--positiveInk_radii', help='Use vessel radii for extrusion calculations? 1 = Yes, 0 = No', type=int, required=False, default=0)
parser.add_argument('--positiveInk_diam', help='Vessel diameter (mm) for positive ink displacement-based printing (not using SimVascular radii)', type=float, required=False, default=1)
parser.add_argument('--positiveInk_syringe_diam', help='Syringe diameter (mm) for positive ink displacement-based printing', type=float, required=False, default=1)
parser.add_argument('--positiveInk_factor', help='Extrusion value multiplier for positive ink displacement-based printing', type=float, required=False, default=1)
# Multimaterial extrusion parameters
parser.add_argument('--positiveInk_start_arterial', help='Extrusion start value for arterial ink in positive ink displacement-based printing (mm)', type=float, required=False, default=0)
parser.add_argument('--positiveInk_start_venous', help='Extrusion start value for venous ink in positive ink displacement-based printing (mm)', type=float, required=False, default=0)
parser.add_argument('--positiveInk_end_arterial', help='Extrusion stop value for arterial ink in positive ink displacement-based printing (mm)', type=float, required=False, default=0)
parser.add_argument('--positiveInk_end_venous', help='Extrusion stop value for venous ink in positive ink displacement-based printing (mm)', type=float, required=False, default=0)

args = parser.parse_args()

multimaterial = args.multimaterial
tolerance = args.tolerance
tolerance_flag = args.tolerance_flag
nozzle_OD = args.nozzle_diameter
scaleFactor = args.scale_factor
topPadding = args.top_padding
numDecimalsOutput = args.num_decimals
flow = args.flow
speed_calc = args.speed_calc
plots = args.plots
container_x = args.container_x
container_y = args.container_y
downsample = args.downsample
downsample_factor = args.downsample_factor
dwell_start = args.dwell_start
dwell_end = args.dwell_end 
containerHeight = args.container_height
resting_pressure = args.resting_pressure
active_pressure = args.active_pressure
dist_between_printheads = args.offset_x
ydist_between_printheads = args.offset_y
amount_up = args.amount_up
printhead_1 = args.printhead_1
printhead_2 = args.printhead_2
printhead1_axis = args.axis_1
printhead2_axis = args.axis_2
num_overlap = args.num_overlap
close_var_SM = args.close_sm
close_var_MM = args.close_mm
custom_gcode = args.custom
print_speed = args.print_speed
printer_type = args.printer_type
#prevent_drying = args.prevent_drying

customJogSpeed = args.jog_speed
customZJogSpeed = args.jog_speed_lift
customPositiveInkStartValue = args.positiveInk_start
customPositiveInkStopValue = args.positiveInk_end
customPositiveInkLineDiameter = args.positiveInk_diam
customPositiveInkSyringeDiameter = args.positiveInk_syringe_diam
customPositiveInkFactor = args.positiveInk_factor
useRadiiPositiveInk = args.positiveInk_radii
initial_lift = args.initial_lift
customJogSpeedTranslation = args.jog_translation

customPositiveInkStartValueA = args.positiveInk_start_arterial
customPositiveInkStartValueV = args.positiveInk_start_venous
customPositiveInkStopValueA = args.positiveInk_end_arterial
customPositiveInkStopValueV = args.positiveInk_end_venous

gap_file_SM = "inputs/pass_to_extend_SM.txt"
deltas_file_SM = "inputs/deltas_to_extend_SM.txt"
gap_file_MM = "inputs/pass_to_extend_MM.txt"
deltas_file_MM = "inputs/deltas_to_extend_MM.txt"

gap_file_SM = "inputs/extension/pass_to_extend_SM.txt"
gap_file_MM = "inputs/extension/pass_to_extend_MM.txt"
deltas_file_SM = "inputs/extension/deltas_to_extend_SM.txt"
deltas_file_MM = "inputs/extension/deltas_to_extend_MM.txt"

headerCode = "inputs/custom/header_code.txt"
startExtrusionCode = "inputs/custom/start_extrusion_code.txt"
stopExtrusionCode = "inputs/custom/stop_extrusion_code.txt"

stopExtrusionCode_printhead2 = "inputs/custom/stop_extrusion_code_printhead2.txt"
stopExtrusionCode_printhead1 = "inputs/custom/stop_extrusion_code_printhead1.txt"
startExtrusionCode_printhead2 = "inputs/custom/start_extrusion_code_printhead2.txt"
startExtrusionCode_printhead1 = "inputs/custom/start_extrusion_code_printhead1.txt"
active_pressure_printhead1 = "inputs/custom/active_pressure_printhead1.txt"
active_pressure_printhead2 = "inputs/custom/active_pressure_printhead2.txt"
rest_pressure_printhead1 = "inputs/custom/rest_pressure_printhead1.txt"
rest_pressure_printhead2 = "inputs/custom/rest_pressure_printhead2.txt"


dwell_printhead1 = "inputs/custom/dwell_code.txt"
dwell_printhead2 = "inputs/custom/dwell_code.txt"


###################################################################### Preprocessing ######################################################################


# Network filename (within Google Drive)
filename = args.network_file

# Inlet/outlet filename (within Google Drive)
inlet_outlet = args.inletoutlet_file

# Conversion factor (converts SimVascular output, which is in cm, to mm)
convertFactor = 10.0000000000000000

# Remove blank lines and vessel labels from coordinates
coord_num_tracker = {}
counter = -1
with open(f'{filename}','r') as original, open('preprocessed.txt','w') as preprocessed:
    for line in original:
        if line.strip() and line.startswith('Vessel'):
          counter += 1
          coord_num_tracker[counter] = []
        if line.strip() and not line.startswith('Vessel'):
            preprocessed.write(line)
            coord_num_tracker[counter].append(1)

# Create array to store the number of coordinates per vessel
coord_num_dict = {}
for i in range(0, len(coord_num_tracker)):
  coord_num_dict[i] = sum(coord_num_tracker[i])

# Create .txt files for preprocessing the input .txt files
newfile = open('preprocessed.txt','r')

linecount = 0
with open(f'{inlet_outlet}','r') as inletoutlet:
  for line in inletoutlet:
    if line.startswith('inlet'):
      inlet_line_index = linecount
    if line.startswith('outlet'):
      outlet_line_index = linecount
    linecount += 1
with open(f'{inlet_outlet}','r') as inletoutlet:
  num_lines = len(inletoutlet.readlines())

# Generate separate .txt files for inlet and outlet coordinates
inlets = []
outlets = []
with open(f'{inlet_outlet}','r') as inletoutlet, open('inlets.txt','w') as inlet_file, open('outlets.txt','w') as outlet_file:
  content = inletoutlet.readlines()
  content = [item.rstrip() for item in content]
  for line in range(1,outlet_line_index):
    inlets.append(content[line])
    inlet_file.write(content[line])
  for line in range(outlet_line_index+1,num_lines):
    outlets.append(content[line])
    outlet_file.write(content[line]+'\n')
inlet_file.close()
outlet_file.close()

# Update filename for preprocessed network
filename = 'preprocessed.txt'

###################################################################### Import: Vascular Network ######################################################################

# Import coordinates from SimVascular
points = pd.read_csv(f'{filename}', header=None)

# Read the number of columns from input .txt file
numColumns = len(points.columns)

# Number of original vessels in SimVascular network
numVessels = len(coord_num_tracker)

# Nozzle radius
nozzle_radius = nozzle_OD / 2

# Establish column headers for parsing text files
if numColumns == 5:
  columnHeaders = ['x', 'y', 'z', 'radius','artven']
elif numColumns == 4:
  columnHeaders = ['x', 'y', 'z', 'radius']
else:
  columnHeaders = ['x', 'y', 'z']
columnHeaders_inletoutlet = ['x','y','z']

points.columns = columnHeaders

# Number of decimal places
firstPoint = str(abs(points.iloc[0][0]))
decimalIndex = firstPoint.find('.')
numDecimals = len(firstPoint[decimalIndex+1:])

# Convert to numpy array
points_array = points.to_numpy()

# Establish column
inlets = pd.read_csv('inlets.txt',header=None)
inlets.columns = columnHeaders_inletoutlet
inlets_array = inlets.to_numpy()
outlets = pd.read_csv('outlets.txt',header=None)
outlets.columns = columnHeaders_inletoutlet
outlets_array = outlets.to_numpy()

# Convert to mm
points_array = points_array * convertFactor
inlets_array = inlets_array * convertFactor
outlets_array = outlets_array * convertFactor

# Scale for print dimensions
points_array = points_array * scaleFactor
inlets_array = inlets_array * scaleFactor
outlets_array = outlets_array * scaleFactor

# Locate top of network
networkTop = max(points_array[:,2]) + topPadding

# Round coordinate values
for i in range(0, len(points_array)):
  i = int(i)
  for j in range(0, len(points_array[i])):
    points_array[i][j] = round(points_array[i][j], numDecimals)
for i in range(0, len(inlets_array)):
  i = int(i)
  for j in range(0, len(inlets_array[i])):
    inlets_array[i][j] = round(inlets_array[i][j], numDecimals)
for i in range(0, len(outlets_array)):
  i = int(i)
  for j in range(0, len(outlets_array[i])):
    outlets_array[i][j] = round(outlets_array[i][j], numDecimals)

# Locate nodal indices of inlets/outlets (pre-interpolation)
inlet_nodes = []
outlet_nodes = []
# inlets
for inlet in range(0,len(inlets_array)):
  for point in range(0,len(points_array)):
    if (inlets_array[inlet][0] == points_array[point][0]):
      if (inlets_array[inlet][1] == points_array[point][1]):
        if (inlets_array[inlet][2] == points_array[point][2]):
          inlet_nodes.append(point)
# outlets
for outlet in range(0,len(outlets_array)):
  for point in range(0,len(points_array)):
    if (outlets_array[outlet][0] == points_array[point][0]):
      if (outlets_array[outlet][1] == points_array[point][1]):
        if (outlets_array[outlet][2] == points_array[point][2]):
          outlet_nodes.append(point)

# Console output
print('\nImported network. Now plotting original network.')

####################################################### Plotting Original Network #######################################################

# Animated plot of original network 
if plots == 1:

  x = {}
  y = {}
  z = {}

  for i in range(0,len(coord_num_dict)):
    x[i] = []
    y[i] = []
    z[i] = []
    if i == 0:
      num_before = 0
      for j in range(0, coord_num_dict[i]):
        x[i].append(points_array[j][0])
        y[i].append(points_array[j][1])
        z[i].append(points_array[j][2])
    elif i == len(coord_num_dict)-1:
      for j in range(num_before, len(points_array)):
        x[i].append(points_array[j][0])
        y[i].append(points_array[j][1])
        z[i].append(points_array[j][2])    
    else:
      for j in range(num_before, num_before+coord_num_dict[i]):
        x[i].append(points_array[j][0])
        y[i].append(points_array[j][1])
        z[i].append(points_array[j][2])
    num_before = num_before + coord_num_dict[i]

  fig = go.Figure()
  fig = go.Figure(layout_title_text = 'Original Network')
  config = dict({'scrollZoom': True})
  for i in x:
    fig.add_trace(go.Scatter3d(x=x[i], y=y[i], z=z[i]))
    fig.update_traces(marker_size = 2)
    fig.update_layout(title_x=0.5)

  # Create and add slider
  steps = []
  for i in range(len(fig.data)):
      step = dict(
          method="update",
          args=[{"visible": [False] * len(fig.data)},
                {"title": "Single Material <br>[Print Pass: " + str(i) + "]"}],  
      )
      for j in range(0,i+1):
        step["args"][0]["visible"][j] = True
      steps.append(step)
  sliders = [dict(
      currentvalue={"prefix": "Print pass: "},
      steps=steps
  )]
  fig.update_layout(
      sliders=sliders,
      margin=dict(l=30, r=30, t=30, b=30),
    title_x=0.5
  )

  fig.update_scenes(aspectmode='cube')

  # Store output graphs
  fig.write_html(f'outputs/network_original.html') 

# Console output
print('\nPlotted original network. Now interpolating.')

####################################################### Interpolation #######################################################

# Find start points of original vessels
vessel_start_original_nodenum = []
num_prev = 0
for i in range(numVessels):
  start_index = 0 + num_prev
  num_prev = num_prev + coord_num_dict[i]
  end_index = num_prev - 1
  vessel_start_original_nodenum.append(start_index)
vessel_start_original_coord = []
for i in vessel_start_original_nodenum:
  vessel_start_original_coord.append(points_array[i])

count = 0
for i in vessel_start_original_coord:
  for j in points_array:
    if np.array_equal(i, j):
      count += 1

##### Interpolation #####

# Add column to points_array to flag the vessel start points
last_column = np.zeros(len(points_array))
last_column = np.reshape(last_column, (len(last_column),1))
points_array = np.append(points_array, last_column, axis=1)
vessel_start_original_nodenum = []
num_prev = 0
for i in range(numVessels):
  start_index = 0 + num_prev
  num_prev = num_prev + coord_num_dict[i]
  end_index = num_prev - 1
  vessel_start_original_nodenum.append(start_index)
vessel_start_original_coord = []
for i in vessel_start_original_nodenum:
  vessel_start_original_coord.append(points_array[i])

# Flag the start of a new vessel with the arbitrary number "500"
for i in range(0, len(vessel_start_original_nodenum)):
  points_array[vessel_start_original_nodenum[i]][-1] = 500

# Create a copy of points_array
points_array_interp = np.copy(points_array)

# Interpolate
i = -1
while i < points_array_interp.shape[0]-2:
  i += 1
  x1 = points_array_interp[i][0]
  y1 = points_array_interp[i][1]
  z1 = points_array_interp[i][2]
  x2 = points_array_interp[i+1][0]
  y2 = points_array_interp[i+1][1]
  z2 = points_array_interp[i+1][2]
  dist = np.sqrt((x1 - x2)**2 + (y1 - y2)**2 + (z1 - z2)**2)
  deltax = x2 - x1
  deltay = y2 - y1
  deltaz = z2 - z1
  # Avoid comparing current point to next point if next point is start of a new vessel
  if points_array_interp[i+1][-1] == 500:
    continue
  # If the distance between the points is greater than the nozzle radius, interpolate until it isn't
  if dist > (nozzle_radius):
    scale = np.ceil(dist/nozzle_radius)
    incrementx = deltax/scale
    incrementy = deltay/scale
    incrementz = deltaz/scale
    j = 0
    # Insert new points
    for j in range(1, int(scale)):
      newpointx = x1+incrementx*j
      newpointy = y1+incrementy*j
      newpointz = z1+incrementz*j
      # If no radii or vessel types (arterial vs. venous) provided
      if numColumns == 3:
        points_array_interp = np.insert(points_array_interp, i+j, np.array([newpointx, newpointy, newpointz, 400]),axis=0) # 400 is a placeholder
      # If radii (but not vessel type) provided
      if numColumns == 4:
        rad = points_array_interp[i][3]
        points_array_interp = np.insert(points_array_interp, i+j, np.array([newpointx, newpointy, newpointz]+[rad]+[400]),axis=0) # 400 is a placeholder
      # If radii and vessel types provided
      if numColumns == 5:
        rad = points_array_interp[i][3]
        artven_type = points_array_interp[i][4]
        points_array_interp = np.insert(points_array_interp, i+j, np.array([newpointx, newpointy, newpointz]+[rad]+[artven_type]+[400]),axis=0) # 400 is a placeholder
    i += j

# Print the number of new points added
print(f'\n{len(points_array_interp) - len(points_array)} points added during interpolation; network now contains {len(points_array_interp)} points.')

# Output
print('\nNetwork interpolated. Now generating graph.')

####################################################### Generating Graph #######################################################

# Store the original network, pre-interpolation
points_array_original = np.copy(points_array)
inlet_nodes_original = np.copy(inlet_nodes)
outlet_nodes_original = np.copy(outlet_nodes)

# Update points_array to the interpolated version
points_array = []
points_array = np.copy(points_array_interp)

# Store the start points of the vessels, post-interpolation 
vessel_start_interp_coord = []
vessel_start_interp_nodenum = []
for i in range(0,len(points_array)):
  if points_array[i][-1] == 500:
    vessel_start_interp_nodenum.append(i)
    vessel_start_interp_coord.append(points_array[i])
vessel_start_interp_coord = np.array(vessel_start_interp_coord)

coord_num_dict_interp = {}
for i in range(0, len(vessel_start_interp_nodenum)):
  coord_num_dict_interp[i] = []
  if i == len(vessel_start_interp_nodenum)-1:
    coord_num_dict_interp[i] = len(points_array_interp) - vessel_start_interp_nodenum[i]
  else:
    coord_num_dict_interp[i] = vessel_start_interp_nodenum[i+1] - vessel_start_interp_nodenum[i]

##### Compiling Endpoints, "True" Endpoints, and Branchpoints #####

# Find endpoints, post-interpolation
endpoints = []
endpoint_nodes = []
end_index = 0 # initializing
num_prev = 0 # initializing
num_prev_array = [] # store for use in finding branchpoints below
nodes_by_vessel = {} # list of nodal identities by vessel
for i in range(numVessels):
  start_index = 0 + num_prev
  num_prev_array.append(num_prev)
  num_prev = num_prev + coord_num_dict_interp[i]
  end_index = num_prev - 1
  point1 = start_index
  point2 = end_index
  endpoint1 = points_array[point1]
  endpoints.append(endpoint1)
  endpoint_nodes.append(point1)
  endpoint2 = points_array[point2]
  endpoints.append(endpoint2)
  endpoint_nodes.append(point2)
  # Store nodal identity by print pass
  nodes_by_vessel[i] = list(np.arange(start_index, end_index+1, 1))

# Locate nodal indices of inlets/outlets (post-interpolation)
inlet_nodes_interp = []
outlet_nodes_interp = []
# inlets
for inlet in range(0,len(inlets_array)):
  for point in range(0,len(points_array)):
    if (inlets_array[inlet][0] == points_array[point][0]):
      if (inlets_array[inlet][1] == points_array[point][1]):
        if (inlets_array[inlet][2] == points_array[point][2]):
          inlet_nodes_interp.append(point)
# outlets
for outlet in range(0,len(outlets_array)):
  for point in range(0,len(points_array)):
    if (outlets_array[outlet][0] == points_array[point][0]):
      if (outlets_array[outlet][1] == points_array[point][1]):
        if (outlets_array[outlet][2] == points_array[point][2]):
          outlet_nodes_interp.append(point)

# print(f'inlet_nodes: {inlet_nodes_original}')
# print(f'outlet_nodes: {outlet_nodes_original}')
# print(f'inlet_nodes_interp: {inlet_nodes_interp}')
# print(f'outlet_nodes_interp: {outlet_nodes_interp}')

# Update inlet and outlet nodes to post-interpolation nodes
inlet_nodes = []
inlet_nodes = inlet_nodes_interp
outlet_nodes = []
outlet_nodes = outlet_nodes_interp

# Arbitrary placeholder value (used later in code)
last_vessel = list(nodes_by_vessel)[-1]
arbitrary_val = nodes_by_vessel[last_vessel][-1] + 100

# Find branchpoints
all_dist = []
branch_array = []
lowest_indices = []
branch_dict = {}
counter = 0
for i in range(numVessels):
  # Compiling endpoint indices to check
  endpoint1_index = counter
  endpoint2_index = counter + 1
  counter += 2
  points_before = []
  points_after = []
  points_all = []
  points_to_check = []
  endpoints_to_check = []
  # To check "before"
  if endpoint1_index != 0: # if there are segments before (i.e. not the first segment)
    points_before = list(np.arange(0, num_prev_array[i], 1))
  # To check "after"
  if endpoint2_index != (numVessels*2)+1: # if there are segments after (i.e. not the last segment)
    if i != numVessels-1:
      points_after = list(np.arange(num_prev_array[i+1], len(points_array), 1))
    else:
      points_after = []
  # Compile indices
  points_to_check = points_before + points_after
  endpoints_to_check = [endpoint1_index, endpoint2_index]
  # Check points
  for j in range(0,len(endpoints_to_check)):
    endpoint = endpoint_nodes[endpoints_to_check[j]]
    branch_dict[endpoint] = []
    col1 = []
    col2 = []
    col3 = []
    for k in points_to_check:
      x1 = points_array[endpoint,0]
      y1 = points_array[endpoint,1]
      z1 = points_array[endpoint,2]
      x2 = points_array[k,0]
      y2 = points_array[k,1]
      z2 = points_array[k,2]
      dist = np.sqrt((x1 - x2)**2 + (y1 - y2)**2 + (z1 - z2)**2)
      col1.append(endpoint)
      col2.append(k)
      col3.append(dist)
    lowest_index = col2[np.argsort(col3)[0]]
    second_lowest_index = col2[np.argsort(col3)[1]]
    branch_dict[endpoint].append(lowest_index)
    branch_dict[endpoint].append(second_lowest_index)
    lowest_indices.append(lowest_index)
    lowest_indices.append(second_lowest_index)
    # Handle any artifacts from SimVascular sampling rate
    if abs(lowest_index - second_lowest_index) != 1: # if daughters are non-consecutive integers
      # Mark whichever daughter it is closest to, of the pair, as one of the two "true" daughters:
      true_daughter1 = min(lowest_index, second_lowest_index)
      # Find second "true" daughter, which will be consecutive integer of first "true" daughter:
      check1 = lowest_index - 1
      check2 = lowest_index + 1
      check_array = [check1, check2]
      dist_array = []
      for check_node in check_array:
        x2 = points_array[check_node, 0]
        y2 = points_array[check_node, 1]
        z2 = points_array[check_node, 2]
        dist = np.sqrt((x1 - x2)**2 + (y1 - y2)**2 + (z1 - z2)**2)
        dist_array.append(dist)
      true_daughter2 = check_array[np.argsort(dist_array)[0]]
      # Update parent branchpoint dictionary
      branch_dict[endpoint] = []
      branch_dict[endpoint] = [true_daughter1, true_daughter2]

# Identify endpoints that are "true endpoints" (from inlet/outlet list, not geographically)
to_pop = inlet_nodes + outlet_nodes

# Remove "true" endpoints from branchpoints
for i in to_pop:
  branch_dict.pop(i)

# Confirm that daughters are part of same vessel
updated_branch_dict = {}
for i in branch_dict:
  parent = i
  if abs(branch_dict[i][0]-branch_dict[i][1]) != 1:
      # Daughters
      daughter1 = branch_dict[i][0]
      daughter2 = branch_dict[i][1]
      # Find the pass (vessel) to which each daughter belongs
      for i in range(0, len(nodes_by_vessel)):
        for j in nodes_by_vessel[i]:
          if j == daughter1:
            daughter1_pass = i
          elif j == daughter2:
            daughter2_pass = i
          else:
            continue
      # Daughter 1 possible pairing:
      daughter1_array = []
      for j in nodes_by_vessel[daughter1_pass]:
        x1 = points_array[j,0]
        y1 = points_array[j,1]
        z1 = points_array[j,2]
        x2 = points_array[parent,0]
        y2 = points_array[parent,1]
        z2 = points_array[parent,2]
        dist = np.sqrt((x1 - x2)**2 + (y1 - y2)**2 + (z1 - z2)**2)  
        daughter1_array.append(dist)
      # print(f'nodes_by_vessel[daughter1_pass] is {nodes_by_vessel[daughter1_pass]}')
      d1_sorted_indices = np.argpartition(daughter1_array, (0,2))
      d1_index1 = d1_sorted_indices[0]
      d1_index2 = d1_sorted_indices[1]
      # print(f'd1_index1: {d1_index1}, d1_index2: {d1_index2}')
      d1_node1 = nodes_by_vessel[daughter1_pass][d1_index1]
      d1_node2 = nodes_by_vessel[daughter1_pass][d1_index2]
      # Daughter 2 possible pairing:
      daughter2_array = []
      for j in nodes_by_vessel[daughter2_pass]:
        x1 = points_array[j,0]
        y1 = points_array[j,1]
        z1 = points_array[j,2]
        x2 = points_array[parent,0]
        y2 = points_array[parent,1]
        z2 = points_array[parent,2]
        dist = np.sqrt((x1 - x2)**2 + (y1 - y2)**2 + (z1 - z2)**2)  
        daughter2_array.append(dist)
      # print(f'nodes_by_vessel[daughter2_pass] is {nodes_by_vessel[daughter2_pass]}')
      d2_sorted_indices = np.argpartition(daughter2_array, (0,2))
      d2_index1 = d2_sorted_indices[0]
      d2_index2 = d2_sorted_indices[1]
      # print(f'd2_index1: {d2_index1}, d2_index2: {d2_index2}')
      d2_node1 = nodes_by_vessel[daughter2_pass][d2_index1]
      d2_node2 = nodes_by_vessel[daughter2_pass][d2_index2]
      # Compute the two lines of the two possible pairings
      check_x = points_array[parent,0]
      check_y = points_array[parent,1]
      check_z = points_array[parent,2]
      d1_x1 = points_array[d1_node1,0]
      d1_y1 = points_array[d1_node1,1]
      d1_z1 = points_array[d1_node1,2]
      d1_x2 = points_array[d1_node2,0]
      d1_y2 = points_array[d1_node2,1]
      d1_z2 = points_array[d1_node2,2]
      d2_x1 = points_array[d2_node1,0]
      d2_y1 = points_array[d2_node1,1]
      d2_z1 = points_array[d2_node1,2]
      d2_x2 = points_array[d2_node2,0]
      d2_y2 = points_array[d2_node2,1]
      d2_z2 = points_array[d2_node2,2]
      # Compute line 1 (line between d1_node1 and d1_node2)
      line1_x = round(((check_x - d1_x1)/(d1_x2-d1_x1)),5)
      line1_y = round(((check_y - d1_y1)/(d1_y2-d1_y1)),5)
      line1_z = round(((check_z - d1_z1)/(d1_z2-d1_z1)),5)
      # Compute line 2 (line between d2_node1 and d2_node2)
      line2_x = round(((check_x - d2_x1)/(d2_x2-d2_x1)),5)
      line2_y = round(((check_y - d2_y1)/(d2_y2-d2_y1)),5)
      line2_z = round(((check_z - d2_z1)/(d2_z2-d2_z1)),5)
      # Check whether parent branchpoint is on line 1; if so, select this daughter pairing
      if (line1_x == line1_y == line1_z).all():
        # Update the branchpoint dictionary
        branch_dict[parent] = []
        branch_dict[parent].append(d1_node1)
        branch_dict[parent].append(d1_node2)
      # Check whether parent branchpoint is on line 2; if so, select this daughter pairing
      if (line2_x == line2_y == line2_z).all():
        # Update the branchpoint dictionary
        branch_dict[parent] = []
        branch_dict[parent].append(d2_node1)
        branch_dict[parent].append(d2_node2)


# Print to console as dictionary ("key: [values]" where key=branchpoint and values=neighbors of that branchpoint)
# print('Updated branchpoint dictionary:')
# print(branch_dict)

# Compile list of final branchpoints
branchpoint_list = []
for i in branch_dict:
  branchpoint_list.append(branch_dict[i])
branchpoint_list = sum(branchpoint_list, [])
branchpoint_list_keys = list(branch_dict.keys())

branchpoint_daughter_dict = {}
for i in branch_dict:
  for j in branch_dict[i]:
    branchpoint_daughter_dict[j] = []
    branchpoint_daughter_dict[j] = i

with open('special_nodes.txt', 'w') as f:

  # print('\n')
  # print('Keys (branchpoint neighbors):')
  # print(branchpoint_list)

  f.write('Daughter nodes:')
  f.write(str(branchpoint_list))

  # print('\n')
  # print('\nBranchpoint nodes:')
  # print(branchpoint_list_keys)

  f.write('\n\nParent branchpoints:')
  f.write(str(branchpoint_list_keys))

  # print('\n')
  # print('List of endpoints (nodes):')
  # print(endpoint_nodes)

  f.write('\n\nEndpoint nodes:')
  f.write(str(endpoint_nodes))

  # print('\n')
  # print('Inlet node(s):')
  # print(inlet_nodes)

  f.write('\n\nInlet nodes:')
  f.write(str(inlet_nodes))

  # print('\n')
  # print('Outlet node(s):')
  # print(outlet_nodes)

  f.write('\n\nOutlet nodes:')
  f.write(str(outlet_nodes))

  # print('\n')
  # print('Branchpoint daughter dictionary:')
  # print(branchpoint_daughter_dict)
  # print('\n')

  f.write('\n\nBranchpoint daughter dictionary:')
  f.write(str(branchpoint_daughter_dict))

  # Check whether any daughters belong to more than one parent branchpoint 
  repeat_daughters = []
  for i in branchpoint_list:
    count = 0
    for j in range(0,len(branchpoint_list)):
      if branchpoint_list[j] == i:
        count += 1
    if count > 1:
      repeat_daughters.append(i)
  repeat_daughters = set(repeat_daughters)
  if len(repeat_daughters) == 0:
    # print('\n No daughter nodes belong to >1 parent branchpoint.\n')
    f.write('\n\nNo daughter nodes belong to >1 parent branchpoint.\n')
  else:
    # print('Daughter nodes with >1 parent branchpoint: \n')
    # print(repeat_daughters)
    f.write('\n\nDaughter nodes with >1 parent branchpoint (xcavate will limit to one daughter): \n')
    f.write(str(repeat_daughters))

f.close()

##### Represent as Graph #####

graph = {}
for i in range(points_array.shape[0]):
  graph[i] = []
  # Handle endpoints
  for j in range(points_array.shape[0]):
    # If node (i) is an endpoint, its neighbors should not also be endpoints
    if (j == (i-1)) or (j == (i+1)):
      # Check that j and i are not both endpoints (in which case, they shouldn't be considered neighbors, UNLESS there are only 2 points in the vessel)
      if i in endpoint_nodes and j in endpoint_nodes:
        # Check length of node's vessel to see if it is 2
        for vessel in range(0, len(nodes_by_vessel)):
          if (i in nodes_by_vessel[vessel]) and len(nodes_by_vessel[vessel]) == 2:
              graph[i].append(j)
        # If length is not 2
        else:
          continue
      # Otherwise
      graph[i].append(j)
  # Check for parent branchpoints
  if i in branch_dict:
    for k in branch_dict[i]:
      graph[i].append(k)
  # Check for daughter branchpoints
  if i in branchpoint_daughter_dict:
    if i not in repeat_daughters:
      parent = branchpoint_daughter_dict[i]
      graph[i].append(parent)
    elif i in repeat_daughters:
      for m_parent in branch_dict:
        for n_daughter in branch_dict[m_parent]:
          if n_daughter == i:
            graph[i].append(m_parent)
  # Include node as its own neighbor
  graph[i].append(i)
  # Sort
  graph[i] = sorted(graph[i])

# Connect daughter branchpoints to parent branchpoints only (not to other daughter in pair)
for i in graph:
  # If the node is a daughter
  if i in branchpoint_daughter_dict:
    parent = branchpoint_daughter_dict[i]
    daughters = branch_dict[parent]
    # For each daughter in the daughter-pair pertaining to parent
    for j in daughters:
      # Remove the second daughter from the list of neighbors of first daughter (in graph)
      if j != i:
        daughter_to_remove = j
        graph[i].remove(daughter_to_remove)

# Handle repeated daughters
for daughter in repeat_daughters:
  neighbors_of_daughter = graph[daughter]
  checking_values = []
  for neighbor in neighbors_of_daughter:
    x_check = points_array[neighbor,0]
    y_check = points_array[neighbor,1]
    z_check = points_array[neighbor,2]
    x = points_array[daughter, 0]
    y = points_array[daughter, 1]
    z = points_array[daughter, 2]
    dist = np.sqrt((x-x_check)**2 + (y-y_check)**2 + (z-z_check)**2)
    checking_values.append(dist)
  maximum = max(checking_values)
  index = checking_values.index(maximum)
  node_to_remove = neighbors_of_daughter[index]
  graph[daughter].remove(node_to_remove)

##### Comment back in to see graph (adjacency structure) #####


with open('graph.txt', 'w') as f:
  f.write('Graph edges:\n\n')
  for i in range(0,len(graph)):
    f.write(str(f'{i}: {graph[i]}'))
    f.write('\n')
f.close()

# Console output
print('\nGraph generated. Now generating initial print passes.')

###################################################################### Function: Validity ######################################################################

# Key function: label a point as valid (i.e. does not permanently block the printing of other points) or invalid

def is_valid(node, point, point_set):
    # Current point to check
    x0,y0,z0 = point[0],point[1],point[2]
    # Check against all other points
    othernode_num = -1
    for otherpoint in point_set:
        othernode_num += 1
        # Collect point
        x1,y1,z1 = otherpoint[0],otherpoint[1],otherpoint[2]  
        # Check
        if ((y1 - y0)**2 + (x1 - x0)**2) < (nozzle_radius**2):
          if z1 - z0 < 0:
            if (tolerance_flag == 1) and ((y1 - y0)**2 + (x1 - x0)**2 + (z1-z0)**2) < (tolerance**2):
              continue
            else:
              return False
          else:
            continue
        else:
          continue  
    return True

################################################################# Function: Find Lowest Unvisited #################################################################

# This function finds the lowest unvisited node within the network
def find_lowest_unvisited(unvisited,points_array):
    # Start at beginning of points_array (this is an index, not a value)
    lowest_node = list(unvisited)[0] 
    # Only check the unvisited nodes within points_array
    for i in list(unvisited): 
        # z-coordinate to check
        z = points_array[i,2]
        if z < points_array[lowest_node,2]:
            # Update index
            lowest_node = i 
    return lowest_node


######################################## Main part of algorithm: modified DFS to traverse network, subject to validity ########################################

# Set to keep track of visited nodes of graph
visited = set() 
not_visited = set(graph.keys())

# DFS
def dfs(visited, graph, node, pass_list):
    if node not in visited:
        if is_valid(node, points_array[node],points_array[list(not_visited)]):
            visited.add(node)
            not_visited.remove(node)
            pass_list.append(node)
            for neighbor in graph[node]:
                dfs(visited, graph, neighbor, pass_list)

print_passes = {}
print_passes_info = {}
i = 0

for iteration in range(1):
    #print(f'Iteration {iteration+1}')
    while len(not_visited) > 0:
        pass_list = []
        lowest_node = find_lowest_unvisited(not_visited, points_array)
        dfs(visited, graph, lowest_node, pass_list)
        print_passes[i] = pass_list

        i += 1

##### Initial print passes (pre-subdivision) #####
with open('changelog.txt', 'w') as f:
  # print('\nInitial print passes (post-DFS):')
  f.write('Initial print passes (post-DFS):\n\n')
  for i in print_passes:
    #print(f'Pass {i} | {print_passes[i]}')
    #print('\n')
    f.write(str(f'Pass {i} \n{print_passes[i]}'))
    f.write('\n\n')
f.close()

# Output
print(f'\nInitial passes generated. Now subdividing passes.')

###################################################################### Processing: Subdivision ######################################################################

# Note: because of the way DFS works (it can backtrack), might have instances in which successive nodes in a print pass are not neighbors. The following code, 
# after this section, handles this to eliminate backtracking.

# Find break points (places to further segment, because they involve large nozzle translations due to backtracking of DFS)

# Find break points
break_points = {}
for i in print_passes:
  counter = 0
  breaks = []
  for j in print_passes[i]:
    if counter < len(print_passes[i])-1:
      next_node = print_passes[i][counter + 1]
      if next_node not in graph[j]:
        breaks.append(next_node)
      counter += 1
    break_points[i] = breaks

# Divide into new passes
new_matrix = {}
for i in break_points:
  # If not empty
  if break_points[i]:
    new_passes = {}
    start = 0
    counter = -1
    check = 0
    for j in break_points[i]:
      total = len(break_points[i])
      # Track 
      counter += 1
      check += 1
      # Update "end" index
      end = print_passes[i].index(j)
      # Store nodes in new_pass
      new_passes[counter] = print_passes[i][start:end]
      # Update "start" index
      start = end
      if check == total:
        end = len(print_passes[i])
        new_passes[check] = print_passes[i][start:end]
    new_matrix[i] = new_passes

# Number of new passes to add
num_new = 0
for i in new_matrix:
  num_new = len(new_matrix[i]) + num_new
num_new = num_new - len(new_matrix)
num_total = len(print_passes) + num_new

# Store the processed (subdivided) print passes
counter = 0
counter_old = 0
counter_new = 0
print_passes_processed ={}
while counter < num_total:
  if counter_old in new_matrix:
    # Initialize
    num_to_add = 0
    while num_to_add < len(new_matrix[counter_old]):
      print_passes_processed[counter] = new_matrix[counter_old][num_to_add]
      counter += 1
      num_to_add += 1
    counter_old += 1
  else:
    print_passes_processed[counter] = print_passes[counter_old]
    counter += 1
    counter_old += 1

# Ensure that the subdivided segments begin with the lowest node in that segment:
for i in print_passes_processed:
  first_node = print_passes_processed[i][0]
  last_node = print_passes_processed[i][-1]
  if points_array[first_node][2] > points_array[last_node][2]:
    print_passes_processed[i].reverse()

##### Comment back in to see break points #####
# print('Breakpoints:')
# print(break_points)

##### Comment back in to see updated print passes (post-subdivision) #####
# print('\nSubdivided passes (dictionary):')
# print(new_matrix)
# print('\n---------------------')
# print('\nUpdated print passes:')
# print('\n---------------------')

# Print subdivided print passes, a.k.a. "processed print passes" (prior to closing any gaps)
print('\nSubdivision completed.')

with open('changelog.txt', 'a') as f:
  f.write('######################################################################')
  f.write('\n\nSubdivided print passes:\n\n')
  for i in print_passes_processed:
    f.write(str(f'Print pass {i} \n{print_passes_processed[i]}'))
    f.write('\n\n')
f.close()

# Print data about print passes
numpoints_in_subdivided_passes = []
for i in print_passes_processed:
  numpoints_in_subdivided_passes.append(len(print_passes_processed[i]))
avg_in_subdivided_passes = sum(numpoints_in_subdivided_passes) / len(print_passes_processed)
# print(f'\nAverage number of nodes per pass: {avg_in_subdivided_passes}')
# print(f'Maximum number of nodes per pass: {max(numpoints_in_subdivided_passes)}')
# print(f'Minimum number of nodes per pass: {min(numpoints_in_subdivided_passes)}')


###################################################################### Changelog 0 ######################################################################

# This cell of code checks for POTENTIALLY disconnected endpoints (i.e. 
# endpoints which only occur once as an endpoint, meaning that no other endpoint
# joins to them) and creates a CHANGELOG of ACTUALLY disconnected points.

# Create list of all endpoints of print_passes_processed
processed_endpoints = []
single_node_in_pass = []
for i in print_passes_processed:
  # If only one coordinate in the pass, only add once
  if len(print_passes_processed[i])==1:
    processed_endpoints.append(print_passes_processed[i][0])
    single_node_in_pass.append(print_passes_processed[i][0])
  else:
    processed_endpoints.append(print_passes_processed[i][0])
    processed_endpoints.append(print_passes_processed[i][-1])

# print('Endpoints of print_passes_processed:')
# print(processed_endpoints)

# print(f'\nSingle node in pass:')
# print(f'{single_node_in_pass}')

pass_counter = 0
disconnected = []
for i in processed_endpoints:
  pass_counter += 1 
  if processed_endpoints.count(i) == 1:
    disconnected.append(i)

with open('changelog.txt', 'a') as f:
  f.write(f'\nPotentially disconnected: {disconnected}\n\n')
f.close()

# Exclude inlets/outlets and endpoints of original vessels
to_remove = []
for i in disconnected:
  # Exclude endpoints of original vessels (includes inlets/outlets), UNLESS that endpoint is the only node in its pass
  if (i in endpoint_nodes) and (i not in single_node_in_pass):
    to_remove.append(i)
for i in to_remove:
  disconnected.remove(i)

# Initialize
potential_disconnect = {}
for i in disconnected:
  potential_disconnect[i] = []

# Checking the potentially disconnected endpoints for connection to other parts 
# of the print_passes (e.g., a node within a previous pass may join to where the
# endpoint of a different pass begins; these are not truly disconnected endpoints)
true_disconnected = []
true_disconnected_pass = {}
for i in print_passes_processed:
  for potentially_disconnected_node in disconnected:
    disconnect_count = 0 # reset for iteration
    if potentially_disconnected_node in print_passes_processed[i]:
      # Check against other print passes
      for m in range(0,len(print_passes_processed)):
        if potentially_disconnected_node in print_passes_processed[m]:
          potential_disconnect[potentially_disconnected_node].append(m)

# Remove duplicates
for i in potential_disconnect:
  potential_disconnect[i] = [*set(potential_disconnect[i])]

# print('\nPotential disconnects (format "NODE: [PRINT_PASS OF NODE]"):')
# print(potential_disconnect)

# Find true disconnects (endpoint only appears once, within its own vessel)
final_true_disconnect = {}
for i in potential_disconnect:
  if len(potential_disconnect[i]) == 1:
    final_true_disconnect[i] = potential_disconnect[i]

# print('\nFinal true disconnected nodes (format "NODE: [PRINT_PASS OF NODE]")')
# print(final_true_disconnect)

# Locate neighbors of disconnected nodes in the network
neighbor_locs = {}
neighbor_nodes = {}
neighbor_index = {}
neighbor_to_connect = {}
for i in final_true_disconnect:
  neighbor_nodes = graph[i]
  neighbor_locs[i] = []
  neighbor_index[i] = []
  neighbor_to_connect[i] = []

  # for each neighbor (j) of the disconnected node (i)
  for j in neighbor_nodes:
    # if the neighbor is not the disconnected node itself
    if j != i:
      # within each print_pass
      for passNum in print_passes_processed:
        # get the pass of the disconnected node (i)
        pass_of_disconnected_node = final_true_disconnect[i][0]

        # [1] if neighbor (j) in DIFF print_pass as node (i)
        if j in print_passes_processed[passNum] and passNum!=pass_of_disconnected_node: #: i.e., if currently in pass of the neighbor (j) and that pass is different from pass of disconnected node (i); i.e. have found the non-self print_pass containing neighbor 
          # store pass number of the non-self neighbor (j)
          neighbor_locs[i].append(passNum)
          # store index of the neighbor (j) within its own print_pass
          neighbor_index[i].append(print_passes_processed[passNum].index(j))
          # store the nodal identity of neighbor j
          neighbor_to_connect[i].append(j)

        # [2] if neighbor (j) in SAME print_pass as node (i)  
        if j in print_passes_processed[passNum] and passNum==pass_of_disconnected_node:
          # index of disconnected node (i) in its pass
          index = print_passes_processed[passNum].index(i)

          # [2A] if disconnected node (i) is LAST node of its pass
          if index==len(print_passes_processed[passNum])-1:
            # get node to "left" of disconnected node (i) in its pass (ie second-to-last node)
            node_left = print_passes_processed[passNum][(index-1)]
            # only connect neighbor (j) if not already connected to node (i) (ie if not already next to each other in the print_pass)
            if node_left != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)

          # [2B] if disconnected node (i) is FIRST node of its pass
          if index == 0:
            # get node to "right" of disconnected node (i) in its pass (ie second node)
            node_right = print_passes_processed[pass_of_disconnected_node][(index+1)]
            # only connect neighbor (j) if not already connected to node (i)
            if node_right != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)            


# Last processing step to ensure only true disconnects remain
to_pop_disconnects = {}
for i in neighbor_locs:
  # Pass of potentially disconnected node
  passnumber = final_true_disconnect[i][0]
  # Index of potentially disconnected node in its pass
  indexnumber = print_passes_processed[passnumber].index(i)
  # If only one node in pass
  if (len(print_passes_processed[passnumber]) == 1):
    continue
  # If first node
  if (indexnumber == 0) and (len(print_passes_processed[passnumber]) > 0): # is 0 here for checking not empty e.g. []
    rightindex = indexnumber+1
    # If not actually disconnected
    if print_passes_processed[passnumber][rightindex] == neighbor_to_connect[i][0]:
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)
  # If last node
  if (indexnumber+1 == len(print_passes_processed[passnumber])) and (len(print_passes_processed[passnumber]) > 0):  # is 0 here for checking not empty e.g. []
    leftindex = indexnumber-1
    # If not actually disconnected
    if print_passes_processed[passnumber][leftindex] == neighbor_to_connect[i][0]:
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)

# Check for any instances in which the first and last node of the same print 
# pass get reciprocally joined to each other, and make it so that only the last 
# node gets joined to the first (not the first to the last)

still_check = {}
tracker = 0
for i in final_true_disconnect:
  pass_to_check = final_true_disconnect[i][0]
  # if the print_pass of the disconnected node is the same as the print_pass of its neighbor (the node to which it joins)
  if final_true_disconnect[i] == neighbor_locs[i]:
    # if first node of pass (only two nodes will be checked for a given print pass - the first and last)
    if (tracker % 2 == 0):
      # save a list of these nodes, sorted by print pass
      still_check[pass_to_check] = []
      still_check[pass_to_check].append(i)      
      # update tracker
      tracker = len(still_check[pass_to_check])
    # if last node of pass (only two nodes will be checked for a given print pass - the first and last)
    elif (tracker % 2 == 1): # don't need to initialize
      still_check[pass_to_check].append(i)    
      tracker == 0
      # update tracker
      tracker = len(still_check[pass_to_check])

for i in (still_check):
  # if two nodes to connect in same print pass
  if len(still_check[i]) == 2:
    node = still_check[i][0]
    next_node = still_check[i][1]
    # if graphical neighbors
    if next_node in graph[node]:
      if neighbor_to_connect[node][0] == next_node:
        # if node is first node of pass and next_node is last node of pass
        if (node == print_passes_processed[i][0]) and (next_node == print_passes_processed[i][-1]):
          with open('changelog.txt', 'a') as f:
            f.write(f'for print pass {i}, not going to append {next_node} to {node} at start of pass because {node} will get appended to last node {next_node}.')
            f.write('\n')
          f.close()
          to_pop_disconnects[node] = []
          to_pop_disconnects[node].append(node)

# Remove any connected nodes from list of disconnects
for i in to_pop_disconnects:
  final_true_disconnect.pop(i)
  neighbor_locs.pop(i)
  neighbor_to_connect.pop(i)
  neighbor_index.pop(i)


# Print summary table of remaining disconnected nodes
with open('changelog.txt', 'a') as f:
  f.write('\n')
  f.write('Summary of remaining disconnects:                         Join to:')
  f.write('\n-----------------------------------------------------     --------------------')
  for i in neighbor_locs:
    f.write(f'\nNode {i} is in pass {final_true_disconnect[i][0]} and disconnected from pass {neighbor_locs[i][0]}.        {neighbor_to_connect[i][0]} at index {neighbor_index[i][0]}')
  f.write('\n-----------------------------------------------------     --------------------')
  f.write('\n\nNumber of disconnects: ')
  f.write(str(len(final_true_disconnect)))
  f.write('\n\n################################################################################')
f.close()

# Output
print('\n')
print('Now running Condition 0.\n')
with open('changelog.txt','a') as f:
  f.write('\n\nNow running Condition 0.\n')
f.close()

################################################## Post-Processing: CONDITION #0 (Gaps Within Existing Vessels) ##################################################

# CONDITION 0: Find and fix gaps within existing vessels (excluding endpoints and parent branchpoints)

# In this code block: for a given print_pass, starting with the second print_pass, 
# check whether the node numerically left or right of the first node (i.e. 
# first node - 1 or first node + 1) or last node occurs within a previous 
# print_pass. If so, and if these two nodes are 1) part of the same original vessel, 
# and 2) actual neighbors in the graph, append the neighbor to the start of the 
# current print_pass. 

# Note: these sections specifically check the first/last nodes of each print_pass, 
# because gaps appear only at these nodes (i.e., between discrete print_passes).

# This code distinguishes between "graphical neighbors" (the neighbors in the
# graph) and "numerical neighbors" (neighbors in the ordered list of nodes, i.e.
# node +/- 1, which may or may not be graphical neighbors)

# Initialize
start_append = {}
end_append = {}

# Beginning with second print_pass, iterate through all print_passes (i)
for i in range(1,len(print_passes_processed)):

  # [1] Check FIRST node of current print_pass (i)
  first_node = print_passes_processed[i][0]
  # Subtract 1 from first node of current print_pass (numerical neighbor)
  left_of_first = first_node - 1
  # Add 1 to first node of current print_pass (numerical neighbor)
  right_of_first = first_node + 1
  # Check whether the two numerical neighbors are graphical neighbors of first node of current print_pass
  if left_of_first not in graph[first_node]:
    # If not neighbor, update to arbitrary placeholder number
    left_of_first = arbitrary_val
  if right_of_first not in graph[first_node]:
    # If not neighbor, update to arbitrary placeholder number
    right_of_first = arbitrary_val

  # [2] Check LAST node of current print_pass (i)
  last_node = print_passes_processed[i][-1]
  # Subtract 1 from last node of current print_pass (numerical neighbor)
  left_of_last = last_node - 1
  # Add 1 to last node of current print_pass (numerical neighbor)
  right_of_last = last_node + 1
  # Check whether the two numerical neighbors are graphical neighbors of last node of current print_pass
  if left_of_last not in graph[last_node]:
    # If not neighbor, update to arbitrary placeholder number
    left_of_last = arbitrary_val
  if right_of_last not in graph[last_node]:
    # If not neighbor, update to arbitrary placeholder number
    right_of_last = arbitrary_val

  # [3] Identify instances of only ONE NODE in the current print_pass
  if first_node == last_node:
    flag = 1
  else:
    flag = 0
  
  # Print output
  # print(f'Pass {i} | first node: {first_node}, left: {left_of_first}, right: {right_of_first} ')
  # print(f'Pass {i} | last node: {last_node}, left: {left_of_last}, right: {right_of_last} ')

  # Iterate through previous print_passes (j) up to current print_pass (i)
  for j in range(0,i):
    # For each node (k) in the previous print_pass (j)
    for k in print_passes_processed[j]:
      # Reset for start of iteration
      already_added_to_single = 0 

      # [1] Handle FIRST_NODE | branchpoint_list_keys = parent branchpoint | branchpoint_list = daughters
      if (k == left_of_first or k == right_of_first) and (first_node not in branchpoint_list_keys) and (first_node not in endpoint_nodes):
        # [1A] if node (k) of previous print_pass (j) is a DAUGHTER node (branchpoint_list) of any parent branchpoint
        if k in branchpoint_list:
          # find daughter partner of node (k), step 1
          list_index = int(branchpoint_list.index(k))
          list_index = int(np.trunc(list_index/2))
          # find parent branchpoint of the daughter pair (node (k) and its partner)
          associated_branch = list(branch_dict)[list_index]
          # find daughter partner of (k), step 2
          pair = branch_dict[associated_branch]
          partner = [point for point in pair if point != k][0]
          # print(f'Branchpoint is {k} associated with branch {associated_branch}; its partner is {partner}')
          # Handle appropriate ordering of the daughter (k)
          if partner == first_node:
            with open('changelog.txt', 'a') as f:
              #f.write(f'\nBefore branch: NOT appending {k} to start of {i}, immediately preceding {first_node}, because order is {k} <--> {associated_branch} <--> {partner}')
              f.write('')
            f.close()
          else:
            start_append[i] = []
            start_append[i].append(k)
            with open('changelog.txt', 'a') as f:
              #f.write(f'\nAppending {k} to start of {i}, immediately preceding {first_node}, because order is {k} <--> {associated_branch} <--> {partner}')
              f.write('')
            f.close()
            # If only one node in the current print_pass (i)
            if flag == 1:
              already_added_to_single = 1
            # If >1 node in the current print_pass (i)
            else:
              already_added_to_single = 0
        # [1B] if node (k) is NOT a daughter node
        else:
          start_append[i] = []
          start_append[i].append(k)
          with open('changelog.txt', 'a') as f:
            #f.write(f'\nAppending {k} to start of {i}, immediately preceding {first_node}')
            f.write('')
          f.close()
          if flag == 1:
            already_added_to_single = 1
          else:
            already_added_to_single = 0

      # [2] Handle LAST_NODE | branchpoint_list_keys = parent branchpoint | branchpoint_list = daughters
      if (k == left_of_last or k == right_of_last) and (last_node not in branchpoint_list_keys) and (last_node not in endpoint_nodes):
        # [2A] node (k) of previous print_pass (j) is a DAUGHTER node (branchpoint_list) of any parent branchpoint
        if k in branchpoint_list:
          # find daughter partner of node (k), step 1
          list_index = int(branchpoint_list.index(k))
          list_index = int(np.trunc(list_index/2))
          # find parent branchpoint of the daughter pair (node (k) and its partner)
          associated_branch = list(branch_dict)[list_index]
          # find daughter partner of node (k), step 2
          pair = branch_dict[associated_branch]
          partner = [point for point in pair if point != k][0]
          # print(f'Branchpoint is {k} associated with branch {associated_branch}; its partner is {partner}')
          # Handle appropriate ordering of the daughter (k)
          if partner == last_node:
            with open('changelog.txt', 'a') as f:
              #f.write(f'\nBefore branch: NOT appending {k} to end of {i}, immediately following {last_node}, because order is {k} <--> {associated_branch} <--> {partner}')
              f.write('')
            f.close()
          else:
            if already_added_to_single == 0:
              end_append[i] = []
              end_append[i].append(k)
              with open('changelog.txt', 'a') as f:
                #f.write(f'\nAppending {k} to end of {i}, immediately following {last_node}, because order is {k} <--> {associated_branch} <--> {partner}')
                f.write('')
              f.close()
            else:
              with open('changelog.txt', 'a') as f:
                #f.write(f'\nNOT appending {k} to end of {i}, immediately following {last_node}, because already added {k} to start of {i}')
                f.write('')
              f.close()
        # [2B] if node (k) is NOT a daughter node
        else:
          if already_added_to_single == 0:
            end_append[i] = []
            end_append[i].append(k)
            with open('changelog.txt', 'a') as f:
              #f.write(f'\nAppending {k} to end of {i}, immediately after {last_node}')
              f.write('')
            f.close()
          else:
            with open('changelog.txt', 'a') as f:
              #f.write(f'\nNOT appending {k} to end of {i}, immediately following {last_node}, because already added {k} to start of {i}')
              f.write('')
            f.close()


# List of nodes to append
# print('\n')
# print('Append to start of print pass (format "PASS: [NODE]"):')
# print(start_append)
# print('\nAppend to end of print pass (format "PASS: [NODE]"):')
# print(end_append)

# Update print_passes_processed
for i in start_append:
  print_passes_processed[i].insert(0,start_append[i][0]) 
  with open('changelog.txt', 'a') as f:
    f.write(f'\nAppending node {start_append[i][0]} to start of pass {i}.')
  f.close()
for i in end_append:
  print_passes_processed[i].append(end_append[i][0])
  with open('changelog.txt', 'a') as f:
    f.write(f'\nAppending node {end_append[i][0]} to end of pass {i}.')
  f.close()

# Print output
print('\nCondition 0 completed.')
with open('changelog.txt', 'a') as f:
  # Print current list of print_passes_processed
  f.write('\n\nCondition 0 completed.')
  f.write('\n\nCurrent list of print passes: \n\n')
  for i in print_passes_processed:
    f.write(f'Pass {i}: \n{print_passes_processed[i]}')
    f.write('\n\n')
f.close()

########################################################## Changelog 1: Post-Condition 0 ###############################################################

# This cell of code checks for POTENTIALLY disconnected endpoints (i.e. 
# endpoints which only occur once as an endpoint, meaning that no other endpoint
# joins to them) and creates a CHANGELOG of ACTUALLY disconnected points.

# Create list of all endpoints of print_passes_processed
processed_endpoints = []
single_node_in_pass = []
for i in print_passes_processed:
  # if only one coordinate in the pass, only add once
  if len(print_passes_processed[i])==1:
    processed_endpoints.append(print_passes_processed[i][0])
    single_node_in_pass.append(print_passes_processed[i][0])
  else:
    processed_endpoints.append(print_passes_processed[i][0])
    processed_endpoints.append(print_passes_processed[i][-1])

# print('Endpoints of print_passes_processed:')
# print(processed_endpoints)
# print('\n')

# print(f'Single node in pass:')
# print(f'{single_node_in_pass}')

pass_counter = 0
disconnected = []
for i in processed_endpoints:
  pass_counter += 1 
  if processed_endpoints.count(i) == 1:
    disconnected.append(i)

# Exclude inlets/outlets and endpoints of original vessels
to_remove = []
for i in disconnected:
  # Exclude endpoints of original vessels (includes inlets/outlets), UNLESS that endpoint is the only node in its pass
  if (i in endpoint_nodes) and (i not in single_node_in_pass):
    to_remove.append(i)
for i in to_remove:
  disconnected.remove(i)


# Initialize
potential_disconnect = {}
for i in disconnected:
  potential_disconnect[i] = []

# Checking the potentially disconnected endpoints for connection to other parts 
# of the print_passes (e.g., a node within a previous pass may join to where the
# endpoint of a different pass begins; these are not truly disconnected endpoints)

true_disconnected = []
true_disconnected_pass = {}
for i in print_passes_processed:
  for potentially_disconnected_node in disconnected:
    disconnect_count = 0 # reset for iteration
    if potentially_disconnected_node in print_passes_processed[i]:
      # check against other print passes
      for m in range(0,len(print_passes_processed)):
        if potentially_disconnected_node in print_passes_processed[m]:
          potential_disconnect[potentially_disconnected_node].append(m)

# Remove duplicates
for i in potential_disconnect:
  potential_disconnect[i] = [*set(potential_disconnect[i])]

# print('\nPotentially disconnected nodes (format "NODE: [PRINT_PASS OF NODE]"):')
# print(potential_disconnect)

# Find true disconnects (endpoint only appears once, within its own vessel)
final_true_disconnect = {}
for i in potential_disconnect:
  if len(potential_disconnect[i]) == 1:
    final_true_disconnect[i] = potential_disconnect[i]

# print('\nActually disconnected nodes (format "NODE: [PRINT_PASS OF NODE]"):')
# print(final_true_disconnect)

# Locate neighbors of disconnected nodes in the network
neighbor_locs = {}
neighbor_nodes = {}
neighbor_index = {}
neighbor_to_connect = {}
for i in final_true_disconnect:
  neighbor_nodes = graph[i]
  neighbor_locs[i] = []
  neighbor_index[i] = []
  neighbor_to_connect[i] = []

  # for each neighbor (j) of the disconnected node (i)
  for j in neighbor_nodes:
    # if the neighbor is not the disconnected node itself
    if j != i:
      # within each print_pass
      for passNum in print_passes_processed:
        # get the pass of the disconnected node (i)
        pass_of_disconnected_node = final_true_disconnect[i][0]

        # [1] if neighbor (j) in DIFF print_pass as node (i)
        if j in print_passes_processed[passNum] and passNum!=pass_of_disconnected_node: #: i.e., if currently in pass of the neighbor (j) and that pass is different from pass of disconnected node (i); i.e. have found the non-self print_pass containing neighbor 
          # store pass number of the non-self neighbor (j)
          neighbor_locs[i].append(passNum)
          # store index of the neighbor (j) within its own print_pass
          neighbor_index[i].append(print_passes_processed[passNum].index(j))
          # store the nodal identity of neighbor j
          neighbor_to_connect[i].append(j)

        # [2] if neighbor (j) in SAME print_pass as node (i)  
        if j in print_passes_processed[passNum] and passNum==pass_of_disconnected_node:
          # index of disconnected node (i) in its pass
          index = print_passes_processed[passNum].index(i)

          # [2A] if disconnected node (i) is LAST node of its pass
          if index==len(print_passes_processed[passNum])-1:
            # get node to "left" of disconnected node (i) in its pass (ie second-to-last node)
            node_left = print_passes_processed[passNum][(index-1)]
            # only connect neighbor (j) if not already connected to node (i) (ie if not already next to each other in the print_pass)
            if node_left != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)

          # [2B] if disconnected node (i) is FIRST node of its pass
          if index == 0:
            # get node to "right" of disconnected node (i) in its pass (ie second node)
            node_right = print_passes_processed[pass_of_disconnected_node][(index+1)]
            # only connect neighbor (j) if not already connected to node (i)
            if node_right != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)            


# Last processing step to ensure only true disconnects remain
to_pop_disconnects = {}
for i in neighbor_locs:
  passnumber = final_true_disconnect[i][0] # pass of potentially disconnected node
  indexnumber = print_passes_processed[passnumber].index(i) # index of potentially disconnected node in its pass
  # if only one node
  if (len(print_passes_processed[passnumber]) == 1):
    continue
  # if first node
  if (indexnumber == 0) and (len(print_passes_processed[passnumber]) > 0):  # is 0 here for non-empty []
    rightindex = indexnumber+1
    if print_passes_processed[passnumber][rightindex] == neighbor_to_connect[i][0]:
      with open('changelog.txt', 'a') as f:
        f.write(f'\nNode {neighbor_to_connect[i][0]} not actually disconnected.')
      f.close()
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)
  # if last node
  if (indexnumber+1 == len(print_passes_processed[passnumber])) and (len(print_passes_processed[passnumber]) > 0):  # is 0 here for non-empty
    leftindex = indexnumber-1
    if print_passes_processed[passnumber][leftindex] == neighbor_to_connect[i][0]:
      with open('changelog.txt', 'a') as f:
        f.write(f'\nNode {neighbor_to_connect[i][0]} not actually disconnected.')
      f.close()
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)

# Check for any instances in which the first and last node of the same print 
# pass get reciprocally joined to each other, and make it so that only the last 
# node gets joined to the first (not the first to the last)

still_check = {}
tracker = 0
for i in final_true_disconnect:
  pass_to_check = final_true_disconnect[i][0]
  # if the print_pass of the disconnected node is the same as the print_pass of its neighbor (the node to which it joins)
  if final_true_disconnect[i] == neighbor_locs[i]:
    # if first node of pass (only two nodes will be checked for a given print pass - the first and last)
    if (tracker % 2 == 0):
      # save a list of these nodes, sorted by print pass
      still_check[pass_to_check] = []
      still_check[pass_to_check].append(i)      
      # update tracker
      tracker = len(still_check[pass_to_check])
    # if last node of pass (only two nodes will be checked for a given print pass - the first and last)
    elif (tracker % 2 == 1): # don't need to initialize
      still_check[pass_to_check].append(i)    
      tracker == 0
      # update tracker
      tracker = len(still_check[pass_to_check])

for i in (still_check):
  # if two nodes to connect in same print pass
  if len(still_check[i]) == 2:
    node = still_check[i][0]
    next_node = still_check[i][1]
    # if graphical neighbors
    if next_node in graph[node]:
      if neighbor_to_connect[node][0] == next_node:
        # if node is first node of pass and next_node is last node of pass
        if (node == print_passes_processed[i][0]) and (next_node == print_passes_processed[i][-1]):
          with open('changelog.txt', 'a') as f:
            f.write(f'\nfor print pass {i}, not appending {next_node} to {node} at start of pass because {node} will get appended to last node {next_node}.')
          f.close()
          to_pop_disconnects[node] = []
          to_pop_disconnects[node].append(node)
          # print(f'to_pop_disconnects[node] is {to_pop_disconnects[node]}') 

for i in to_pop_disconnects:
  final_true_disconnect.pop(i)
  neighbor_locs.pop(i)
  neighbor_to_connect.pop(i)
  neighbor_index.pop(i)

# Print summary table of remaining disconnected nodes
with open('changelog.txt', 'a') as f:
  f.write('\n')
  f.write('Summary of remaining disconnects:                         Join to:')
  f.write('\n-----------------------------------------------------     --------------------')
  for i in neighbor_locs:
    f.write(f'\nNode {i} is in pass {final_true_disconnect[i][0]} and disconnected from pass {neighbor_locs[i][0]}.        {neighbor_to_connect[i][0]} at index {neighbor_index[i][0]}')
  f.write('\n-----------------------------------------------------     --------------------')
  f.write('\n\nNumber of disconnects: ')
  f.write(str(len(final_true_disconnect)))
  f.write('\n\n################################################################################')
f.close()  

# For any passes consisting of only 1 node, check whether that single point gets
# printed in previous or future print passes (due to having been appended above)
# and, if so, remove its print pass from the list of passes.

for i in print_passes_processed:
  if len(print_passes_processed[i]) == 1:
    for j in range(0,i):
      if print_passes_processed[i][0] in print_passes_processed[j]:
        # drop from print_passes_processed dictionary if this single point will be printed in a previous pass
        print_passes_processed[i] = [arbitrary_val, arbitrary_val]  # will post-process to remove empty arrays at end
    for k in range(i+1,len(print_passes_processed)):
      if print_passes_processed[i][0] in print_passes_processed[k]:
        # drop from print_passes_processed dictionary if this single point will be printed in a future pass (because it was previously appended in code above)
        print_passes_processed[i] = [arbitrary_val, arbitrary_val]  # will post-process to remove empty arrays at end


######################### Post-Processing: BRANCHPOINT CONDITION #1 (Daughters-to-Parent, "Checking Backwards") ###################################

print('\n\nNow running Branchpoint Condition #1.')

with open('changelog.txt', 'a') as f:
  f.write('\n\nNow running Branchpoint Condition #1.\n')
f.close()

# BRANCHPOINT CONDITION #1

# Close branchpoints: daughters-to-parent (checking "backwards").

# In the following block of code, check whether any daughter nodes (i.e., 
# the two nodes that "sandwich" the parent branchpoint) serve as endpoints
# (either first_point or last_point) of the current print_pass. If so, check 
# whether their parent branchpoint (parents = "keys" of branch_dict) falls 
# within a PREVIOUS print_pass (anywhere within that print_pass; the parent itself
# does not need to be an endpoint). If so, append the parent branchpoint to the
# daughter branchpoint in the current print_pass.

# For passes which consist of only one point, avoid appending the parent 
# branchpoint to both the start and the end of that point (resulting in 3 nodes
# in the pass, when it should just be 2) by appending ONLY to the start, not 
# to the end. The START was selected because ink continuity is enhanced when
# starting from a shared node, rather than ending on a shared node.

# This block handles gaps between numerically NON-SUCCESSIVE indices.

# Note: these sections specifically check the first/last nodes of each print_pass, 
# because gaps appear only at these nodes (i.e., between discrete print_passes).

# Initializing
append_first_branch = {}
append_first_branch_check = {}
append_last_branch = {}
append_last_branch_check = {}

# For current print_pass (i) in print_passes_processed (starting with second print_pass)
for i in range(1,len(print_passes_processed)):
  # first node of print_pass (i)
  first_point = print_passes_processed[i][0]
  # last node of print_pass (i)
  last_point = print_passes_processed[i][-1]
  # if >1 node in current print_pass (i)
  if len(print_passes_processed[i]) > 1:
    # get the second node
    second_point = print_passes_processed[i][1]
    # get the second-to-last node
    second_to_last_point = print_passes_processed[i][-2]
  # [1] if the FIRST node of print_pass (i) is a daughter
  if first_point in branchpoint_list:
    if first_point not in repeat_daughters:
      # find parent branchpoint and daughter pair
      list_index = int(branchpoint_list.index(first_point))
      list_index = int(np.trunc(list_index/2))
      associated_branch = list(branch_dict)[list_index]
      pair = branch_dict[associated_branch]
      partner = [point for point in pair if point != k][0]
    elif first_point in repeat_daughters:
      for (index, item) in enumerate(branchpoint_list):
        if item == first_point:
          list_index = int(np.trunc(index/2))
          associated_branch = list(branch_dict)[list_index]
          pair = branch_dict[associated_branch]
          partner = [point for point in pair if point != item][0]
    # for each print_pass (j) prior to the current print_pass (i)
    for j in range(0,i):
      # for each node (k) of print_pass (j)
      for k in print_passes_processed[j]:
        # if node (k) is the parent branchpoint of the first_node (daughter) of print_pass (i), connect the parent (k) to start of print_pass (i)
        if int(associated_branch) == k:
          if second_point != int(associated_branch): # if not already connected
            append_first_branch[i] = []
            append_first_branch[i] = k
  # [2] if LAST NODE of print_pass (i) is a daughter
  if last_point in branchpoint_list:
    if last_point not in repeat_daughters:
      # find parent branchpoint and daughter pair
      list_index = int(branchpoint_list.index(last_point))
      list_index = int(np.trunc(list_index/2))
      associated_branch = list(branch_dict)[list_index]
      pair = branch_dict[associated_branch]
      partner = [point for point in pair if point != k][0]
    elif last_point in repeat_daughters:
      for (index, item) in enumerate(branchpoint_list):
        if item == last_point:
          list_index = int(np.trunc(index/2))
          associated_branch = list(branch_dict)[list_index]
          pair = branch_dict[associated_branch]
          partner = [point for point in pair if point != item][0]
    # for each print_pass (j) prior to the current print_pass (i)
    for j in range(0,i):
      # for each node (k) of print_pass (j)
      for k in print_passes_processed[j]:
        # if node (k) is parent branchpoint of last_node (daughter) of print_pass (i), connect parent (k) to end of print_pass (i), UNLESS only one node in pass (in which case, we already added it to the start, above)
        if (int(associated_branch) == k) and (first_point != last_point):
          if second_to_last_point != int(associated_branch):
            append_last_branch[i] = []
            append_last_branch[i] = k


# List of nodes to append
# print('\n')
# print('Append to start of print pass (format "PASS: [NODE]"):')
# print(append_first_branch)
# print('\nAppend to end of print pass (format "PASS: [NODE]"):')
# print(append_last_branch)

# Update print_passes_processed (BRANCHPOINT CONDITION #1)
for i in append_first_branch:
  print_passes_processed[i].insert(0,append_first_branch[i]) 
  with open('changelog.txt', 'a') as f:
    f.write(f'\nAppending node {append_first_branch[i]} to start of pass {i}.')
  f.close()
for i in append_last_branch:
  print_passes_processed[i].append(append_last_branch[i])
  with open('changelog.txt', 'a') as f:
    f.write(f'\nAppending node {append_last_branch[i]} to end of pass {i}.')
  f.close()

# Print output
print('\nBranchpoint Condition #1 completed.')

# Print current list of print_passes_processed
with open('changelog.txt', 'a') as f:
  f.write('\nBranchpoint Condition #1 completed.\n')
  f.write('\nCurrent list of print passes: \n\n')
  for i in print_passes_processed:
    f.write(f'Pass {i} \n{print_passes_processed[i]}')
    f.write('\n\n')
f.close()

################################################### Changelog 2: Post-Branchpoint Condition 1  ##############################################################

# CHANGELOG: BRANCHPOINT CONDITION #1

# This cell of code checks for POTENTIALLY disconnected endpoints (i.e. 
# endpoints which only occur once as an endpoint, meaning that no other endpoint
# joins to them) and creates a CHANGELOG of ACTUALLY disconnected points.

# Create list of all endpoints of print_passes_processed
processed_endpoints = []
single_node_in_pass = []
for i in print_passes_processed:
  # if only one coordinate in the pass, only add once
  if len(print_passes_processed[i])==1:
    processed_endpoints.append(print_passes_processed[i][0])
    single_node_in_pass.append(print_passes_processed[i][0])
  else:
    processed_endpoints.append(print_passes_processed[i][0])
    processed_endpoints.append(print_passes_processed[i][-1])

# print('Endpoints of print_passes_processed:')
# print(processed_endpoints)

# print(f'\nSingle node in pass:')
# print(f'{single_node_in_pass}')

pass_counter = 0
disconnected = []
for i in processed_endpoints:
  pass_counter += 1 
  if processed_endpoints.count(i) == 1:
    disconnected.append(i)

# Exclude inlets/outlets and endpoints of original vessels
to_remove = []
for i in disconnected:
  # Exclude endpoints of original vessels (includes inlets/outlets), UNLESS that endpoint is the only node in its pass
  if (i in endpoint_nodes) and (i not in single_node_in_pass):
    to_remove.append(i)
for i in to_remove:
  disconnected.remove(i)


# Initialize
potential_disconnect = {}
for i in disconnected:
  potential_disconnect[i] = []

# Checking the potentially disconnected endpoints for connection to other parts 
# of the print_passes (e.g., a node within a previous pass may join to where the
# endpoint of a different pass begins; these are not truly disconnected endpoints)

true_disconnected = []
true_disconnected_pass = {}
for i in print_passes_processed:
  for potentially_disconnected_node in disconnected:
    disconnect_count = 0 # reset for iteration
    if potentially_disconnected_node in print_passes_processed[i]:
      # check against other print passes
      for m in range(0,len(print_passes_processed)):
        if potentially_disconnected_node in print_passes_processed[m]:
          potential_disconnect[potentially_disconnected_node].append(m)

# Remove duplicates
for i in potential_disconnect:
  potential_disconnect[i] = [*set(potential_disconnect[i])]

# Find true disconnects (endpoint only appears once, within its own vessel)
final_true_disconnect = {}
for i in potential_disconnect:
  if len(potential_disconnect[i]) == 1:
    final_true_disconnect[i] = potential_disconnect[i]

# Print output
# print('\nActually disconnected nodes (format "NODE: [PRINT_PASS OF NODE]"):')
# print(final_true_disconnect)
# print('\n')

# Locate neighbors of disconnected nodes in the network
neighbor_locs = {}
neighbor_nodes = {}
neighbor_index = {}
neighbor_to_connect = {}
for i in final_true_disconnect:
  neighbor_nodes = graph[i]
  neighbor_locs[i] = []
  neighbor_index[i] = []
  neighbor_to_connect[i] = []

  # for each neighbor (j) of the disconnected node (i)
  for j in neighbor_nodes:
    # if the neighbor is not the disconnected node itself
    if j != i:
      # within each print_pass
      for passNum in print_passes_processed:
        # get the pass of the disconnected node (i)
        pass_of_disconnected_node = final_true_disconnect[i][0]

        # [1] if neighbor (j) in DIFF print_pass as node (i)
        if j in print_passes_processed[passNum] and passNum!=pass_of_disconnected_node: #: i.e., if currently in pass of the neighbor (j) and that pass is different from pass of disconnected node (i); i.e. have found the non-self print_pass containing neighbor 
          # store pass number of the non-self neighbor (j)
          neighbor_locs[i].append(passNum)
          # store index of the neighbor (j) within its own print_pass
          neighbor_index[i].append(print_passes_processed[passNum].index(j))
          # store the nodal identity of neighbor j
          neighbor_to_connect[i].append(j)

        # [2] if neighbor (j) in SAME print_pass as node (i)  
        if j in print_passes_processed[passNum] and passNum==pass_of_disconnected_node:
          # index of disconnected node (i) in its pass
          index = print_passes_processed[passNum].index(i)

          # [2A] if disconnected node (i) is LAST node of its pass
          if index==len(print_passes_processed[passNum])-1:
            # get node to "left" of disconnected node (i) in its pass (ie second-to-last node)
            node_left = print_passes_processed[passNum][(index-1)]
            # only connect neighbor (j) if not already connected to node (i) (ie if not already next to each other in the print_pass)
            if node_left != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)

          # [2B] if disconnected node (i) is FIRST node of its pass
          if index == 0:
            # get node to "right" of disconnected node (i) in its pass (ie second node)
            node_right = print_passes_processed[pass_of_disconnected_node][(index+1)]
            # only connect neighbor (j) if not already connected to node (i)
            if node_right != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)            


# Last processing step to ensure only true disconnects remain
to_pop_disconnects = {}
for i in neighbor_locs:
  passnumber = final_true_disconnect[i][0] # pass of potentially disconnected node
  indexnumber = print_passes_processed[passnumber].index(i) # index of potentially disconnected node in its pass
  # if only one node
  if (len(print_passes_processed[passnumber]) == 1):
    # print(f' only one node {i}')
    continue
  # if first node
  if (indexnumber == 0) and (len(print_passes_processed[passnumber]) > 0): # is 0 here for non-empty []
    rightindex = indexnumber+1
    if print_passes_processed[passnumber][rightindex] == neighbor_to_connect[i][0]:
      with open('changelog.txt', 'a') as f:
        f.write(f'\nNode {neighbor_to_connect[i][0]} not actually disconnected.')
      f.close()
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)
  # if last node
  if (indexnumber+1 == len(print_passes_processed[passnumber])) and (len(print_passes_processed[passnumber]) > 0):  # is 0 here for non-empty []
    leftindex = indexnumber-1
    if print_passes_processed[passnumber][leftindex] == neighbor_to_connect[i][0]:
      with open('changelog.txt', 'a') as f:
        f.write(f'\nNode {neighbor_to_connect[i][0]} not actually disconnected.')
      f.close()
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)


# Check for any instances in which the first and last node of the same print 
# pass get reciprocally joined to each other, and make it so that only the last 
# node gets joined to the first (not the first to the last)

still_check = {}
tracker = 0
for i in final_true_disconnect:
  pass_to_check = final_true_disconnect[i][0]
  # if the print_pass of the disconnected node is the same as the print_pass of its neighbor (the node to which it joins)
  if final_true_disconnect[i] == neighbor_locs[i]:
    # if neighbors
    # print(f'final_true_disconnect[i] == neighbor_locs[i]: {final_true_disconnect[i]} == {neighbor_locs[i]} ')
    # if first node of pass (only two nodes will be checked for a given print pass - the first and last)
    if (tracker % 2 == 0):
      # save a list of these nodes, sorted by print pass
      still_check[pass_to_check] = []
      still_check[pass_to_check].append(i)      
      # update tracker
      tracker = len(still_check[pass_to_check])
    # if last node of pass (only two nodes will be checked for a given print pass - the first and last)
    elif (tracker % 2 == 1): # don't need to initialize
      still_check[pass_to_check].append(i)    
      tracker == 0
      # update tracker
      tracker = len(still_check[pass_to_check])

for i in (still_check):
  # if two nodes to connect in same print pass
  if len(still_check[i]) == 2:
    node = still_check[i][0]
    next_node = still_check[i][1]
    # if graphical neighbors
    if next_node in graph[node]:
      if neighbor_to_connect[node][0] == next_node:
        # if node is first node of pass and next_node is last node of pass
        if (node == print_passes_processed[i][0]) and (next_node == print_passes_processed[i][-1]):
          with open('changelog.txt', 'a') as f:
            f.write(f'for print pass {i}, not going to append {next_node} to {node} at start of pass because {node} will get appended to last node {next_node}.')
          f.close()
          to_pop_disconnects[node] = []
          to_pop_disconnects[node].append(node)

for i in to_pop_disconnects:
  final_true_disconnect.pop(i)
  neighbor_locs.pop(i)
  neighbor_to_connect.pop(i)
  neighbor_index.pop(i)

# Print summary table of remaining disconnected nodes
with open('changelog.txt', 'a') as f:
  f.write('\n')
  f.write('Summary of remaining disconnects:                         Join to:')
  f.write('\n-----------------------------------------------------     --------------------')
  for i in neighbor_locs:
    f.write(f'\nNode {i} is in pass {final_true_disconnect[i][0]} and disconnected from pass {neighbor_locs[i][0]}.        {neighbor_to_connect[i][0]} at index {neighbor_index[i][0]}')
  f.write('\n-----------------------------------------------------     --------------------')
  f.write('\n\nNumber of disconnects: ')
  f.write(str(len(final_true_disconnect)))
  f.write('\n\n################################################################################')
f.close()  


######################## Post-Processing: BRANCHPOINT CONDITION #2 (Daughters-to-Parents, "Checking Forwards") #################################################################

print('\nNow running Branchpoint Condition #2.')

with open('changelog.txt', 'a') as f:
  f.write('\n\nNow running Branchpoint Condition #2.\n')
f.close()

# BRANCHPOINT CONDITION #2

# Closing branchpoints: daughter-to-parent (checking "forwards").

# In the following block of code, check whether any daughter nodes (i.e., 
# the two nodes that "sandwich" the parent branchpoint) serve as endpoints
# (either first_point or last_point) of the current print_pass. If so, check 
# whether their parent branchpoint (parents = "keys" of branch_dict) falls 
# within a FUTURE print_pass (anywhere within that print_pass; the parent itself
# does not need to be an endpoint). If so, append the parent branchpoint to the
# daughter branchpoint in the current print_pass - but ONLY IF the parent 
# branchpoint is not already its neighbor in the current print_pass (i.e., from)
# having already been appended when checking Branchpoint Condition #1).

# Note: these sections specifically check the first/last nodes of each print_pass, 
# because gaps appear only at these nodes (i.e., between discrete print_passes).

# Initializing
append_first_branch = {}
append_last_branch = {}

# For print_pass (i) in list of print_passes_processed
for i in print_passes_processed:
  # first node of print_pass (i)
  first_point = print_passes_processed[i][0]
  # last node of print_pass (i)
  last_point = print_passes_processed[i][-1]
  # if >1 node in current print_pass (i)
  if len(print_passes_processed[i]) > 1:
    # get the second node
    second_point = print_passes_processed[i][1]
    # get the second-to-last node
    second_to_last_point = print_passes_processed[i][-2]
  # if FIRST NODE of print_pass (i) is a daughter
  if first_point in branchpoint_list:
    # find parent branchpoint and daughter pair (when daugher has only one parent)
    if first_point not in repeat_daughters:
      # find parent branchpoint and daughter pair
      list_index = int(branchpoint_list.index(first_point))
      list_index = int(np.trunc(list_index/2))
      associated_branch = list(branch_dict)[list_index]
      pair = branch_dict[associated_branch]
      partner = [point for point in pair if point != k][0]
    # find parent branchpoint and daughter pair (when daughter has >1 parent)
    elif first_point in repeat_daughters:
      for (index, item) in enumerate(branchpoint_list):
        if item == first_point:
          list_index = int(np.trunc(index/2))
          associated_branch = list(branch_dict)[list_index]
          pair = branch_dict[associated_branch]
          partner = [point for point in pair if point != item][0]
    # for each print_pass (j) following print_pass (i)
    for j in range(i+1,len(print_passes_processed)):
      # for each node (k) of print_pass (j)
      for k in print_passes_processed[j]:
        # if (k) is the parent branchpoint and the first_node is not already connected to the parent branchpoint
        if int(associated_branch) == k and second_point != int(associated_branch):
          append_first_branch[i] = []
          append_first_branch[i] = k
  # if LAST NODE of print_pass (i) is a daughter
  if last_point in branchpoint_list:
    if last_point not in repeat_daughters:
      # find parent branchpoint and daughter pair
      list_index = int(branchpoint_list.index(last_point))
      list_index = int(np.trunc(list_index/2))
      associated_branch = list(branch_dict)[list_index]
      pair = branch_dict[associated_branch]
      partner = [point for point in pair if point != k][0]
    elif last_point in repeat_daughters:
      for (index, item) in enumerate(branchpoint_list):
        if item == last_point:
          list_index = int(np.trunc(index/2))
          associated_branch = list(branch_dict)[list_index]
          pair = branch_dict[associated_branch]
          partner = [point for point in pair if point != item][0]
    # for each print_pass (j) following print_pass (i)
    for j in range(i+1,len(print_passes_processed)):
      # for each node (k) of print_pass (j)
      for k in print_passes_processed[j]:
        # if (k) is the parent branchpoint and the last_node is not already connected to the parent branchpoint
        if int(associated_branch) == k and second_to_last_point != int(associated_branch):
          append_last_branch[i] = []
          append_last_branch[i] = k

# print('Append to start of print pass (format "PASS: [NODE]"):')
# print(append_first_branch)
# print('\nAppend to end of print pass (format "PASS: [NODE]"):')
# print(append_last_branch)


# Update print_passes_processed (BRANCHPOINT CONDITION #2)
for i in append_first_branch:
  print_passes_processed[i].insert(0,append_first_branch[i]) 
  with open('changelog.txt', 'a') as f:
    f.write(f'\nAppending node {append_first_branch[i]} to start of pass {i}.')
  f.close()
for i in append_last_branch:
  print_passes_processed[i].append(append_last_branch[i])
  with open('changelog.txt', 'a') as f:
    f.write(f'\nAppending node {append_last_branch[i]} to end of pass {i}.')
  f.close()

# print output
print('\nBranchpoint Condition #2 completed.')

# Print updated passes (BRANCHPOINT CONDITION #2)
with open('changelog.txt', 'a') as f:
  f.write('\n\nBranchpoint Condition #2 completed.\n')
  f.write('\nCurrent list of print passes: \n')
  for i in print_passes_processed:
    f.write(f'\nPass {i} | {print_passes_processed[i]}')
    f.write('\n')
f.close()

############################################ Changelog 3: Post-Branchpoint Condition 2 ##############################################################

# This cell of code checks for POTENTIALLY disconnected endpoints (i.e. 
# endpoints which only occur once as an endpoint, meaning that no other endpoint
# joins to them) and creates a CHANGELOG of ACTUALLY disconnected points.

# Create list of all endpoints of print_passes_processed
processed_endpoints = []
single_node_in_pass = []
for i in print_passes_processed:
  # if only one coordinate in the pass, only add once
  if len(print_passes_processed[i])==1:
    processed_endpoints.append(print_passes_processed[i][0])
    single_node_in_pass.append(print_passes_processed[i][0])
  else:
    processed_endpoints.append(print_passes_processed[i][0])
    processed_endpoints.append(print_passes_processed[i][-1])

# print('Endpoints of print_passes_processed:')
# print(processed_endpoints)
# print('\n')

# print('Single node in pass:')
# print(f'{single_node_in_pass}')

pass_counter = 0
disconnected = []
for i in processed_endpoints:
  pass_counter += 1 
  if processed_endpoints.count(i) == 1:
    disconnected.append(i)

# Exclude inlets/outlets and endpoints of original vessels
to_remove = []
for i in disconnected:
  # Exclude endpoints of original vessels (includes inlets/outlets), UNLESS that endpoint is the only node in its pass
  if (i in endpoint_nodes) and (i not in single_node_in_pass):
    to_remove.append(i)
for i in to_remove:
  disconnected.remove(i)


# Initialize
potential_disconnect = {}
for i in disconnected:
  potential_disconnect[i] = []

# Checking the potentially disconnected endpoints for connection to other parts 
# of the print_passes (e.g., a node within a previous pass may join to where the
# endpoint of a different pass begins; these are not truly disconnected endpoints)

true_disconnected = []
true_disconnected_pass = {}
for i in print_passes_processed:
  for potentially_disconnected_node in disconnected:
    disconnect_count = 0 # reset for iteration
    if potentially_disconnected_node in print_passes_processed[i]:
      # check against other print passes
      for m in range(0,len(print_passes_processed)):
        if potentially_disconnected_node in print_passes_processed[m]:
          # print(f'i: {i}, disconnected: {potentially_disconnected_node}, m: {m}')
          potential_disconnect[potentially_disconnected_node].append(m)

# Remove duplicates
for i in potential_disconnect:
  potential_disconnect[i] = [*set(potential_disconnect[i])]


# Find true disconnects (endpoint only appears once, within its own vessel)
final_true_disconnect = {}
for i in potential_disconnect:
  if len(potential_disconnect[i]) == 1:
    final_true_disconnect[i] = potential_disconnect[i]

# Print output
# print('\nActually disconnected nodes (format NODE: [PRINT_PASS OF NODE]):')
# print(final_true_disconnect)
# print('\n')

# Locate neighbors of disconnected nodes in the network
neighbor_locs = {}
neighbor_nodes = {}
neighbor_index = {}
neighbor_to_connect = {}
for i in final_true_disconnect:
  neighbor_nodes = graph[i]
  neighbor_locs[i] = []
  neighbor_index[i] = []
  neighbor_to_connect[i] = []

  # for each neighbor (j) of the disconnected node (i)
  for j in neighbor_nodes:
    # if the neighbor is not the disconnected node itself
    if j != i:
      # within each print_pass
      for passNum in print_passes_processed:
        # get the pass of the disconnected node (i)
        pass_of_disconnected_node = final_true_disconnect[i][0]

        # [1] if neighbor (j) in DIFF print_pass as node (i)
        if j in print_passes_processed[passNum] and passNum!=pass_of_disconnected_node: #: i.e., if currently in pass of the neighbor (j) and that pass is different from pass of disconnected node (i); i.e. have found the non-self print_pass containing neighbor 
          # store pass number of the non-self neighbor (j)
          neighbor_locs[i].append(passNum)
          # store index of the neighbor (j) within its own print_pass
          neighbor_index[i].append(print_passes_processed[passNum].index(j))
          # store the nodal identity of neighbor j
          neighbor_to_connect[i].append(j)

        # [2] if neighbor (j) in SAME print_pass as node (i)  
        if j in print_passes_processed[passNum] and passNum==pass_of_disconnected_node:
          # index of disconnected node (i) in its pass
          index = print_passes_processed[passNum].index(i)

          # [2A] if disconnected node (i) is LAST node of its pass
          if index==len(print_passes_processed[passNum])-1:
            # get node to "left" of disconnected node (i) in its pass (ie second-to-last node)
            node_left = print_passes_processed[passNum][(index-1)]
            # only connect neighbor (j) if not already connected to node (i) (ie if not already next to each other in the print_pass)
            if node_left != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)

          # [2B] if disconnected node (i) is FIRST node of its pass
          if index == 0:
            # get node to "right" of disconnected node (i) in its pass (ie second node)
            node_right = print_passes_processed[pass_of_disconnected_node][(index+1)]
            # only connect neighbor (j) if not already connected to node (i)
            if node_right != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)            


# Last processing step to ensure only true disconnects remain
to_pop_disconnects = {}
for i in neighbor_locs:
  passnumber = final_true_disconnect[i][0] # pass of potentially disconnected node
  indexnumber = print_passes_processed[passnumber].index(i) # index of potentially disconnected node in its pass
  # if only one node
  if (len(print_passes_processed[passnumber]) == 1):
    continue
  # if first node
  if (indexnumber == 0) and (len(print_passes_processed[passnumber]) > 0):  # is 0 here for non-empty []
    rightindex = indexnumber+1
    if print_passes_processed[passnumber][rightindex] == neighbor_to_connect[i][0]:
      with open('changelog.txt', 'a') as f:
        f.write(f'{neighbor_to_connect[i][0]} not actually disconnected.')
      f.close()
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)
  # if last node
  if (indexnumber+1 == len(print_passes_processed[passnumber])) and (len(print_passes_processed[passnumber]) > 0):  # is 0 here for non-empty []
    leftindex = indexnumber-1
    if print_passes_processed[passnumber][leftindex] == neighbor_to_connect[i][0]:
      with open('changelog.txt', 'a') as f:
        f.write(f'{neighbor_to_connect[i][0]} not actually disconnected.')
      f.close()
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)

# Check for any instances in which the first and last node of the same print 
# pass get reciprocally joined to each other, and make it so that only the last 
# node gets joined to the first (not the first to the last)

still_check = {}
tracker = 0
for i in final_true_disconnect:
  pass_to_check = final_true_disconnect[i][0]
  # if the print_pass of the disconnected node is the same as the print_pass of its neighbor (the node to which it joins)
  if final_true_disconnect[i] == neighbor_locs[i]:
    # if first node of pass (only two nodes will be checked for a given print pass - the first and last)
    if (tracker % 2 == 0):
      # save a list of these nodes, sorted by print pass
      still_check[pass_to_check] = []
      still_check[pass_to_check].append(i)      
      # update tracker
      tracker = len(still_check[pass_to_check])
    # if last node of pass (only two nodes will be checked for a given print pass - the first and last)
    elif (tracker % 2 == 1): # don't need to initialize
      still_check[pass_to_check].append(i)    
      tracker == 0
      # update tracker
      tracker = len(still_check[pass_to_check])

for i in (still_check):
  # if two nodes to connect in same print pass
  if len(still_check[i]) == 2:
    node = still_check[i][0]
    next_node = still_check[i][1]
    # if graphical neighbors
    if next_node in graph[node]:
      if neighbor_to_connect[node][0] == next_node:
        # if node is first node of pass and next_node is last node of pass
        if (node == print_passes_processed[i][0]) and (next_node == print_passes_processed[i][-1]):
          with open('changelog.txt', 'a') as f:
            f.write(f'for print pass {i}, not going to append {next_node} to {node} at start of pass because {node} will get appended to last node {next_node}.')
          f.close()
          to_pop_disconnects[node] = []
          to_pop_disconnects[node].append(node)
          # print(f'to_pop_disconnects[node] is {to_pop_disconnects[node]}') 

for i in to_pop_disconnects:
  final_true_disconnect.pop(i)
  neighbor_locs.pop(i)
  neighbor_to_connect.pop(i)
  neighbor_index.pop(i)


# Print summary table of remaining disconnected nodes
with open('changelog.txt', 'a') as f:
  f.write('\n')
  f.write('Summary of remaining disconnects:                         Join to:')
  f.write('\n-----------------------------------------------------     --------------------')
  for i in neighbor_locs:
    f.write(f'\nNode {i} is in pass {final_true_disconnect[i][0]} and disconnected from pass {neighbor_locs[i][0]}.        {neighbor_to_connect[i][0]} at index {neighbor_index[i][0]}')
  f.write('\n-----------------------------------------------------     --------------------')
  f.write('\n\nNumber of disconnects: ')
  f.write(str(len(final_true_disconnect)))
  f.write('\n\n################################################################################')
f.close()  


###################### Post-Processing: BRANCHPOINT CONDITION #3 (Parent-to-neighbor, where neighbor is non-daughter) ######################

print('\nNow running Branchpoint Condition #3.')

with open('changelog.txt', 'a') as f:
  f.write('\n\nNow running Branchpoint Condition #3.')
f.close()

# BRANCHPOINT CONDITION #3

# Close branchpoints: parent-to-neighbor (non-daughter).

# In this block: If START of print_pass is a parent branchpoint, check that it 
# connects to its NON-DAUGHTER neighbor if that neighbor is in a previous 
# print_pass. 

# The parent branchpoints were already connected to their DAUGHTERS in 
# BRANCHPOINT CONDITIONS #1 AND #2.

# Note: these sections specifically check the first/last nodes of each print_pass, 
# because gaps appear only at these nodes (i.e., between discrete print_passes).

# Initializing
append_end = {}
append_start = {}

# For each print_pass (i)
for i in range(1,len(print_passes_processed)):
  # first point of the current print_pass (i)
  first_point_curr = print_passes_processed[i][0]
  # if first_point of current print_pass (i) is a parent branchpoint
  if first_point_curr in branch_dict:
    # for each print_pass (j) prior to current print_pass (i)
    for j in range(0,i):
      # last and first nodes of previous print_pass (j)
      last_point_prev = print_passes_processed[j][-1]
      first_node_prev = print_passes_processed[j][0]
      # find non-daughter graphical neighbor of parent branchpoint (aka of first_point)
      first_point_neighbors = graph[first_point_curr]
      first_point_branches = branch_dict[first_point_curr]
      overlap = list(set(first_point_neighbors).intersection(first_point_branches))
      removed = [x for x in first_point_neighbors if x not in overlap]
      removed = [x for x in removed if x != first_point_curr]
      removed = removed[0]
      # if the non-daughter graphical neighbor of parent branchpoint (i) is the last point of previous print_pass (j)
      if (removed == last_point_prev):
        append_end[j] = []
        append_end[j].append(first_point_curr)
      # if the non-daughter graphical neighbor of parent branchpoint (i) is the first point of previous print_pass (j)
      elif (removed == first_node_prev):
        append_start[j] = []
        append_start[j].append(first_point_curr)


# print('\n')
# print('Append to start of print pass (format "PASS: [NODE]"):')
# print(append_start)
# print('Append to end of print pass (format "PASS: [NODE]"):')
# print(append_end)


# Update print_passes (BRANCHPOINT CONDITION #3)
for i in append_start:
  print_passes_processed[i].insert(0,append_start[i][0])
  with open('changelog.txt', 'a') as f:
    f.write(f'\nAppending node {append_start[i][0]} to start of pass {i}.')
  f.close()
for i in append_end:
  print_passes_processed[i].append(append_end[i][0])
  with open('changelog.txt', 'a') as f:
    f.write(f'\nAppending node {append_end[i][0]} to end of pass {i}.')
  f.close()

# Print output
print('\nBranchpoint Condition #3 completed.')

# Print updated print passes
with open('changelog.txt', 'a') as f:
  f.write('\n\nBranchpoint Condition #3 completed.\n')
  f.write(f'\nCurrent list of print passes:\n\n')
  for passNum in print_passes_processed:
    f.write(f'Pass {passNum} \n{print_passes_processed[passNum]}')
    f.write('\n\n')
f.close()



############################################# Changelog 4: Post-Branchpoint Condition 3 #################################################

# CHANGELOG: BRANCHPOINT CONDITION #3

# This cell of code checks for POTENTIALLY disconnected endpoints (i.e. 
# endpoints which only occur once as an endpoint, meaning that no other endpoint
# joins to them) and creates a CHANGELOG of ACTUALLY disconnected points.

# Create list of all endpoints of print_passes_processed
processed_endpoints = []
single_node_in_pass = []
for i in print_passes_processed:
  # if only one coordinate in the pass, only add once
  if len(print_passes_processed[i])==1:
    processed_endpoints.append(print_passes_processed[i][0])
    single_node_in_pass.append(print_passes_processed[i][0])
  else:
    processed_endpoints.append(print_passes_processed[i][0])
    processed_endpoints.append(print_passes_processed[i][-1])

# print('Endpoints of print_passes_processed:')
# print(processed_endpoints)
# print('\n')

# print('Single node in pass:')
# print(f'{single_node_in_pass}')

pass_counter = 0
disconnected = []
for i in processed_endpoints:
  pass_counter += 1 
  if processed_endpoints.count(i) == 1:
    disconnected.append(i)

# Exclude inlets/outlets and endpoints of original vessels
to_remove = []
for i in disconnected:
  # Exclude endpoints of original vessels (includes inlets/outlets), UNLESS that endpoint is the only node in its pass
  if (i in endpoint_nodes) and (i not in single_node_in_pass):
    to_remove.append(i)
for i in to_remove:
  disconnected.remove(i)


# Initialize
potential_disconnect = {}
for i in disconnected:
  potential_disconnect[i] = []

# Checking the potentially disconnected endpoints for connection to other parts 
# of the print_passes (e.g., a node within a previous pass may join to where the
# endpoint of a different pass begins; these are not truly disconnected endpoints)

true_disconnected = []
true_disconnected_pass = {}
for i in print_passes_processed:
  for potentially_disconnected_node in disconnected:
    disconnect_count = 0 # reset for iteration
    if potentially_disconnected_node in print_passes_processed[i]:
      # check against other print passes
      for m in range(0,len(print_passes_processed)):
        if potentially_disconnected_node in print_passes_processed[m]:
          potential_disconnect[potentially_disconnected_node].append(m)

# Remove duplicates
for i in potential_disconnect:
  potential_disconnect[i] = [*set(potential_disconnect[i])]

# Find true disconnects (endpoint only appears once, within its own vessel)
final_true_disconnect = {}
for i in potential_disconnect:
  if len(potential_disconnect[i]) == 1:
    final_true_disconnect[i] = potential_disconnect[i]

# print('\nActually disconnected nodes (format NODE: [PRINT_PASS OF NODE]):')
# print(final_true_disconnect)
# print('\n')

# Locate neighbors of disconnected nodes in the network
neighbor_locs = {}
neighbor_nodes = {}
neighbor_index = {}
neighbor_to_connect = {}
for i in final_true_disconnect:
  neighbor_nodes = graph[i]
  neighbor_locs[i] = []
  neighbor_index[i] = []
  neighbor_to_connect[i] = []

  # for each neighbor (j) of the disconnected node (i)
  for j in neighbor_nodes:
    # if the neighbor is not the disconnected node itself
    if j != i:
      # within each print_pass
      for passNum in print_passes_processed:
        # get the pass of the disconnected node (i)
        pass_of_disconnected_node = final_true_disconnect[i][0]

        # [1] if neighbor (j) in DIFF print_pass as node (i)
        if j in print_passes_processed[passNum] and passNum!=pass_of_disconnected_node: #: i.e., if currently in pass of the neighbor (j) and that pass is different from pass of disconnected node (i); i.e. have found the non-self print_pass containing neighbor 
          # store pass number of the non-self neighbor (j)
          neighbor_locs[i].append(passNum)
          # store index of the neighbor (j) within its own print_pass
          neighbor_index[i].append(print_passes_processed[passNum].index(j))
          # store the nodal identity of neighbor j
          neighbor_to_connect[i].append(j)

        # [2] if neighbor (j) in SAME print_pass as node (i)  
        if j in print_passes_processed[passNum] and passNum==pass_of_disconnected_node:
          # index of disconnected node (i) in its pass
          index = print_passes_processed[passNum].index(i)

          # [2A] if disconnected node (i) is LAST node of its pass
          if index==len(print_passes_processed[passNum])-1:
            # get node to "left" of disconnected node (i) in its pass (ie second-to-last node)
            node_left = print_passes_processed[passNum][(index-1)]
            # only connect neighbor (j) if not already connected to node (i) (ie if not already next to each other in the print_pass)
            if node_left != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)

          # [2B] if disconnected node (i) is FIRST node of its pass
          if index == 0:
            # get node to "right" of disconnected node (i) in its pass (ie second node)
            node_right = print_passes_processed[pass_of_disconnected_node][(index+1)]
            # only connect neighbor (j) if not already connected to node (i)
            if node_right != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)            


# Last processing step to ensure only true disconnects remain
to_pop_disconnects = {}
for i in neighbor_locs:
  passnumber = final_true_disconnect[i][0] # pass of potentially disconnected node
  indexnumber = print_passes_processed[passnumber].index(i) # index of potentially disconnected node in its pass
  # if only one node
  if (len(print_passes_processed[passnumber]) == 1):
    # print(f' only one node {i}')
    continue
  # if first node
  if (indexnumber == 0) and (len(print_passes_processed[passnumber]) > 0):  # is 0 here for non-empty []
    rightindex = indexnumber+1
    if print_passes_processed[passnumber][rightindex] == neighbor_to_connect[i][0]:
      with open('changelog.txt', 'a') as f:
        f.write(f'\n{neighbor_to_connect[i][0]} not actually disconnected.')
      f.close()
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)
  # if last node
  if (indexnumber+1 == len(print_passes_processed[passnumber])) and (len(print_passes_processed[passnumber]) > 0):  # is 0 here for non-empty []
    leftindex = indexnumber-1
    if print_passes_processed[passnumber][leftindex] == neighbor_to_connect[i][0]:
      with open('changelog.txt', 'a') as f:
        f.write(f'\n{neighbor_to_connect[i][0]} not actually disconnected.')
      f.close()
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)


# Check for any instances in which the first and last node of the same print 
# pass get reciprocally joined to each other, and make it so that only the last 
# node gets joined to the first (not the first to the last)

still_check = {}
tracker = 0
for i in final_true_disconnect:
  pass_to_check = final_true_disconnect[i][0]
  # if the print_pass of the disconnected node is the same as the print_pass of its neighbor (the node to which it joins)
  if final_true_disconnect[i] == neighbor_locs[i]:
    # if first node of pass (only two nodes will be checked for a given print pass - the first and last)
    if (tracker % 2 == 0):
      # save a list of these nodes, sorted by print pass
      still_check[pass_to_check] = []
      still_check[pass_to_check].append(i)      
      # update tracker
      tracker = len(still_check[pass_to_check])
    # if last node of pass (only two nodes will be checked for a given print pass - the first and last)
    elif (tracker % 2 == 1): # don't need to initialize
      still_check[pass_to_check].append(i)    
      tracker == 0
      # update tracker
      tracker = len(still_check[pass_to_check])

for i in (still_check):
  # if two nodes to connect in same print pass
  if len(still_check[i]) == 2:
    node = still_check[i][0]
    next_node = still_check[i][1]
    # if graphical neighbors
    if next_node in graph[node]:
      if neighbor_to_connect[node][0] == next_node:
        # if node is first node of pass and next_node is last node of pass
        if (node == print_passes_processed[i][0]) and (next_node == print_passes_processed[i][-1]):
          with open('changelog.txt', 'a') as f:
            f.write(f'\nfor print pass {i}, not going to append {next_node} to {node} at start of pass because {node} will get appended to last node {next_node}.')
          f.close()
          to_pop_disconnects[node] = []
          to_pop_disconnects[node].append(node)

for i in to_pop_disconnects:
  final_true_disconnect.pop(i)
  neighbor_locs.pop(i)
  neighbor_to_connect.pop(i)
  neighbor_index.pop(i)

# Print summary table of remaining disconnected nodes
with open('changelog.txt', 'a') as f:
  f.write('\n')
  f.write('Summary of remaining disconnects:                         Join to:')
  f.write('\n-----------------------------------------------------     --------------------')
  for i in neighbor_locs:
    f.write(f'\nNode {i} is in pass {final_true_disconnect[i][0]} and disconnected from pass {neighbor_locs[i][0]}.        {neighbor_to_connect[i][0]} at index {neighbor_index[i][0]}')
  f.write('\n-----------------------------------------------------     --------------------')
  f.write('\n\nNumber of disconnects: ')
  f.write(str(len(final_true_disconnect)))
  f.write('\n\n################################################################################')
f.close()  

######################################################## Final Gap Closure ###########################################################


with open('changelog.txt', 'a') as f:
  f.write('\n\nNow running Final Gap Closure.\n')
f.close()

# Close gaps identified in most recent changelog (following branchpoint condition #3)

# These gaps typically take the form of gaps between standard-node endpoints and 
# parent branch points embedded within existing print passes.

start_append = {}
end_append = {}
for i in final_true_disconnect:
  passnum = final_true_disconnect[i][0]
  index = print_passes_processed[passnum].index(i)
  # if first node
  if index == 0:
    if (len(print_passes_processed[passnum])>1):
      if (print_passes_processed[passnum][index+1] != neighbor_to_connect[i][0]):
        start_append[passnum] = []
        start_append[passnum].append(neighbor_to_connect[i][0])
    elif (len(print_passes_processed[passnum])==1):
      start_append[passnum] = []
      start_append[passnum].append(neighbor_to_connect[i][0])
    elif (len(print_passes_processed[passnum])==0):
      start_append[passnum] = []
      start_append[passnum].append(neighbor_to_connect[i][0])  
  # if last node
  if index == (len(print_passes_processed[passnum])-1):
    if (len(print_passes_processed[passnum])>1):
      if (print_passes_processed[passnum][index-1] != neighbor_to_connect[i][0]):
        end_append[passnum] = []
        end_append[passnum].append(neighbor_to_connect[i][0])
    elif (len(print_passes_processed[passnum])==1):
      start_append[passnum] = []
      start_append[passnum].append(neighbor_to_connect[i][0])
    elif (len(print_passes_processed[passnum])==0):
      end_append[passnum] = []
      end_append[passnum].append(neighbor_to_connect[i][0])  

# print('start append')
# print(start_append)
# print('end append')
# print(end_append)

# Update print_passes_processed (final gaps)
for i in start_append:
  print_passes_processed[i].insert(0,start_append[i][0])
  with open('changelog.txt', 'a') as f:
    f.write(f'\nAppending node {start_append[i][0]} to start of pass {i}.')
  f.close()
for i in end_append:
  print_passes_processed[i].append(end_append[i][0])
  with open('changelog.txt', 'a') as f:
    f.write(f'\nAppending node {end_append[i][0]} to end of pass {i}.')
  f.close()


################################################### Changelog 5: Final Gap Closure #######################################################

# This cell of code checks for POTENTIALLY disconnected endpoints (i.e. 
# endpoints which only occur once as an endpoint, meaning that no other endpoint
# joins to them) and creates a CHANGELOG of ACTUALLY disconnected points.

# Create list of all endpoints of print_passes_processed
processed_endpoints = []
single_node_in_pass = []
for i in print_passes_processed:
  # if only one coordinate in the pass, only add once
  if len(print_passes_processed[i])==1:
    processed_endpoints.append(print_passes_processed[i][0])
    single_node_in_pass.append(print_passes_processed[i][0])
  else:
    processed_endpoints.append(print_passes_processed[i][0])
    processed_endpoints.append(print_passes_processed[i][-1])

# print('Endpoints of print_passes_processed:')
# print(processed_endpoints)
# print('\n')

# print(f'Single node in pass: {single_node_in_pass}')

pass_counter = 0
disconnected = []
for i in processed_endpoints:
  pass_counter += 1 
  if processed_endpoints.count(i) == 1:
    disconnected.append(i)


# Exclude inlets/outlets and endpoints of original vessels
to_remove = []
for i in disconnected:
  # exclude endpoints of original vessels (includes inlets/outlets), UNLESS that endpoint is the only node in its pass
  if (i in endpoint_nodes) and (i not in single_node_in_pass):
    to_remove.append(i)
    # print(f'popping {i}')
for i in to_remove:
  disconnected.remove(i)


# Initialize
potential_disconnect = {}
for i in disconnected:
  potential_disconnect[i] = []

# Checking the potentially disconnected endpoints for connection to other parts 
# of the print_passes (e.g., a node within a previous pass may join to where the
# endpoint of a different pass begins; these are not truly disconnected endpoints)

true_disconnected = []
true_disconnected_pass = {}
for i in print_passes_processed:
  for potentially_disconnected_node in disconnected:
    disconnect_count = 0 # reset for iteration
    if potentially_disconnected_node in print_passes_processed[i]:
      # check against other print passes
      for m in range(0,len(print_passes_processed)):
        if potentially_disconnected_node in print_passes_processed[m]:
          # print(f'i: {i}, disconnected: {potentially_disconnected_node}, m: {m}')
          potential_disconnect[potentially_disconnected_node].append(m)

# Remove duplicates
for i in potential_disconnect:
  potential_disconnect[i] = [*set(potential_disconnect[i])]

# print('Note: the dictionaries below have the format NODE: [PRINT_PASS], where 
# print_pass is the pass(es) in which the node appears.')

# print('\nPotential disconnects:')
# print(potential_disconnect)

# Find true disconnects (endpoint only appears once, within its own vessel)
final_true_disconnect = {}
for i in potential_disconnect:
  if len(potential_disconnect[i]) == 1:
    final_true_disconnect[i] = potential_disconnect[i]


# print('\nFinal true disconnected nodes (format NODE: [PRINT_PASS OF NODE])')
# print(final_true_disconnect)
# print('\n')


# Locate neighbors of disconnected nodes in the network
neighbor_locs = {}
neighbor_nodes = {}
neighbor_index = {}
neighbor_to_connect = {}
for i in final_true_disconnect:
  neighbor_nodes = graph[i]
  # print(f'i is {i}, neighbor_nodes are {neighbor_nodes}')
  neighbor_locs[i] = []
  neighbor_index[i] = []
  neighbor_to_connect[i] = []

  # for each neighbor (j) of the disconnected node (i)
  for j in neighbor_nodes:
    # if the neighbor is not the disconnected node itself
    if j != i:
      # within each print_pass
      for passNum in print_passes_processed:
        # get the pass of the disconnected node (i)
        pass_of_disconnected_node = final_true_disconnect[i][0]

        # [1] if neighbor (j) in DIFF print_pass as node (i)
        if j in print_passes_processed[passNum] and passNum!=pass_of_disconnected_node: #: i.e., if currently in pass of the neighbor (j) and that pass is different from pass of disconnected node (i); i.e. have found the non-self print_pass containing neighbor 
          # store pass number of the non-self neighbor (j)
          neighbor_locs[i].append(passNum)
          # store index of the neighbor (j) within its own print_pass
          neighbor_index[i].append(print_passes_processed[passNum].index(j))
          # store the nodal identity of neighbor j
          neighbor_to_connect[i].append(j)

        # [2] if neighbor (j) in SAME print_pass as node (i)  
        if j in print_passes_processed[passNum] and passNum==pass_of_disconnected_node:
          # index of disconnected node (i) in its pass
          index = print_passes_processed[passNum].index(i)

          # [2A] if disconnected node (i) is LAST node of its pass
          if index==len(print_passes_processed[passNum])-1:
            # get node to "left" of disconnected node (i) in its pass (ie second-to-last node)
            node_left = print_passes_processed[passNum][(index-1)]
            # only connect neighbor (j) if not already connected to node (i) (ie if not already next to each other in the print_pass)
            if node_left != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)

          # [2B] if disconnected node (i) is FIRST node of its pass
          if index == 0:
            # get node to "right" of disconnected node (i) in its pass (ie second node)
            node_right = print_passes_processed[pass_of_disconnected_node][(index+1)]
            # only connect neighbor (j) if not already connected to node (i)
            if node_right != j:
              # store pass number of (i) and (j), which is the same
              neighbor_locs[i].append(passNum)
              # store index of the neighbor (j) within the print_pass
              neighbor_index[i].append(print_passes_processed[passNum].index(j))
              # store the nodal identity of neighbor (j)
              neighbor_to_connect[i].append(j)            


# Last processing step to ensure only true disconnects remain
to_pop_disconnects = {}
for i in neighbor_locs:
  passnumber = final_true_disconnect[i][0] # pass of potentially disconnected node
  indexnumber = print_passes_processed[passnumber].index(i) # index of potentially disconnected node in its pass
  # if only one node
  if (len(print_passes_processed[passnumber]) == 1):
    # print(f' only one node {i}')
    continue
  # if first node
  if (indexnumber == 0) and (len(print_passes_processed[passnumber]) > 0):  # is 0 here for non-empty []
    rightindex = indexnumber+1
    if print_passes_processed[passnumber][rightindex] == neighbor_to_connect[i][0]:
      with open('changelog.txt', 'a') as f:
        f.write(f'\n{neighbor_to_connect[i][0]} not actually disconnected.')
      f.close()
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)
  # if last node
  if (indexnumber+1 == len(print_passes_processed[passnumber])) and (len(print_passes_processed[passnumber]) > 0):  # is 0 here for non-empty []
    leftindex = indexnumber-1
    if print_passes_processed[passnumber][leftindex] == neighbor_to_connect[i][0]:
      with open('changelog.txt', 'a') as f:
        f.write(f'\n{neighbor_to_connect[i][0]} not actually disconnected.')
      f.close()
      to_pop_disconnects[i] = []
      to_pop_disconnects[i].append(i)

# Check for any instances in which the first and last node of the same print 
# pass get reciprocally joined to each other, and make it so that only the last 
# node gets joined to the first (not the first to the last)

# print(f'final is')
# print(final_true_disconnect)

still_check = {}
tracker = 0
for i in final_true_disconnect:
  pass_to_check = final_true_disconnect[i][0]
  # print(f'pass_to_check is {pass_to_check}')
  # if the print_pass of the disconnected node is the same as the print_pass of its neighbor (the node to which it joins)
  if final_true_disconnect[i] == neighbor_locs[i]:
    # if neighbors
    # print(f'final_true_disconnect[i] == neighbor_locs[i]: {final_true_disconnect[i]} == {neighbor_locs[i]} ')
    # if first node of pass (only two nodes will be checked for a given print pass - the first and last)
    if (tracker % 2 == 0):
      # save a list of these nodes, sorted by print pass
      still_check[pass_to_check] = []
      still_check[pass_to_check].append(i)      
      # update tracker
      tracker = len(still_check[pass_to_check])
    # if last node of pass (only two nodes will be checked for a given print pass - the first and last)
    elif (tracker % 2 == 1): # don't need to initialize
      still_check[pass_to_check].append(i)    
      tracker == 0
      # update tracker
      tracker = len(still_check[pass_to_check])

for i in (still_check):
  # if two nodes to connect in same print pass
  if len(still_check[i]) == 2:
    node = still_check[i][0]
    next_node = still_check[i][1]
    # if graphical neighbors
    if next_node in graph[node]:
      if neighbor_to_connect[node][0] == next_node:
        # if node is first node of pass and next_node is last node of pass
        if (node == print_passes_processed[i][0]) and (next_node == print_passes_processed[i][-1]):
          with open('changelog.txt', 'a') as f:
            f.write(f'\nfor print pass {i}, not going to append {next_node} to {node} at start of pass because {node} will get appended to last node {next_node}.')
          f.close()
          to_pop_disconnects[node] = []
          to_pop_disconnects[node].append(node)
          # print(f'to_pop_disconnects[node] is {to_pop_disconnects[node]}') 

for i in to_pop_disconnects:
  final_true_disconnect.pop(i)
  neighbor_locs.pop(i)
  neighbor_to_connect.pop(i)
  neighbor_index.pop(i)


# print('\nNumber of disconnects:')
# print(len(final_true_disconnect))

# for passNum in print_passes_processed:
#   print(f'Pass {passNum} | {print_passes_processed[passNum]}')

################################################# Post-Processing: Final Removal Step ####################################################

to_remove = []
for i in print_passes_processed:
  if print_passes_processed[i][0] == (arbitrary_val):
    to_remove.append(i)
    with open('changelog.txt', 'a') as f:
      f.write('\nRemoving non-relevant pass (artifact from processing) {i}.')
    f.close()

for i in to_remove:
  print_passes_processed.pop(i)

print_passes_processed_copy = print_passes_processed
print_passes_processed = {}

counter = 0
for i in print_passes_processed_copy:
  print_passes_processed[counter] = print_passes_processed_copy[i]
  counter +=1

# Print output
print('\nFinal Gap Closure completed.\n')

with open('changelog.txt', 'a') as f:
  f.write('\n\nFinal Gap Closure completed.\n')
f.close()

############################################

# Print summary table of remaining disconnected nodes
with open('changelog.txt', 'a') as f:
  f.write('\n')
  f.write('Summary of remaining disconnects:                         Join to:')
  f.write('\n-----------------------------------------------------     --------------------')
  for i in neighbor_locs:
    f.write(f'\nNode {i} is in pass {final_true_disconnect[i][0]} and disconnected from pass {neighbor_locs[i][0]}.        {neighbor_to_connect[i][0]} at index {neighbor_index[i][0]}')
  f.write('\n-----------------------------------------------------     --------------------')
  f.write('\n\nNumber of disconnects: ')
  f.write(str(len(final_true_disconnect)))
  f.write('\n\n################################################################################')
f.close()  


############################################


# Outputting the final processed print passes to the changelog
with open('changelog.txt', 'a') as f:
  # Print final print passes
  f.write('\n\nFinal print passes, single material (before any downsampling or overlapping):\n\n')
  for passNum in print_passes_processed:
    f.write(f'Pass {passNum} \n{print_passes_processed[passNum]}')
    f.write('\n\n')
f.close()

with open('changelog.txt', 'a') as f:
  f.write('\nNow plotting final print passes (single material) - saved to outputs folder.\n')
f.close()


##### Output to terminal #####
print('\nGap closure completed. Now plotting final print passes (single material).\n')


############################################### Plot: Final Print Passes (Single Material) ##############################################

if plots == 1:

  x = {}
  y = {}
  z = {}
  for i in print_passes_processed:
    x[i] = []
    y[i] = []
    z[i] = []
    for j in print_passes_processed[i]:
      x[i].append(points_array[j][0])
      y[i].append(points_array[j][1])
      z[i].append(points_array[j][2])

  fig = go.Figure()
  fig = go.Figure(layout_title_text = 'Single Material')
  config = dict({'scrollZoom': True})
  for i in x:
    fig.add_trace(go.Scatter3d(x=x[i], y=y[i], z=z[i]))
    fig.update_traces(marker_size = 2)
    fig.update_layout(title_x=0.5)

  # Create and add slider
  steps = []
  for i in range(len(fig.data)):
      step = dict(
          method="update",
          args=[{"visible": [False] * len(fig.data)},
                {"title": "Single Material <br>[Print Pass: " + str(i) + "]"}],  
      )
      for j in range(0,i+1):
        step["args"][0]["visible"][j] = True
      steps.append(step)

  sliders = [dict(
      currentvalue={"prefix": "Print pass: "},
      steps=steps
  )]

  fig.update_layout(
      sliders=sliders,
      margin=dict(l=30, r=30, t=30, b=30),
    title_x=0.5
  )

  fig.update_scenes(aspectmode='cube')

  # Store output graphs
  fig.write_html(f'outputs/network_SM.html') 

############################################### Optional: downsampling to decrease print resolution ###############################################

print_passes_processed_downsample = {}

if downsample == 1:

  print('Plotting completed. Now downsampling network.\n')

  for i in range(0,len(print_passes_processed)):
    print_passes_processed_downsample[i] = []
    passlen = len(print_passes_processed[i])
    if passlen > 3:
      for j in range(0,len(print_passes_processed[i])):
        # if first or last node
        if j == 0 or j == len(print_passes_processed[i])-1:
          print_passes_processed_downsample[i].append(print_passes_processed[i][j])
        # if parent or daughter node
        elif (print_passes_processed[i][j] in branchpoint_list) or (print_passes_processed[i][j] in branchpoint_list_keys):
          print_passes_processed_downsample[i].append(print_passes_processed[i][j])  
        # if endpoint node
        elif (print_passes_processed[i][j]) in endpoint_nodes:
          print_passes_processed_downsample[i].append(print_passes_processed[i][j])  
        # otherwise
        else:
          if j%downsample_factor == 0:   
            print_passes_processed_downsample[i].append(print_passes_processed[i][j])
    else:
      print_passes_processed_downsample[i] = print_passes_processed[i]


  # Update print_passes_processed to downsampled version
  print_passes_processed = {}
  print_passes_processed = copy.deepcopy(print_passes_processed_downsample)

  print('Downsampling completed. Now plotting downsampled network.')


else:
  print('Plotting completed.\n')



########################################### Plot: Final Print Passes (Single Material, Downsampled Version) ##########################################

if plots == 1 and downsample == 1:

  x = {}
  y = {}
  z = {}
  for i in print_passes_processed:
    x[i] = []
    y[i] = []
    z[i] = []
    for j in print_passes_processed[i]:
      x[i].append(points_array[j][0])
      y[i].append(points_array[j][1])
      z[i].append(points_array[j][2])

  fig = go.Figure()
  fig = go.Figure(layout_title_text = 'Single Material (Downsampled)')
  config = dict({'scrollZoom': True})
  for i in x:
    fig.add_trace(go.Scatter3d(x=x[i], y=y[i], z=z[i]))
    fig.update_traces(marker_size = 2)
    fig.update_layout(title_x=0.5)

  # Create and add slider
  steps = []
  for i in range(len(fig.data)):
      step = dict(
          method="update",
          args=[{"visible": [False] * len(fig.data)},
                {"title": "Single Material <br>[Print Pass: " + str(i) + "]"}],  
      )
      for j in range(0,i+1):
        step["args"][0]["visible"][j] = True
      steps.append(step)

  sliders = [dict(
      currentvalue={"prefix": "Print pass: "},
      steps=steps
  )]

  fig.update_layout(
      sliders=sliders,
      margin=dict(l=30, r=30, t=30, b=30),
    title_x=0.5
  )

  fig.update_scenes(aspectmode='cube')

  # Store output graphs
  fig.write_html(f'outputs/network_downsampled_SM.html') 

  print('Plotted downsampled network.\n')

################################################## Preserve print passes for single material ############################################

with open('changelog.txt', 'a') as f:
  f.write('\nNow copying print_passes_processed to print_passes_processed_SM.\n')
f.close()

print_passes_processed_SM = copy.deepcopy(print_passes_processed)

##################################################### Multi-material (Arterial vs. Venous) #########################################################

##### Pre-processing of vessel type #####

if multimaterial == 1:

  print('\nNow generating passes for multi-material printing (arterial vs venous).')

  print_passes_processed_artven = {}
  for i in range(0, len(print_passes_processed)):
    print_passes_processed_artven[i] = []
    for j in print_passes_processed[i]:
      print_passes_processed_artven[i].append(points_array[j, 4])
  with open('changelog.txt', 'a') as f:
    f.write('\n################################################################################')
    f.write('\n\nVessel types within each print pass:\n')
    for i in print_passes_processed_artven:
      f.write(f'\n\nPass {i}\n')
      f.write(str(print_passes_processed_artven[i]))
      f.write('\n')
  f.close()
  # for i in print_passes_processed:
  #   print(f'Pass {i}')
  #   print(print_passes_processed[i])
  print_passes_processed_artven_predivis = print_passes_processed_artven
  print_passes_processed_predivis = print_passes_processed

  with open('changelog.txt', 'a') as f:
    f.write('\n\nNow swapping vessel types for these cases:')
    f.write('\n1. The vessel type of the first node in the pass differs from the vessel type of the following nodes.')
    f.write('\n2. The vessel type of the last node in the pass differs from the vessel type of the preceding nodes.')
    f.write('\n3. The vessel type of an individual node within the pass differs from the vessel type of its two bordering neighbor nodes.')
    f.write('\n4. There are only two nodes in the pass and their vessel types differ. In this case, arbitrarily set the vessel type of the first node equal to the vessel type of the second node.')
    f.write('\n\n')
    f.write('These nodes were swapped:\n')
  f.close()

  
  for i in print_passes_processed_artven:
    for j in range(0, len(print_passes_processed_artven[i])):
      curr_node_artven = print_passes_processed_artven[i][j]
      # If at least 3 nodes in the print pass
      if len(print_passes_processed_artven[i]) > 2:
        # if first node in pass
        if j == 0:
          next_node_artven = print_passes_processed_artven[i][1]
          next_next_node_artven = print_passes_processed_artven[i][2]
          # Swap if only first node is different
          if (next_node_artven == next_next_node_artven) and (curr_node_artven != next_node_artven):
            #print(f'i is {i}, j is {j}')
            #print(f'curr_node_artven is {curr_node_artven}')
            #print(f'prev_node_artven is {prev_node_artven}')
            #print(f'next_node_artven is {next_node_artven}')     
            print_passes_processed_artven[i][j] = next_node_artven
            #print(f'curr_node_artven was {curr_node_artven} and is now {print_passes_processed_artven[i][j]}.')
            with open('changelog.txt', 'a') as f:
              f.write(f'\nNode {j} in pass {i} was swapped from {curr_node_artven} to {print_passes_processed_artven[i][j]}.')         
            f.close()  
        # if last node in pass
        elif j == len(print_passes_processed[i])-1:
          #print('on the last node')
          prev_node_artven = print_passes_processed_artven[i][-2]
          prev_prev_node_artven = print_passes_processed_artven[i][-3]
          # Swap if only last node is different
          if (prev_node_artven == prev_prev_node_artven) and (curr_node_artven != prev_node_artven):
            #print(f'i is {i}, j is {j}')
            #print(f'curr_node_artven is {curr_node_artven}')
            #print(f'prev_node_artven is {prev_node_artven}')
            #print(f'next_node_artven is {next_node_artven}')        
            print_passes_processed_artven[i][j] = prev_node_artven
            #print(f'curr_node_artven was {curr_node_artven} and is now {print_passes_processed_artven[i][j]}.')
            with open('changelog.txt', 'a') as f:
              f.write(f'\nNode {j} in pass {i} was swapped from {curr_node_artven} to {print_passes_processed_artven[i][j]}.')
            f.close()            
        # If neither first nor last node in pass 
        else: 
          prev_node_artven = print_passes_processed_artven[i][j+1]
          next_node_artven = print_passes_processed_artven[i][j-1]
          # SWAP NODES
          if (prev_node_artven == next_node_artven) and (prev_node_artven != curr_node_artven):
            #print(f'i is {i}, j is {j}')
            #print(f'curr_node_artven is {curr_node_artven}')
            #print(f'prev_node_artven is {prev_node_artven}')
            #print(f'next_node_artven is {next_node_artven}')
            print_passes_processed_artven[i][j] = prev_node_artven
            #print(f'curr_node_artven was {curr_node_artven} and is now {print_passes_processed_artven[i][j]}.')
            with open('changelog.txt', 'a') as f:
              f.write(f'\nNode {j} in pass {i} was swapped from {curr_node_artven} to {print_passes_processed_artven[i][j]}.')    
            f.close()       
      # If only 2 nodes in the print pass
      elif 1 < len(print_passes_processed_artven[i]) <= 2: 
        # If the two nodes are not the same vessel type, set them as the same
        if print_passes_processed_artven[0] != print_passes_processed_artven[1]:
          print_passes_processed_artven[0] == print_passes_processed_artven[1]
          with open('changelog.txt', 'a') as f:
            f.write(f'\nNode {print_passes_processed[i][j]} in pass {i} was swapped from {print_passes_processed_artven[0]} to {print_passes_processed_artven[1]}.')
          f.close()
        continue
      # If only 1 node in the print pass
      else: 
        continue


  # Print output
  with open('changelog.txt', 'a') as f:
    f.write('\n')
    f.write('\nFollowing swapping, the vessel types of the print passes are:\n')
    for i in print_passes_processed_artven:
      f.write(f'\nPass {i}\n')
      f.write(str(print_passes_processed_artven[i]))
      f.write('\n')
  f.close()

##### Arterial-Venous #####

# Only execute this block of code if printing multimaterial
if multimaterial == 1:

  # Find break points
  break_points = {}
  for i in print_passes_processed_artven:
    #counter = 0
    breaks = []
    for j in range(0,len(print_passes_processed_artven[i])):
      curr_node_artven = print_passes_processed_artven[i][j]
      # if only one node in print pass 
      if len(print_passes_processed_artven[i]) == 1:
        continue
      # if only two nodes in print pass
      elif len(print_passes_processed_artven[i]) == 2:
        continue
      # if at least 3 nodes in print pass
      else:
        # if first node
        if j == 0:
          next_node_artven = print_passes_processed_artven[i][j+1]
          # if type of first node differs from next node (it shouldn't, due to the prior subdivision), then break
          if next_node_artven != curr_node_artven:
            breaks.append(print_passes_processed[i][j])
        # if last node
        elif j == len(print_passes_processed_artven[i])-1:
          prev_node_artven = print_passes_processed_artven[i][j-1]
          # if type of last node differs from prev node (it shouldn't, due to the prior subdivision), then break
          if prev_node_artven != curr_node_artven:
            breaks.append(print_passes_processed[i][j])
        # if middle node
        else:          
          prev_node_artven = print_passes_processed_artven[i][j-1]
          next_node_artven = print_passes_processed_artven[i][j+1]
          # if current node doesn't match previous node, break
          if (curr_node_artven != prev_node_artven):
            breaks.append(print_passes_processed[i][j])
        # Store the breakpoints
        break_points[i] = breaks

  # Print the breakpoints
  # print('\n')
  # print(f' break points are: {break_points}')


  # Divide into new passes
  new_matrix = {}
  new_matrix_artven = {}
  for i in break_points:
    if break_points[i]: # if not empty
      new_passes = {}
      new_passes_artven = {}
      start = 0
      counter = -1
      check = 0
      for j in break_points[i]:
        total = len(break_points[i])
        # track 
        counter += 1
        check += 1
        # If first breakpoint (j) in list of breakpoints for pass i
        if counter == 0:
          # if >1 breakpoint
          if total > 1:
            end = print_passes_processed[i].index(j) # update 'end' index for current iteration
            new_passes[counter] = print_passes_processed[i][start:end] # not necessary to include "-1" (see below) for first new pass
            new_passes_artven[counter] = print_passes_processed_artven[i][start:end]
            start = end # update 'start' index for next iteration
          # if only 1 breakpoint
          else:
            end = print_passes_processed[i].index(j) # update 'end' index for current iteration
            new_passes[counter] = print_passes_processed[i][start:end] # not necessary to include "-1" (see below)
            new_passes_artven[counter] = print_passes_processed_artven[i][start:end]
            start = end # update 'start' index for next iteration
            end = len(print_passes_processed[i]) # update 'end' index for current iteration
            new_passes[check] = print_passes_processed[i][start-1:end]
            new_passes_artven[check] = print_passes_processed_artven[i][start-1:end]            
        # if not the first breakpoint (j)
        else:
          # if last breakpoint in list of breakpoints for pass i
          if counter == (total-1):
            end = print_passes_processed[i].index(j) # update 'end' index for current iteration
            new_passes[counter] = print_passes_processed[i][start-1:end]
            new_passes_artven[counter] = print_passes_processed_artven[i][start-1:end]
            start = end # update 'start' index for next iteration
            end = len(print_passes_processed[i]) # update 'end' index for current iteration
            new_passes[check] = print_passes_processed[i][start-1:end]
            new_passes_artven[check] = print_passes_processed_artven[i][start-1:end]
          # if not the last breakpoint in list of breakpoints for pass i
          else:
            end = print_passes_processed[i].index(j) # update 'end' index for current iteration
            new_passes[counter] = print_passes_processed[i][start-1:end] # the "-1" ensures that the new pass starts where the previous one ended (prevents ink gaps)
            new_passes_artven[counter] = print_passes_processed_artven[i][start-1:end]
            start = end # update 'start' index for next iteration
      # Store in new arrays
      new_matrix[i] = new_passes
      new_matrix_artven[i] = new_passes_artven

  # Print new passes
  # print('New passes')
  # print(new_matrix)
  # print('\n New passes (artven)')
  # print(new_matrix_artven)

  # Number of new passes to add
  num_new = 0
  for i in new_matrix:
    num_new = len(new_matrix[i]) + num_new
  num_new = num_new - len(new_matrix)
  num_total = len(print_passes_processed) + num_new

  # Building a dictionary for print passes; can do by keys (unordered)
  counter = 0
  counter_old = 0
  counter_new = 0
  print_passes_processed_final ={}
  while counter < num_total:
    if counter_old in new_matrix:
      num_to_add = 0 # initialize
      while num_to_add < len(new_matrix[counter_old]):
        print_passes_processed_final[counter] = new_matrix[counter_old][num_to_add]
        counter += 1
        num_to_add += 1
      counter_old += 1
    else:
      print_passes_processed_final[counter] = print_passes_processed[counter_old]
      counter += 1
      counter_old += 1

  # print(print_passes_processed)
  # print(print_passes_processed_final)

  # Building a dictionary for print passes; can do by keys (unordered)
  counter = 0
  counter_old = 0
  counter_new = 0
  print_passes_processed_final_artven ={}
  while counter < num_total:
    if counter_old in new_matrix_artven:
      num_to_add = 0 # initialize
      while num_to_add < len(new_matrix_artven[counter_old]):
        print_passes_processed_final_artven[counter] = new_matrix_artven[counter_old][num_to_add]
        counter += 1
        num_to_add += 1
      counter_old += 1
    else:
      print_passes_processed_final_artven[counter] = print_passes_processed_artven[counter_old]
      counter += 1
      counter_old += 1

  # print(print_passes_processed_artven)
  # print(print_passes_processed_final_artven)

  # Arterial_Venous
  print_passes_processed = print_passes_processed_final
  print_passes_processed_artven = print_passes_processed_final_artven

  # Print output
  with open('changelog.txt', 'a') as f:
    f.write('\n\nSubdivided multi-material passes (vessel type): \n')
    for i in print_passes_processed_artven:
      f.write(f'\nPass {i}\n')
      f.write(str(print_passes_processed_artven[i]))
      f.write('\n')
  f.close()

  with open('changelog.txt', 'a') as f:
    f.write('\n\nSubdivided multi-material passes (nodes): \n\n')
    for i in print_passes_processed:
      f.write(f'\nPass {i}\n')
      f.write(str(print_passes_processed[i]))
      f.write('\n')
  f.close()

  # Note: even though it may look like there are some passes where the first node is a different type, 
  # it will NOT print this way - this is because the code repeats shared endnodes where necessary to 
  # avoid gaps.

  with open('changelog.txt', 'a') as f:
    f.write('\nThe vessel types, by print pass, are as follows:')
    for i in print_passes_processed_artven:
      if print_passes_processed_artven[i][-1] != 0:
        f.write(f'\nPass {i} is arterial')
      else:
        f.write(f'\nPass {i} is venous')
  f.close()

  print('\nGenerated passes for multi-material. Now plotting final print passes for multi-material network.')

# If not printing multi-material
else:
  print('\nskipping this block (printing single material, not multi-material)')


########################################### Plot: Final Print Passes (Arterial vs. Venous) ##########################################

if plots == 1 and multimaterial == 1:

  x = {}
  y = {}
  z = {}
  for i in print_passes_processed:
    x[i] = []
    y[i] = []
    z[i] = []
    for j in print_passes_processed[i]:
      x[i].append(points_array[j][0])
      y[i].append(points_array[j][1])
      z[i].append(points_array[j][2])


  color_array = []
  for i in print_passes_processed_artven:
    if print_passes_processed_artven[i][-1] == 0:
      color_array.append("blue")
    else:
      color_array.append("crimson")

  fig = go.Figure()
  if downsample == 1:
    fig = go.Figure(layout_title_text = 'Arterial vs Venous (Downsampled)')
  else:
    fig = go.Figure(layout_title_text = 'Arterial vs Venous')
  config = dict({'scrollZoom': True})


  for i in x:
    fig.add_trace(go.Scatter3d(x=x[i], y=y[i], z=z[i], line_color=color_array[i]))
    fig.update_traces(marker_size = 2)
    fig.update_layout(title_x=0.5)

  # Create and add slider
  steps = []
  for i in range(len(fig.data)):
      step = dict(
          method="update",
          args=[{"visible": [False] * len(fig.data)},
                {"title": "Arterial vs Venous <br>[Print Pass: " + str(i) + "]"}],  # layout attribute
      )
      for j in range(0,i+1):
        step["args"][0]["visible"][j] = True  # Toggle i'th trace to "visible"
      steps.append(step)

  sliders = [dict(
      currentvalue={"prefix": "Print pass: "},
      steps=steps
  )]

  fig.update_layout(
      sliders=sliders,
      margin=dict(l=30, r=30, t=30, b=30),
      title_x=0.5
  )

  fig.update_scenes(aspectmode='cube')

  # Store output graphs
  fig.write_html(f'outputs/network_MM.html') 

  print('\nFinished plotting passes for multi-material network.')


################################################ Computation for changing vessel radius ################################################

# if user specifies "yes" for speed calculation (radius information) 
if numColumns > 3 and speed_calc == 1:

    print('\nNow computing print speeds.')

    #flow = 0.127 # mm/s; experimentally determined
    flow = 0.1609429886081009 # mm/s; experimentally determined

    radius_speed_SM = {}
    radius_speed_MM = {}

    if numColumns > 3:

      # Collect radii
      radii = points_array[:,3]

      # Compute speed based on radius
      for i in range(0, len(print_passes_processed_SM)):
        for j in print_passes_processed_SM[i]:
          radius_speed_SM[j] = flow/((radii[j]**2)*np.pi)
      for i in range(0, len(print_passes_processed)):
        for j in print_passes_processed[i]:
          radius_speed_MM[j] = flow/((radii[j]**2)*np.pi)

    print('\nFinished computing print speeds. Now generating output files.')

else:
  print('\nNow generating output files.')


############################################### Optionally adding overlap: Single Material ##########################################################


# If user specified a number of nodes by which to overlap
if num_overlap != 0:

  pass_ends_on_shared = []
  pass_with_shared = []
  common_node = []

  # Find the print passes which end on a previously-printed node
  keepTrack = 0
  with open('changelog.txt', 'a') as f:
    for i in print_passes_processed_SM:
      f.write(f'i={i}\n')
      if keepTrack == 0: # check all passes after the first one
        f.write(f'keepTrack = {keepTrack}\n')
        keepTrack = keepTrack+1
        continue
      else:
        check_last_node = print_passes_processed_SM[i][-1] # last node of print pass
        f.write(f'Checking node {check_last_node}\n')
        for j in print_passes_processed_SM:
          for k in print_passes_processed_SM[j]:
            if k == check_last_node and i != j and i>j:
              #with open('changelog.txt', 'a') as f:
              f.write(f'Node {check_last_node} in Pass {i} appears in previously-printed Pass {j}.\n')
              pass_ends_on_shared.append(i)
              pass_with_shared.append(j)
              common_node.append(check_last_node)
            else:
              continue
    f.write(f'pass_ends_on_shared {pass_ends_on_shared}\n')
    f.write(f'pass_with_shared {pass_with_shared}\n')
    f.write(f'common_node {common_node}\n')



    # Retrace nodes for gap closure (optional)
    trackPoint = 0 # tracker as we iterate through pass_ends_on_shared
    # for each item in pass_with_shared (same length as pass_ends_on_shared)
    for i in pass_with_shared:
      # if we haven't yet iterated through the entire pass_ends_on_shared list
      if trackPoint < len(pass_ends_on_shared):
        #f.write(f'len+1 = {len(pass_ends_on_shared)}\n')
        # find the index of the common_node in pass_with_shared
        idx = print_passes_processed_SM[i].index(common_node[trackPoint])
        idx_count = 0
        #f.write(f'trackPoint {trackPoint}\n')
        # if node is not first node in pass_with_shared
        if idx != 0 and idx-(idx_count+1) > 0 :
          # collect neighbors of already-printed shared node in pass containing already-printed shared node
          while idx_count < num_overlap and (idx-(idx_count+1)) >= 0:
            #f.write(f'idx {idx} idx_count {idx_count} i {i}   idx-idx_count-1   {idx-idx_count-1}\n')
            print_passes_processed_SM[pass_ends_on_shared[trackPoint]].append(print_passes_processed_SM[i][idx-(idx_count+1)])
            f.write(f'Appending node {print_passes_processed_SM[i][idx-(idx_count+1)]} from pass {pass_with_shared[trackPoint]} to pass {pass_ends_on_shared[trackPoint]}.\n')
            idx_count = idx_count+1
            #f.write(f'idx_count {idx_count}\n')
          trackPoint = trackPoint+1
          #f.write(f'trackPoint {trackPoint}\n')
        else:
          trackPoint = trackPoint+1
          #f.write(f'else trackPoint {trackPoint}\n')  
          continue
      else:
        continue

  f.close()


  with open('changelog.txt', 'a') as f:
    # Print final print passes
    f.write('\n\nFinal single material print passes (after overlap applied):\n\n')
    for passNum in print_passes_processed_SM:
      f.write(f'Pass {passNum} \n{print_passes_processed_SM[passNum]}')
      f.write('\n\n')
  f.close()


############################################### Optionally adding a gap closure file: Single Material ##########################################################

# If user specified the existence of a separate gap closure file
if close_var_SM == 1:

  # Extract list of passes to extend
  with open(f'{gap_file_SM}','r') as gapfile:
    gap_pass_SM = gapfile.readlines()
    gap_pass_SM = [int(item.rstrip()) for item in gap_pass_SM]
    with open ('changelog.txt','a') as f:
      f.write(f'\nExtend SM {gap_pass_SM}')
      f.close()
  f.close()

  # Extract amount by which to extend the print pass (deltas)
  delta_x_SM = []
  delta_y_SM = []
  delta_z_SM = []
  with open(f'{deltas_file_SM}','r') as deltafile:
    for coordLine in deltafile:
      pass_delta = coordLine.split()
      int_delta = [float(s) for s in pass_delta]
      delta_x_SM.append(int_delta[0])
      delta_y_SM.append(int_delta[1])
      delta_z_SM.append(int_delta[2])
      with open('changelog.txt','a') as f:
        f.write(f'\nFloat{int_delta}')
        f.close()
    with open('changelog.txt','a') as f:
      f.write(f'\nDelta_x_SM{delta_x_SM}')
      f.write(f'\nDelta_y_SM{delta_y_SM}')
      f.write(f'\nDelta_z_SM{delta_z_SM}')
      f.close()
  f.close()

############################################### Optionally adding a gap closure file: Multimaterial ##########################################################

# If user specified the existence of a separate gap closure file
if close_var_MM == 1:

  # Extract list of passes to extend
  with open(f'{gap_file_MM}','r') as gapfile:
    gap_pass_MM = gapfile.readlines()
    gap_pass_MM = [int(item.rstrip()) for item in gap_pass_MM]
    with open ('changelog.txt','a') as f:
      f.write(f'\nExtend MM {gap_pass_MM}')
      f.close()
  f.close()

  # Extract amount by which to extend the print pass (deltas)
  delta_x_MM = []
  delta_y_MM = []
  delta_z_MM = []
  with open(f'{deltas_file_MM}','r') as deltafile:
    for coordLine in deltafile:
      pass_delta = coordLine.split()
      int_delta = [float(s) for s in pass_delta]
      delta_x_MM.append(int_delta[0])
      delta_y_MM.append(int_delta[1])
      delta_z_MM.append(int_delta[2])
      with open('changelog.txt','a') as f:
        f.write(f'\nFloat{int_delta}')
        f.close()
    with open('changelog.txt','a') as f:
      f.write(f'\nDelta_x_MM{delta_x_MM}')
      f.write(f'\nDelta_y_MM{delta_y_MM}')
      f.write(f'\nDelta_z_MM{delta_z_MM}')
      f.close()
  f.close()



############################################### Optionally adding overlap: Multimaterial ##########################################################

# If multimaterial specified
if multimaterial == 1:

  # If user specified a number of nodes by which to overlap
  if num_overlap != 0:

    pass_ends_on_shared = []
    pass_with_shared = []
    common_node = []

    # Find the print passes which end on a previously-printed node
    keepTrack = 0
    with open('changelog.txt', 'a') as f:
      for i in print_passes_processed:
        f.write(f'i={i}\n')
        if keepTrack == 0: # check all passes after the first one
          f.write(f'keepTrack = {keepTrack}\n')
          keepTrack = keepTrack+1
          continue
        else:
          check_last_node = print_passes_processed[i][-1] # last node of print pass
          f.write(f'Checking node {check_last_node}\n')
          for j in print_passes_processed:
            for k in print_passes_processed[j]:
              if k == check_last_node and i != j and i>j:
                #with open('changelog.txt', 'a') as f:
                f.write(f'Node {check_last_node} in Pass {i} appears in previously-printed Pass {j}.\n')
                pass_ends_on_shared.append(i)
                pass_with_shared.append(j)
                common_node.append(check_last_node)
              else:
                continue
      f.write(f'pass_ends_on_shared {pass_ends_on_shared}\n')
      f.write(f'pass_with_shared {pass_with_shared}\n')
      f.write(f'common_node {common_node}\n')



      # Retrace nodes for gap closure (optional)
      trackPoint = 0 # tracker as we iterate through pass_ends_on_shared
      # for each item in pass_with_shared (same length as pass_ends_on_shared)
      for i in pass_with_shared:
        # if we haven't yet iterated through the entire pass_ends_on_shared list
        if trackPoint < len(pass_ends_on_shared):
          #f.write(f'len+1 = {len(pass_ends_on_shared)}\n')
          # find the index of the common_node in pass_with_shared
          idx = print_passes_processed[i].index(common_node[trackPoint])
          idx_count = 0
          #f.write(f'trackPoint {trackPoint}\n')
          # if node is not first node in pass_with_shared
          if idx != 0 and idx-(idx_count+1) > 0 :
            # collect neighbors of already-printed shared node in pass containing already-printed shared node
            while idx_count < num_overlap and (idx-(idx_count+1)) >= 0:
              #f.write(f'idx {idx} idx_count {idx_count} i {i}   idx-idx_count-1   {idx-idx_count-1}\n')
              print_passes_processed[pass_ends_on_shared[trackPoint]].append(print_passes_processed[i][idx-(idx_count+1)])
              f.write(f'Appending node {print_passes_processed[i][idx-(idx_count+1)]} from pass {pass_with_shared[trackPoint]} to pass {pass_ends_on_shared[trackPoint]}.\n')
              idx_count = idx_count+1
              #f.write(f'idx_count {idx_count}\n')
            trackPoint = trackPoint+1
            #f.write(f'trackPoint {trackPoint}\n')
          else:
            trackPoint = trackPoint+1
            #f.write(f'else trackPoint {trackPoint}\n')  
            continue
        else:
          continue

    f.close()


    with open('changelog.txt', 'a') as f:
      # Print final print passes
      f.write('\n\nFinal multimaterial print passes (after overlap applied):\n\n')
      for passNum in print_passes_processed:
        f.write(f'Pass {passNum} \n{print_passes_processed[passNum]}')
        f.write('\n\n')
    f.close()

# If not printing multimaterial
else:
  print('\nskipping this block (printing single material, not multi-material)')


############################################### Optional Plot: Final Print Passes (Single Material, With Overlap) ##############################################

if plots == 1 and num_overlap != 0:

  x = {}
  y = {}
  z = {}
  for i in print_passes_processed_SM:
    x[i] = []
    y[i] = []
    z[i] = []
    for j in print_passes_processed_SM[i]:
      x[i].append(points_array[j][0])
      y[i].append(points_array[j][1])
      z[i].append(points_array[j][2])

  fig = go.Figure()
  if downsample == 1:
    fig = go.Figure(layout_title_text = 'Single Material (Overlap, Downsampled)')
  else:
    fig = go.Figure(layout_title_text = 'Single Material (Overlap)')
  config = dict({'scrollZoom': True})
  for i in x:
    fig.add_trace(go.Scatter3d(x=x[i], y=y[i], z=z[i]))
    fig.update_traces(marker_size = 2)
    fig.update_layout(title_x=0.5)

  # Create and add slider
  steps = []
  for i in range(len(fig.data)):
      step = dict(
          method="update",
          args=[{"visible": [False] * len(fig.data)},
                {"title": "Single Material (Overlap) <br>[Print Pass: " + str(i) + "]"}],  
      )
      for j in range(0,i+1):
        step["args"][0]["visible"][j] = True
      steps.append(step)

  sliders = [dict(
      currentvalue={"prefix": "Print pass: "},
      steps=steps
  )]

  fig.update_layout(
      sliders=sliders,
      margin=dict(l=30, r=30, t=30, b=30),
    title_x=0.5
  )

  fig.update_scenes(aspectmode='cube')

  # Store output graphs
  fig.write_html(f'outputs/network_SM_overlap.html') 


########################################### Optional Plot: Final Print Passes (Arterial vs. Venous) (Overlap) ##########################################

if plots == 1 and multimaterial == 1 and num_overlap != 0:

  x = {}
  y = {}
  z = {}
  for i in print_passes_processed:
    x[i] = []
    y[i] = []
    z[i] = []
    for j in print_passes_processed[i]:
      x[i].append(points_array[j][0])
      y[i].append(points_array[j][1])
      z[i].append(points_array[j][2])


  color_array = []
  for i in print_passes_processed_artven:
    if print_passes_processed_artven[i][-1] == 0:
      color_array.append("blue")
    else:
      color_array.append("crimson")

  fig = go.Figure()
  if downsample == 1:
    fig = go.Figure(layout_title_text = 'Arterial vs Venous (Overlap, Downsampled)')
  else:
    fig = go.Figure(layout_title_text = 'Arterial vs Venous (Overlap)')
  config = dict({'scrollZoom': True})

  for i in x:
    fig.add_trace(go.Scatter3d(x=x[i], y=y[i], z=z[i], line_color=color_array[i]))
    fig.update_traces(marker_size = 2)
    fig.update_layout(title_x=0.5)

  # Create and add slider
  steps = []
  for i in range(len(fig.data)):
      step = dict(
          method="update",
          args=[{"visible": [False] * len(fig.data)},
                {"title": "Arterial vs Venous <br>[Print Pass: " + str(i) + "]"}],  # layout attribute
      )
      for j in range(0,i+1):
        step["args"][0]["visible"][j] = True  # Toggle i'th trace to "visible"
      steps.append(step)

  sliders = [dict(
      currentvalue={"prefix": "Print pass: "},
      steps=steps
  )]

  fig.update_layout(
      sliders=sliders,
      margin=dict(l=30, r=30, t=30, b=30),
      title_x=0.5
  )

  fig.update_scenes(aspectmode='cube')

  # Store output graphs
  fig.write_html(f'outputs/network_MM.html') 

  print('\nFinished plotting passes for multi-material network.')




############################################### Output: .txt files for single material print ###############################################

# x-coordinates (single material)
x = []
for i in range(0,len(print_passes_processed_SM)):
  for j in print_passes_processed_SM[i]:
    if int(j) != arbitrary_val:
      x.append(round(points_array[j, 0], numDecimalsOutput))
  x_strings = [str(number) for number in x]
  if i == 0:
    with open('x_coordinates_SM.txt', 'w') as f:
      f.write(f'Pass {i} \n')
      for line in x_strings:
        f.write(line)
        f.write('\n')
      f.close()
  else:
    with open('x_coordinates_SM.txt', 'a') as f:
      f.write('\n')
      f.write(f'\nPass {i} \n')
      f.write('\n'.join(x_strings))
    f.close()
  x_strings = []
  x = []


# y-coordinates (single material)
y = []
for i in range(0,len(print_passes_processed_SM)):
  for j in print_passes_processed_SM[i]:
    if int(j) != arbitrary_val:
      y.append(round(points_array[j, 1], numDecimalsOutput))
  y_strings = [str(number) for number in y]
  if i == 0:
    with open('y_coordinates_SM.txt', 'w') as f:
      f.write(f'Pass {i}\n')
      for line in y_strings:
        f.write(line)
        f.write('\n')
      f.close()
  else:
    with open('y_coordinates_SM.txt', 'a') as f:
      f.write(f'\nPass {i}\n')
      f.write('\n'.join(y_strings))
    f.close()
  y_strings = []
  y = []


# z-coordinates (single material)
z = []
for i in range(0,len(print_passes_processed_SM)):
  for j in print_passes_processed_SM[i]:
    if int(j) != arbitrary_val:
      z.append(round(points_array[j, 2], numDecimalsOutput))
  z_strings = [str(number) for number in z]
  if i == 0:
    with open('z_coordinates_SM.txt', 'w') as f:
      f.write(f'Pass {i}\n')
      for line in z_strings:
        f.write(line)
        f.write('\n')
      f.close()
  else:
    with open('z_coordinates_SM.txt', 'a') as f:
      f.write(f'\n \nPass {i} \n')
      f.write('\n'.join(z_strings))
    f.close()
  z_strings = []
  z = []


# radii (single material)
if numColumns > 3:
  radius = []
  for i in range(0,len(print_passes_processed_SM)):
    for j in print_passes_processed_SM[i]:
      if int(j) != arbitrary_val:
        radius.append(round(points_array[j, 3], numDecimalsOutput))
    radius_strings = [str(number) for number in radius]
    if i == 0:
      with open('radii_list_SM.txt', 'w') as f:
        f.write(f'Pass {i}\n')
        for line in radius_strings:
          f.write(line)
          f.write('\n')
        f.close()
    else:
      with open('radii_list_SM.txt', 'a') as f:
        f.write(f'\n \nPass {i} \n')
        f.write('\n'.join(radius_strings))
      f.close()
    radius_strings = []
    radius = []


# vessel type (single material)
if numColumns == 5:
  vesseltype = []
  for i in range(0,len(print_passes_processed_SM)):
    for j in print_passes_processed_SM[i]:
      if int(j) != arbitrary_val:
        vesseltype.append(round(points_array[j, 4], numDecimalsOutput))
    vesseltype_strings = [str(number) for number in vesseltype]
    if i == 0:
      with open('vesseltype_list_SM.txt', 'w') as f:
        f.write(f'Pass {i}\n')
        for line in vesseltype_strings:
          f.write(line)
          f.write('\n')
        f.close()
    else:
      with open('vesseltype_list_SM.txt', 'a') as f:
        f.write(f'\n \nPass {i} \n')
        f.write('\n'.join(vesseltype_strings))
      f.close()
    vesseltype_strings = []
    vesseltype = []

# print speed (single material)
if numColumns > 3 and speed_calc == 1:
  printspeed = []
  for i in range(0,len(print_passes_processed_SM)):
    for j in print_passes_processed_SM[i]:
      printspeed.append(round(radius_speed_SM[j], numDecimalsOutput))
    printspeed_strings = [str(number) for number in printspeed]
    if i == 0:
      with open('printspeed_list_SM.txt', 'w') as f:
        f.write(f'Pass {i}\n')
        for line in printspeed_strings:
          f.write(line)
          f.write('\n')
        f.close()
    else:
      with open('printspeed_list_SM.txt', 'a') as f:
        f.write(f'\n \nPass {i} \n')
        f.write('\n'.join(printspeed_strings))
      f.close()
    printspeed_strings = []
    printspeed = []


# Single material (all available columns of information)
with open('all_coordinates_SM.txt', 'w') as f:
  for i in range(0,len(print_passes_processed_SM)):
      f.write(f'Pass {i} \n')
      for j in print_passes_processed_SM[i]:
        if int(j) != arbitrary_val:
          x = str(round(points_array[j, 0], numDecimalsOutput))
          y = str(round(points_array[j, 1], numDecimalsOutput))
          z = str(round(points_array[j, 2], numDecimalsOutput))
          if numColumns > 3:
            radius = str(round(points_array[j, 3], numDecimalsOutput))
            all = x + ' ' + y + ' ' + z + ' ' + radius
          if numColumns == 5:
            vesseltype = str(round(points_array[j, 4], numDecimalsOutput))
            all = x + ' ' + y + ' ' + z + ' ' + radius + ' ' + vesseltype
        f.write(all)
        f.write('\n')
        if j == print_passes_processed_SM[i][-1]:
          f.write('\n')
f.close()

############################################### Output: .txt files for multimaterial print ###############################################

if multimaterial == 1:

  # x-coordinates (multimaterial)
  x = []
  for i in range(0,len(print_passes_processed)):
    for j in print_passes_processed[i]:
      if int(j) != arbitrary_val:
        x.append(points_array[j, 0])
    x_strings = [f'%.{numDecimalsOutput}f' % number for number in x]
    if i == 0:
      with open('x_coordinates_MM.txt', 'w') as f:
        f.write(f'Pass {i} \n')
        for line in x_strings:
          f.write(line)
          f.write('\n')
        f.close()
    else:
      with open('x_coordinates_MM.txt', 'a') as f:
        f.write('\n')
        f.write(f'\nPass {i} \n')
        f.write('\n'.join(x_strings))
      f.close()
    x_strings = []

  # y-coordinates (multimaterial)
  y = []
  for i in range(0,len(print_passes_processed)):
    for j in print_passes_processed[i]:
      if int(j) != arbitrary_val:
        y.append(points_array[j, 1])
    y_strings = [f'%.{numDecimalsOutput}f' % number for number in y]
    if i == 0:
      with open('y_coordinates_MM.txt', 'w') as f:
        f.write(f'Pass {i}\n')
        for line in y_strings:
          f.write(line)
          f.write('\n')
        f.close()
    else:
      with open('y_coordinates_MM.txt', 'a') as f:
        f.write(f'\nPass {i}\n')
        f.write('\n'.join(y_strings))
      f.close()
    y_strings = []

  # z-coordinates (multimaterial)
  z = []
  for i in range(0,len(print_passes_processed)):
    for j in print_passes_processed[i]:
      if int(j) != arbitrary_val:
        z.append(points_array[j, 2])
    z_strings = [f'%.{numDecimalsOutput}f' % number for number in z]
    if i == 0:
      with open('z_coordinates_MM.txt', 'w') as f:
        f.write(f'Pass {i}\n')
        for line in z_strings:
          f.write(line)
          f.write('\n')
        f.close()
    else:
      with open('z_coordinates_MM.txt', 'a') as f:
        f.write(f'\n \nPass {i} \n')
        f.write('\n'.join(z_strings))
      f.close()
    z_strings = []

  # radii (multimaterial)
  if numColumns > 3:
    radius = []
    for i in range(0,len(print_passes_processed)):
      for j in print_passes_processed[i]:
        if int(j) != arbitrary_val: 
          radius.append(points_array[j, 3])
      radius_strings = [f'%.{numDecimalsOutput}f' % number for number in radius]
      if i == 0:
        with open('radii_list_MM.txt', 'w') as f:
          f.write(f'Pass {i}\n')
          for line in radius_strings:
            f.write(line)
            f.write('\n')
          f.close()
      else:
        with open('radii_list_MM.txt', 'a') as f:
          f.write(f'\n \nPass {i} \n')
          f.write('\n'.join(radius_strings))
        f.close()
      radius_strings = []

  # vessel type (multimaterial)
  if numColumns == 5:
    vesseltype = []
    for i in range(0,len(print_passes_processed)):
      for j in print_passes_processed[i]:
        if int(j) != arbitrary_val:
          vesseltype.append(points_array[j, 4])
      vesseltype_strings = [f'%.{numDecimalsOutput}f' % number for number in vesseltype]
      if i == 0:
        with open('vesseltype_list_MM.txt', 'w') as f:
          f.write(f'Pass {i}\n')
          for line in vesseltype_strings:
            f.write(line)
            f.write('\n')
          f.close()
      else:
        with open('vesseltype_list_MM.txt', 'a') as f:
          f.write(f'\n \nPass {i} \n')
          f.write('\n'.join(vesseltype_strings))
        f.close()
      vesseltype_strings = []

  # print speed (multimaterial)
  if numColumns > 3 and speed_calc == 1:
    printspeed = []
    for i in range(0,len(print_passes_processed)):
      for j in print_passes_processed[i]:
        printspeed.append(radius_speed_MM[j])
      printspeed_strings = [f'%.{numDecimalsOutput}f' % number for number in printspeed]
      if i == 0:
        with open('printspeed_list_MM.txt', 'w') as f:
          f.write(f'Pass {i}\n')
          for line in printspeed_strings:
            f.write(line)
            f.write('\n')
          f.close()
      else:
        with open('printspeed_list_MM.txt', 'a') as f:
          f.write(f'\n \nPass {i} \n')
          f.write('\n'.join(printspeed_strings))
        f.close()
      printspeed_strings = []

  # Multimaterial (all available columns of information)
  with open('all_coordinates_MM.txt', 'w') as f:
    for i in range(0,len(print_passes_processed)):
        f.write(f'Pass {i} \n')
        for j in print_passes_processed[i]:
          if int(j) != arbitrary_val:
            x = str(round(points_array[j, 0], numDecimalsOutput))
            y = str(round(points_array[j, 1], numDecimalsOutput))
            z = str(round(points_array[j, 2], numDecimalsOutput))
            if numColumns > 3:
              radius = str(round(points_array[j, 3], numDecimalsOutput))
            if numColumns == 5:
              vesseltype = str(round(points_array[j, 4], numDecimalsOutput))
            all = x + ' ' + y + ' ' + z + ' ' + radius + ' ' + vesseltype
          f.write(all)
          f.write('\n')
          if j == print_passes_processed[i][-1]:
            f.write('\n')
  f.close()

print('\nGenerated output files. X-CAVATE has completed.')


############################ Generate g-code | SINGLE MATERIAL (PRESSURE-BASED) | CONSTANT OR CHANGING RADII ##################################

if printer_type == 0:

  gapTracker = 0

  with open('gcode_SM_pressure.txt', 'w') as f:

    # Header
    f.write(';=========== Begin GCODE ============= \n')

    print('\n')

    # Optional custom header
    if custom_gcode == 1:
      with open(f'{headerCode}','r') as headerText:
        for line in headerText:
          f.write(line)
        f.write('\n')

    # Network
    for i in range(0,len(print_passes_processed_SM)):
      j_counter = 0
      for j in print_passes_processed_SM[i]: # coordinate of print pass
        x = round(points_array[j, 0], numDecimalsOutput)
        y = round(points_array[j, 1], numDecimalsOutput)
        z = round(points_array[j, 2], numDecimalsOutput)
        # if changing radii
        if numColumns > 3 and speed_calc == 1:
          printspeed = radius_speed_SM[j]
        # if constant radius
        if speed_calc == 0:
          printspeed = print_speed
        # Start of first print pass
        if j_counter == 0 and i == 0:
          f.write('G90 \n')
          f.write(f'G92 X{x} Y{y} {printhead1_axis}{z} \n')
          f.write(f'G90 F{printspeed} \n')
          # Start extrusion (including dwell)
          if custom_gcode == 1:
            with open(f'{startExtrusionCode}','r') as startExtrusionText:
              for line in startExtrusionText:
                f.write(line)
              f.write('\n')
          f.write(f'G1 X{x} Y{y} {printhead1_axis}{z} F{printspeed}\n')
        # Start of each print pass (except first)
        elif j_counter == 0 and i != 0:
          f.write(f';Print pass {i} \n')
          f.write('G90 \n')
          # Stop extrusion (including dwell)
          if custom_gcode == 1:
            with open(f'{stopExtrusionCode}','r') as stopExtrusionText:
              for line in stopExtrusionText:
                f.write(line)
              f.write('\n')
          f.write(f'G1 X{x} Y{y} \n') # without extrusion
          f.write('G90 \n')
          f.write(f'G1 X{x} Y{y} {printhead1_axis}{z}\n')
          # Start extrusion (code for initial)
          f.write('G91 \n')
          # Start extrusion
          if custom_gcode == 1:
            with open(f'{startExtrusionCode}','r') as startExtrusionText:
              for line in startExtrusionText:
                f.write(line)
              f.write('\n')
          f.write('G90 \n')
          f.write(f'G1 X{x} Y{y} {printhead1_axis}{z} F{printspeed}\n')
        else:
          f.write(f'G1 X{x} Y{y} {printhead1_axis}{z} F{printspeed}\n')
        j_counter += 1
      # Optionally extending the end of the print pass for gap closure
      if close_var_SM == 1 and i in gap_pass_SM:
        f.write(f';##### Extra segment #####\n')
        f.write(f'G91\n')
        f.write(f'G1 X{delta_x_SM[gapTracker]} Y{delta_y_SM[gapTracker]} {printhead1_axis}{delta_z_SM[gapTracker]} F{printspeed}\n')
        f.write(f'G90\n')
        f.write(f';########################\n')
        gapTracker += 1
      # End of print pass (stop extrusion)
      f.write('G91 \n')
      # Stop extrusion (including dwell)
      if custom_gcode == 1:
        with open(f'{stopExtrusionCode}','r') as stopExtrusionText:
          for line in stopExtrusionText:
            f.write(line)
          f.write('\n')
      f.write(f'G1 {printhead1_axis}{initial_lift} F{customZJogSpeed} \n') # initial nozzle lift
      f.write('G90 \n')
      f.write(f'G1 {printhead1_axis}{networkTop} F10 \n')


    # Footer
    f.write('G90 \n')
    f.write(f'G1 {printhead1_axis}{containerHeight+amount_up} \n')
    #f.write('M2 \n')

  f.close()

############################ Generate g-code | SINGLE MATERIAL (POSITIVE INK DISPLACEMENT-BASED) | CONSTANT OR CHANGING RADII ##################################
if printer_type == 1:

  gapTracker = 0

  with open('gcode_SM_positiveInk.txt', 'w') as f:

    # Header
    f.write(';=========== Begin GCODE ============= \n')

    print('\n')

    # Optional custom header
    if custom_gcode == 1:
      with open(f'{headerCode}','r') as headerText:
        for line in headerText:
          f.write(line)
        f.write('\n')

    #Track extrusion position
    plungerPosition = 0
      
    # Network
    for i in range(0,len(print_passes_processed_SM)):
      j_counter = 0
      for j in print_passes_processed_SM[i]: # coordinate of print pass
        x = round(points_array[j, 0], numDecimalsOutput)
        y = round(points_array[j, 1], numDecimalsOutput)
        z = round(points_array[j, 2], numDecimalsOutput)
        r = round(points_array[j, 3], numDecimalsOutput)
        
        # Print speed is constant for positive ink displacement printing
        printspeed = print_speed

        # Start of first print pass
        if j_counter == 0 and i == 0:
          f.write('G90 \n')
          f.write(f';Print pass {i} \n')
          f.write(f'G92 X{x} Y{y} {printhead1_axis}{z} {printhead_1}{0} \n')
          # Start extrusion
          if custom_gcode == 1:
            f.write('G91 \n')
            with open(f'{startExtrusionCode}','r') as startExtrusionText:
              for line in startExtrusionText:
                f.write(line)
              f.write('\n')
            f.write('G90 \n')
            plungerPosition += customPositiveInkStartValue
        # Start of each print pass (except first)
        elif j_counter == 0 and i != 0:
          f.write(f';Print pass {i} \n')
          f.write('G90 \n')
          f.write(f'G1 X{x} Y{y} F{customJogSpeed}\n') # without extrusion
          f.write(f'G1 {printhead1_axis}{z} F{customJogSpeed}\n')
          # Start extrusion
          if custom_gcode == 1:
            f.write('G91 \n')
            with open(f'{startExtrusionCode}','r') as startExtrusionText:
              for line in startExtrusionText:
                f.write(line)
              f.write('\n')
            f.write('G90 \n')
            plungerPosition += customPositiveInkStartValue
        else:

          # Previous coordinates (for extrusion calculation)
          prev_node = print_passes_processed_SM[i][j_counter-1]
          xp = points_array[prev_node, 0]
          yp = points_array[prev_node, 1] 
          zp = points_array[prev_node, 2]

          # Calculate norm
          diff = np.array([x-xp, y-yp, z-zp])
          norm = np.linalg.norm(diff)

          if useRadiiPositiveInk == 0:
            lineRadius = customPositiveInkLineDiameter/2
          elif useRadiiPositiveInk == 1 and numColumns > 3:
            lineRadius = r

          customPositiveInkSyringeRadius = customPositiveInkSyringeDiameter/2

          # Calculate extrusion amount and update the plunger position
          extrusionValue = customPositiveInkFactor * norm * (lineRadius/customPositiveInkSyringeRadius)**2
          plungerPosition += extrusionValue

          f.write(f'G1 X{x} Y{y} {printhead1_axis}{z} {printhead_1}{round(plungerPosition, numDecimalsOutput)} F{printspeed}\n')

        j_counter += 1
      # Optionally extending the end of the print pass for gap closure
      if close_var_SM == 1 and i in gap_pass_SM:

        # Calculate norm of extension segment
        norm = np.linalg.norm([delta_x_SM[gapTracker], delta_y_SM[gapTracker], delta_z_SM[gapTracker]])

        # Calculate the extrusion amount using the last value of lineRadius and update the plunger position
        extrusionValue = customPositiveInkFactor * norm * (lineRadius/customPositiveInkSyringeRadius)**2
        plungerPosition += extrusionValue

        f.write(f';##### Extra segment #####\n')
        f.write(f'G91 \n')
        f.write(f'G1 X{round(delta_x_SM[gapTracker], numDecimalsOutput)} Y{round(delta_y_SM[gapTracker], numDecimalsOutput)} {printhead1_axis}{round(delta_z_SM[gapTracker], numDecimalsOutput)} {printhead_1}{round(extrusionValue, numDecimalsOutput)} F{printspeed}\n')
        f.write(f'G90\n')
        f.write(f';########################\n')
        gapTracker += 1
      # End of print pass (stop extrusion)
      f.write('G91 \n')
      if custom_gcode == 1:
      # Stop extrusion
        with open(f'{stopExtrusionCode}','r') as stopExtrusionText:
          for line in stopExtrusionText:
            f.write(line)
          f.write('\n')
        plungerPosition += customPositiveInkStopValue
      f.write(f'G1 {printhead1_axis}{initial_lift} F{customZJogSpeed} \n')
      f.write('G90 \n')
      f.write(f'G1 {printhead1_axis}{networkTop} F{customJogSpeed} \n')

    # Footer
    f.write(f'G1 {printhead1_axis}{containerHeight+amount_up} \n')

  f.close()


############################ Generate g-code (PRINTESS) | SINGLE MATERIAL | CONSTANT OR CHANGING RADII ##################################

gapTracker = 0

with open('gcode_SM_printess.txt', 'w') as f:

  # Header
  f.write(';=========== Begin GCODE ============= \n')

  print('\n')

  # Network
  for i in range(0,len(print_passes_processed_SM)):
    j_counter = 0
    for j in print_passes_processed_SM[i]: # coordinate of print pass
      x = points_array[j, 0]
      y = points_array[j, 1]
      z = points_array[j, 2]
      # if changing radii
      if numColumns > 3 and speed_calc == 1:
        printspeed = radius_speed_SM[j]
      # if constant radius
      if speed_calc == 0:
        printspeed = print_speed
      # Start of first print pass
      if j_counter == 0 and i == 0:
        f.write('VELOCITY ON \n')
        f.write('ROUNDING ON \n')
        f.write('G90 \n')
        f.write(f'G92 X{x} Y{y} {printhead1_axis}{z} \n')
        f.write(f'Enable {printhead_1} \n')
        f.write(f'G90 F{printspeed} \n')
        f.write(f'BRAKE {printhead_1} 0 \n') # start extrude
        f.write(f'DWELL {dwell_start} \n')
        f.write(f'G1 X{x} Y{y} {printhead1_axis}{z} F{printspeed}\n')
      # Start of each print pass (except first)
      elif j_counter == 0 and i != 0:
        f.write(f';Print pass {i} \n')
        f.write('G90 \n')
        f.write(f'BRAKE {printhead_1} 1 \n') # stop extrusion
        f.write(f'G1 X{x} Y{y} \n') # without extrusion
        f.write('G90 \n')
        f.write(f'G1 X{x} Y{y} {printhead1_axis}{z}\n')
        # Start extrusion (code for initial)
        f.write(f'Enable {printhead_1} \n')
        f.write('G91 \n')
        f.write(f'BRAKE {printhead_1} 0 \n') # start extrusion
        f.write(f'DWELL {dwell_start} \n')
        f.write('G90 \n')
        f.write(f'G1 X{x} Y{y} {printhead1_axis}{z} F{printspeed}\n')
      else:
        f.write(f'G1 X{x} Y{y} {printhead1_axis}{z} F{printspeed}\n')
      j_counter += 1
    # Optionally extending the end of the print pass for gap closure
    if close_var_SM == 1 and i in gap_pass_SM:
      f.write(f';##### Extra segment #####\n')
      f.write(f'G91\n')
      f.write(f'G1 X{delta_x_SM[gapTracker]} Y{delta_y_SM[gapTracker]} {printhead1_axis}{delta_z_SM[gapTracker]} F{printspeed}\n')
      f.write(f'G90\n')
      f.write(f';########################\n')
      gapTracker += 1
    # End of print pass (stop extrusion)
    f.write(f'Enable {printhead_1} \n')
    f.write('G91 \n')
    f.write(f'DWELL {dwell_end} \n')
    f.write(f'BRAKE {printhead_1} 1 \n') # stop extrusion
    f.write(f'G1 {printhead1_axis}{initial_lift} F{customZJogSpeed} \n') # initial nozzle lift
    f.write('G90 \n')
    f.write(f'G1 {printhead1_axis}{networkTop} F{customJogSpeed} \n')


  # Footer
  f.write('G90 \n')
  f.write(f'G1 {printhead1_axis}{containerHeight+amount_up} \n')
  f.write('M2 \n')

f.close()

############################ # Generate g-code | MULTIMATERIAL (PRESSURE-BASED) | CONSTANT OR CHANGING RADII ##################################

gapTracker = 0

if multimaterial == 1 and custom_gcode == 1 and printer_type == 0:

  # Place the arterial (red) ink on the left printead (Aa), and the venous (blue)
  # ink on the righthand printhead (Ab).


  # Specifying which syringe connects to which pressure box
  arterial_COM = 2
  venous_COM = 1

  # Need to start by zeroing at the arterial printhead

  z_range = abs(max(points_array[:,2]) - min(points_array[:,2]))
  clearance = 2 # mm

  # y-offset between nozzles
  if args.front_nozzle == 1: # venous (right) in front of arterial (left)
    y_offsetToVen = ydist_between_printheads
    y_offsetToArt = -ydist_between_printheads
  else: # venous (right) behind arterial (left)
    y_offsetToVen = -ydist_between_printheads
    y_offsetToArt = ydist_between_printheads


  with open('gcode_MM_pressure.txt', 'w') as f:

    # Header
    f.write(';=========== Begin GCODE ============= \n')

    if custom_gcode == 1:
      with open(f'{headerCode}','r') as headerText:
        for line in headerText:
          f.write(line)
        f.write('\n')

    print('\n')

    # Network
    for i in range(0,len(print_passes_processed)):
      j_counter = 0
      for j in print_passes_processed[i]: # coordinate of print pass
        x = round(points_array[j, 0], numDecimalsOutput)
        y = round(points_array[j, 1], numDecimalsOutput)
        z = round(points_array[j, 2], numDecimalsOutput)
        if speed_calc == 1:
          printspeed = radius_speed_MM[j]
        if speed_calc == 0:
          printspeed = print_speed
        if len(print_passes_processed[i]) > 1:
          node = print_passes_processed[i][1] # second node in print pass
          artven = points_array[node,4] # artven of second node in print pass
        else:
          artven = points_array[j, 4] # artven of first (only) node in print pass
        # Start of first print pass
        if j_counter == 0 and i == 0:
          # Default to arterial axis
          curr_printhead = printhead_1
          curr_axis = printhead1_axis
          other_printhead = printhead_2
          other_axis = printhead2_axis
          curr = 1 # arterial
          f.write('G90 \n')
          if artven == 0 and curr == 1: # move to venous if necessary
            curr_printhead = printhead_2
            curr_axis = printhead2_axis
            other_printhead = printhead_1
            other_axis = printhead1_axis
            f.write('; Print Pass 0 \n')
            f.write('; moving to VENOUS \n')
            # Set other_printhead print pressure to resting_pressure (set arterial to "resting")
            if custom_gcode == 1:
              with open(f'{rest_pressure_printhead1}','r') as restPrinthead1:
                for line in restPrinthead1:
                  f.write(line)
                f.write('\n')
            # Set curr_printhead print pressure to active_pressure (set venous to "active")
            if custom_gcode == 1:
              with open(f'{active_pressure_printhead2}','r') as activePrinthead2:
                for line in activePrinthead2:
                  f.write(line)
                f.write('\n')
            f.write(f'G91 G1 {printhead1_axis}{containerHeight+amount_up} {printhead2_axis}{containerHeight+amount_up} F{customJogSpeed} \n') # raise axes 1 and 2
            f.write(f'G91 G1 X-{dist_between_printheads} F{customJogSpeedTranslation} \n')
            f.write(f'G91 G1 Y{y_offsetToVen} F{customJogSpeed} \n')
            f.write(f'G91 G1 {printhead1_axis}-{containerHeight+amount_up} {printhead2_axis}-{containerHeight+amount_up} F{customJogSpeed} \n')
            f.write(f'G90 \n')
            f.write(f'G92 X{x} Y{y} {printhead1_axis}{z} {printhead2_axis}{z} \n')
            # Start extrusion of curr_printhead (including dwell)
            if custom_gcode == 1:
              with open(f'{startExtrusionCode_printhead2}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
            # Start extrusion of other_printhead (including dwell)
            if custom_gcode == 1:
              with open(f'{startExtrusionCode_printhead1}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} F{printspeed} \n')
            curr = 0
          else:
            f.write('; Print Pass 0 \n')
            f.write(f'G92 X{x} Y{y} {curr_axis}{z} \n')
            f.write('G90 F0.5 \n')
            # Start extrusion of curr_printhead
            if custom_gcode == 1:
              with open(f'{startExtrusionCode_printhead1}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
            f.write(f'G1 X{x} Y{y} {printhead1_axis}{z} F{printspeed} \n')
        # Start of each print pass (except first)
        elif j_counter == 0 and i != 0:
          prev_point = print_passes_processed[i-1][-1]
          prev_x = points_array[prev_point, 0]
          prev_y = points_array[prev_point, 1]
          prev_z = points_array[prev_point, 2]
          f.write(f';Print pass {i} \n')
          if (artven != 0 and curr == 0): # move to arterial if necessary; use != 0 to control for the scaleFactor
            curr_printhead = printhead_1
            curr_axis = printhead1_axis
            other_printhead = printhead_2
            other_axis = printhead2_axis
            f.write(f'; moving to ARTERIAL \n')
            # Set other_printhead print pressure to resting_pressure (set venous to "resting")
            if custom_gcode == 1:
              with open(f'{rest_pressure_printhead2}','r') as restPrinthead:
                for line in restPrinthead:
                  f.write(line)
                f.write('\n')
            # Set curr_printhead print pressure to active_pressure (set arterial to "active")
            if custom_gcode == 1:
              with open(f'{active_pressure_printhead1}','r') as activePrinthead:
                for line in activePrinthead:
                  f.write(line)
                f.write('\n')
            f.write(f'G91 G1 {printhead1_axis}{containerHeight+amount_up} {printhead2_axis}{containerHeight+amount_up} F{customJogSpeed} \n') # raise axes 1 and 2
            f.write(f'G91 G1 X{dist_between_printheads} F{customJogSpeedTranslation} \n')
            f.write(f'G91 G1 Y{y_offsetToArt} F{customJogSpeed} \n')
            f.write(f'G91 G1 {printhead1_axis}-{containerHeight+amount_up} {printhead2_axis}-{containerHeight+amount_up} \n')
            f.write(f'G90 \n')
            f.write(f'G92 X{prev_x} Y{prev_y} \n')
            f.write(f'G90 G1 X{x} Y{y} \n')
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} \n')
            # Start extrusion of curr_printhead
            if custom_gcode == 1:
              with open(f'{startExtrusionCode_printhead1}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
            # Start extrusion of other_printhead
            if custom_gcode == 1:
              with open(f'{startExtrusionCode_printhead2}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
            curr = 1 # update printhead tracker
          elif artven == 0 and curr == 1: # move to venous if necessary
            curr_printhead = printhead_2
            curr_axis = printhead2_axis
            other_printhead = printhead_1
            other_axis = printhead1_axis
            f.write('; moving to VENOUS \n')
            # Set other_printhead print pressure to resting_pressure (set arterial to "resting")
            if custom_gcode == 1:
              with open(f'{rest_pressure_printhead1}','r') as restPrinthead1:
                for line in restPrinthead1:
                  f.write(line)
                f.write('\n')
            # Set curr_printhead print pressure to active_pressure here (set venous to "active")
            if custom_gcode == 1:
              with open(f'{active_pressure_printhead2}','r') as activePrinthead2:
                for line in activePrinthead2:
                  f.write(line)
                f.write('\n')
            f.write(f'G91 G1 {printhead1_axis}{containerHeight+amount_up} {printhead2_axis}{containerHeight+amount_up} F{customJogSpeed} \n') # raise axes 1 and 2
            f.write(f'G91 G1 X-{dist_between_printheads} F{customJogSpeedTranslation} \n')
            f.write(f'G91 G1 Y{y_offsetToVen} F{customJogSpeed} \n')
            f.write(f'G91 G1 {printhead1_axis}-{containerHeight+amount_up} {printhead2_axis}-{containerHeight+amount_up} \n')
            f.write(f'G90 \n')
            f.write(f'G92 X{prev_x} Y{prev_y} \n')
            f.write(f'G90 G1 X{x} Y{y} \n')
            f.write(f'G90 G1 X{x} Y{y} {curr_axis}{z} \n')
            # Start extrusion of curr_printhead
            if custom_gcode == 1:
              with open(f'{startExtrusionCode_printhead2}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
            # Start extrusion of other_printhead
            if custom_gcode == 1:
              with open(f'{startExtrusionCode_printhead1}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
            curr = 0 # update printhead tracker
          else:
            # Active printhead is the desired printhead (e.g., want arterial and arterial is active)
            f.write(f'G1 X{x} Y{y} \n')
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} \n')
            # Start extrusion and dwell
            if custom_gcode == 1:
              with open(f'{startExtrusionCode_printhead1}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
              with open(f'{startExtrusionCode_printhead2}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')        
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} F{printspeed} \n')
        else:
          if j_counter == 0:
            # Start extrusion and dwell
            if custom_gcode == 1:
              with open(f'{startExtrusionCode_printhead1}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
              with open(f'{startExtrusionCode_printhead2}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} F{printspeed} \n')
          else:
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} F{printspeed} \n')
        j_counter += 1
      # Optionally extending the end of the print pass for gap closure
      if close_var_MM == 1 and i in gap_pass_MM:
        f.write(f';##### Extra segment #####\n')
        f.write(f'G91\n')
        f.write(f'G1 X{delta_x_MM[gapTracker]} Y{delta_y_MM[gapTracker]} {curr_axis}{delta_z_MM[gapTracker]} F{printspeed}\n')
        f.write(f'G90\n')
        f.write(f';########################\n')
        gapTracker += 1
      # End of print pass
      # Stop extrusion (including dwell)
      if custom_gcode == 1:
        with open(f'{stopExtrusionCode_printhead1}','r') as stopExtrusionText:
          for line in stopExtrusionText:
            f.write(line)
          f.write('\n')
        with open(f'{stopExtrusionCode_printhead2}','r') as stopExtrusionText:
          for line in stopExtrusionText:
            f.write(line)
          f.write('\n')
      f.write(f'G91 G1 {curr_axis}{initial_lift} F{customZJogSpeed} \n') # initial nozzle lift
      f.write(f'G90 G1 {printhead1_axis}{networkTop} {printhead2_axis}{networkTop} F{customJogSpeed} \n') # raises axes 1 and 2
      if curr == 1:
        f.write(f'; ending on ARTERIAL \n')
      if curr == 0:
        f.write(f'; ending on VENOUS \n')



    # Footer
    f.write('G90 \n')
    f.write(f'G1 {printhead1_axis}{containerHeight+amount_up} \n')
    #f.write('M2 \n')

  f.close()

############################ Generate g-code | MULTIMATERIAL (POSITIVE INK DISPLACEMENT-BASED) | CONSTANT OR CHANGING RADII ##################################


if multimaterial == 1 and custom_gcode == 1 and printer_type == 1:

  gapTracker = 0

  # Place the arterial (red) ink on the left printead (Aa), and the venous (blue)
  # ink on the righthand printhead (Ab).

  # Specifying which syringe connects to which pressure box
  arterial_COM = 2
  venous_COM = 1

  # Need to start by zeroing at the arterial printhead

  z_range = abs(max(points_array[:,2]) - min(points_array[:,2]))
  clearance = 2 # mm

  # y-offset between nozzles
  if args.front_nozzle == 1: # venous (right) in front of arterial (left)
    y_offsetToVen = -ydist_between_printheads
    y_offsetToArt = ydist_between_printheads
  else: # venous (right) behind arterial (left)
    y_offsetToVen = ydist_between_printheads
    y_offsetToArt = -ydist_between_printheads

  with open('gcode_MM_positiveInk.txt', 'w') as f:

    # Header
    f.write(';=========== Begin GCODE ============= \n')

    if custom_gcode == 1:
      with open(f'{headerCode}','r') as headerText:
        for line in headerText:
          f.write(line)
        f.write('\n')

    #Track extrusion position for arterial and venous printheads
    plungerPositionA = 0
    plungerPositionV = 0

    # Network
    for i in range(0,len(print_passes_processed)):
      j_counter = 0
      for j in print_passes_processed[i]: # coordinate of print pass
        x = round(points_array[j, 0], numDecimalsOutput)
        y = round(points_array[j, 1], numDecimalsOutput)
        z = round(points_array[j, 2], numDecimalsOutput)
        r = round(points_array[j, 3], numDecimalsOutput)

        #Specify print speed based on user input
        printspeed = print_speed

        #Determine if arterial or venous segment
        if len(print_passes_processed[i]) > 1:
          node = print_passes_processed[i][1] # second node in print pass
          artven = points_array[node,4] # artven of second node in print pass
        else:
          artven = points_array[j, 4] # artven of first (only) node in print pass

        # Start of first print pass
        if j_counter == 0 and i == 0:

          # Default to venous axis (extrusion only)
          curr_printhead = printhead_2
          curr_axis = printhead2_axis
          other_printhead = printhead_1
          other_axis = printhead1_axis
          curr = 0 # venous

          # If the active printhead is venous but need arterial, move to arterial
          if artven == 1 and curr == 0:
            curr_printhead = printhead_1
            curr_axis = printhead1_axis
            other_printhead = printhead_2
            other_axis = printhead2_axis
            f.write('; Print Pass 0 \n')
            f.write(f'G92 {printhead1_axis}{z} {printhead2_axis}{z} {printhead_1}{0} {printhead_2}{0} \n')
            f.write('; moving to ARTERIAL \n')

            # Switch active printhead to arterial and only lower the arterial printhead
            f.write('G90 \n')
            f.write(f'G1 {printhead1_axis}{containerHeight+amount_up} {printhead2_axis}{containerHeight+amount_up} F{customJogSpeed} \n')
            f.write('G91 \n')
            f.write(f'G1 X-{dist_between_printheads} F{customJogSpeedTranslation} \n')
            f.write(f'G1 Y{y_offsetToArt} F{customJogSpeedTranslation} \n')
            f.write('G90 \n')
            f.write(f'G92 X{x} Y{y} \n')
            f.write(f'G1 {printhead1_axis}{z} F{customJogSpeed} \n')

            # Start extrusion of curr_printhead (including dwell)
            if custom_gcode == 1:
              f.write('G91 \n')
              with open(f'{startExtrusionCode_printhead1}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
              f.write('G90 \n')
              plungerPositionV += customPositiveInkStartValueV
            curr = 0

          # If the active printhead is venous, stay on venous but raise the arterial printhead
          else:
            f.write('; Print Pass 0 \n')
            f.write(f'G92 X{x} Y{y} {printhead1_axis}{z} {printhead2_axis}{z} \n')
            f.write('G90 \n')
            f.write(f'G1 {printhead1_axis}{containerHeight+amount_up} F{customJogSpeed} \n')

            # Start extrusion of curr_printhead
            if custom_gcode == 1:
              f.write('G91 \n')
              with open(f'{startExtrusionCode_printhead2}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
              f.write('G90 \n')
              plungerPositionA += customPositiveInkStartValueA

        # Start of each print pass (except first)
        elif j_counter == 0 and i != 0:
        
          #Initialize overshoot adjustment as zero
          overshoot_adjustment = np.zeros(3)

          # Check to see if the previous pass has a gap closure segment
          if close_var_MM == 1 and (i-1) in gap_pass_MM:
            
            # Calculate overshoot by adding deltas for current print pass
            overshoot_adjustment = np.array([delta_x_MM[gapTracker-1], delta_y_MM[gapTracker-1], delta_z_MM[gapTracker-1]])
          
          # Obtains the previous node on the previous vessel
          prev_point = print_passes_processed[i-1][-1]
          prev_x = round(points_array[prev_point, 0] + overshoot_adjustment[0], numDecimalsOutput)
          prev_y = round(points_array[prev_point, 1] + overshoot_adjustment[1], numDecimalsOutput)
          prev_z = round(points_array[prev_point, 2] + overshoot_adjustment[2], numDecimalsOutput)

          f.write(f'; Print pass {i} \n')

          if (artven != 0 and curr == 0): # move to arterial if necessary; use != 0 to control for the scaleFactor
            curr_printhead = printhead_1
            curr_axis = printhead1_axis
            other_printhead = printhead_2
            other_axis = printhead2_axis

            # Switching to arterial printhead
            f.write(f'; moving to ARTERIAL \n')
            f.write(f'G1 {printhead1_axis}{containerHeight+amount_up} {printhead2_axis}{containerHeight+amount_up} F{customJogSpeed} \n')
            f.write('G91 \n')
            f.write(f'G1 X-{dist_between_printheads} F{customJogSpeedTranslation} \n')
            f.write(f'G1 Y{y_offsetToArt} F{customJogSpeed} \n')
            f.write('G90 \n')
            f.write(f'G92 X{prev_x} Y{prev_y} \n')

            # Positioning arterial printhead to start of vessel
            f.write(f'G1 X{x} Y{y} \n')
            f.write(f'G1 {curr_axis}{z} \n')

            # Start extrusion of curr_printhead (arterial)
            if custom_gcode == 1:
              f.write('G91 \n')
              with open(f'{startExtrusionCode_printhead1}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
              f.write('G90 \n')
              plungerPositionA += customPositiveInkStartValueA
            curr = 1 # update printhead tracker

          elif artven == 0 and curr == 1: # move to venous if necessary
            curr_printhead = printhead_2
            curr_axis = printhead2_axis
            other_printhead = printhead_1
            other_axis = printhead1_axis

            # Switching to venous printhead
            f.write('; moving to VENOUS \n')
            f.write(f'G1 {printhead1_axis}{containerHeight+amount_up} {printhead2_axis}{containerHeight+amount_up} F{customJogSpeed} \n')
            f.write('G91 \n')
            f.write(f'G1 X{dist_between_printheads} F{customJogSpeedTranslation} \n')
            f.write(f'G1 Y{y_offsetToVen} F{customJogSpeedTranslation} \n')
            f.write('G90 \n')
            f.write(f'G92 X{prev_x} Y{prev_y} \n')

            # Positioning venous printhead to start of vessel
            f.write(f'G1 X{x} Y{y} \n')
            f.write(f'G1 {curr_axis}{z} \n')

            # Start extrusion of curr_printhead (venous)
            if custom_gcode == 1:
              f.write('G91 \n')
              with open(f'{startExtrusionCode_printhead2}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
              f.write('G90 \n')
              plungerPositionV += customPositiveInkStartValueV
            curr = 0 # update printhead tracker
          
          else: # Active printhead is the desired printhead (e.g., want arterial and arterial is active)
            f.write(f'G1 X{x} Y{y} \n')
            f.write(f'G1 {curr_axis}{z} \n')

            # Start extrusion and dwell arterial or venous as needed
            if custom_gcode == 1 and curr_axis == printhead1_axis:
              f.write('G91 \n')
              with open(f'{startExtrusionCode_printhead1}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
              f.write('G90 \n')
              plungerPositionA += customPositiveInkStartValueA

            elif custom_gcode == 1 and curr_axis == printhead2_axis:
              f.write('G91 \n')
              with open(f'{startExtrusionCode_printhead2}','r') as startExtrusionText:
                for line in startExtrusionText:
                  f.write(line)
                f.write('\n')
              f.write('G90 \n')
              plungerPositionV += customPositiveInkStartValueV

        # Every node in the print pass except the first
        else:
            #Previous coordinates (for extrusion calculation)
            prev_node = print_passes_processed[i][j_counter-1]
            xp = points_array[prev_node, 0]
            yp = points_array[prev_node, 1] 
            zp = points_array[prev_node, 2]

            # Calculate norm
            diff = np.array([x-xp, y-yp, z-zp])
            norm = np.linalg.norm(diff)

            if useRadiiPositiveInk == 0:
              lineRadius = customPositiveInkLineDiameter/2
            elif useRadiiPositiveInk == 1 and numColumns > 3:
              lineRadius = r

            customPositiveInkSyringeRadius = customPositiveInkSyringeDiameter/2

            # Calculate extrusion amount and update the correct plunger position
            extrusionValue = customPositiveInkFactor * norm * (lineRadius/customPositiveInkSyringeRadius)**2
            if curr_axis == printhead1_axis:
              plungerPositionA += extrusionValue
              f.write(f'G1 X{x} Y{y} {curr_axis}{z} {curr_printhead}{round(plungerPositionA, numDecimalsOutput)} F{printspeed} \n')
            elif curr_axis == printhead2_axis:
              plungerPositionV += extrusionValue
              f.write(f'G1 X{x} Y{y} {curr_axis}{z} {curr_printhead}{round(plungerPositionV, numDecimalsOutput)} F{printspeed} \n')

        j_counter += 1

      # Optionally extending the end of the print pass for gap closure
      if close_var_MM == 1 and i in gap_pass_MM:
        #Calculate norm of extension segment
        norm = np.linalg.norm([delta_x_MM[gapTracker], delta_y_MM[gapTracker], delta_z_MM[gapTracker]])

        # Calculate the extrusion amount using the last value of lineRadius and update the correct plunger position
        extrusionValue = customPositiveInkFactor * norm * (lineRadius/customPositiveInkSyringeRadius)**2
        if curr_axis == printhead1_axis:
          plungerPositionA += extrusionValue
        elif curr_axis == printhead2_axis:
          plungerPositionV += extrusionValue

        f.write(f';##### Extra segment #####\n')
        f.write('G91 \n')
        f.write(f'G1 X{round(delta_x_MM[gapTracker], numDecimalsOutput)} Y{round(delta_y_MM[gapTracker], numDecimalsOutput)} {curr_axis}{round(delta_z_MM[gapTracker], numDecimalsOutput)} {curr_printhead}{round(extrusionValue, numDecimalsOutput)} F{printspeed}\n')
        f.write(f'G90\n')
        f.write(f';########################\n')
        gapTracker += 1
      # End of print pass

      f.write('G91 \n')
      # Stop extrusion, using the correct stopExtrusionCode
      if custom_gcode == 1 and curr_axis == printhead1_axis:
        with open(f'{stopExtrusionCode_printhead1}','r') as stopExtrusionText:
          for line in stopExtrusionText:
            f.write(line)
          f.write('\n')
        plungerPositionA += customPositiveInkStopValueA

      elif custom_gcode == 1 and curr_axis == printhead2_axis:
        with open(f'{stopExtrusionCode_printhead2}','r') as stopExtrusionText:
          for line in stopExtrusionText:
            f.write(line)
          f.write('\n')
        plungerPositionV += customPositiveInkStopValueV

      #Raise the current axis by the lift ammount
      f.write(f'G1 {curr_axis}{initial_lift} F{customZJogSpeed} \n') # initial nozzle lift

      # Raise the current axis to the networkTop
      f.write('G90 \n')
      f.write(f'G1 {curr_axis}{round(networkTop, numDecimalsOutput)} F{customJogSpeed} \n')

      if curr == 1:
        f.write(f'; ending on ARTERIAL \n')
      if curr == 0:
        f.write(f'; ending on VENOUS \n')

    # Footer
    f.write('G90 \n')
    f.write(f'G1 {printhead1_axis}{containerHeight+amount_up} \n')
    
  f.close()

############################ # Generate g-code (PRINTESS) | MULTIMATERIAL | CONSTANT OR CHANGING RADII ##################################


if multimaterial == 1 and custom_gcode == 0 and printer_type == 0:

  gapTracker = 0

  # Place the arterial (red) ink on the left printead (Aa), and the venous (blue)
  # ink on the righthand printhead (Ab).


  # Specifying which syringe connects to which pressure box
  arterial_COM = 2
  venous_COM = 1

  # Need to start by zeroing at the arterial printhead

  z_range = abs(max(points_array[:,2]) - min(points_array[:,2]))
  clearance = 2 # mm

  # y-offset between nozzles
  if args.front_nozzle == 1: # venous (right) in front of arterial (left)
    y_offsetToVen = ydist_between_printheads
    y_offsetToArt = -ydist_between_printheads
  else: # venous (right) behind arterial (left)
    y_offsetToVen = -ydist_between_printheads
    y_offsetToArt = ydist_between_printheads


  with open('gcode_MM_printess.txt', 'w') as f:

    # Header
    f.write('DVAR $AP, $COM,$hFile,$press,$length,$lame,$cCheck \n')
    f.write(';=========== Begin GCODE ============= \n')

    print('\n')

    # Network
    for i in range(0,len(print_passes_processed)):
      j_counter = 0
      for j in print_passes_processed[i]: # coordinate of print pass
        x = points_array[j, 0]
        y = points_array[j, 1]
        z = points_array[j, 2]
        if speed_calc == 1:
          printspeed = radius_speed_MM[j]
        if speed_calc == 0:
          printspeed = print_speed
        if len(print_passes_processed[i]) > 1:
          node = print_passes_processed[i][1] # second node in print pass
          artven = points_array[node,4] # artven of second node in print pass
        else:
          artven = points_array[j, 4] # artven of first (only) node in print pass
        # Start of first print pass
        if j_counter == 0 and i == 0:
          # Default to arterial axis
          curr_printhead = printhead_1
          curr_axis = printhead1_axis
          other_printhead = printhead_2
          other_axis = printhead2_axis
          curr = 1 # arterial
          f.write('VELOCITY ON \n')
          f.write('ROUNDING ON \n')
          f.write('G90 \n')
          if artven == 0 and curr == 1: # move to venous if necessary
            curr_printhead = printhead_2
            curr_axis = printhead2_axis
            other_printhead = printhead_1
            other_axis = printhead1_axis
            f.write('; Print Pass 0 \n')
            f.write('; moving to VENOUS \n')
            f.write(f'$COM={arterial_COM} \n') # "resting"
            f.write(f'$AP={resting_pressure} \n') # "resting"
            f.write('Call setPress P$COM Q$AP \n')
            f.write(f'$COM={venous_COM} \n') # active
            f.write(f'$AP={active_pressure} \n') # active
            f.write('Call setPress P$COM Q$AP \n')
            f.write(f'G91 G1 {printhead1_axis}{containerHeight+amount_up} {printhead2_axis}{containerHeight+amount_up} F{customJogSpeed} \n') # raise axes 1 and 2
            f.write(f'G91 G1 X-{dist_between_printheads} F{customJogSpeedTranslation} \n')
            f.write(f'G91 G1 Y{y_offsetToVen} F{customJogSpeed} \n')
            f.write(f'G91 G1 {printhead1_axis}-{containerHeight+amount_up} {printhead2_axis}-{containerHeight+amount_up} F{customJogSpeed} \n')
            f.write(f'G90 \n')
            f.write(f'G92 X{x} Y{y} {printhead1_axis}{z} {printhead2_axis}{z} \n')
            f.write(f'Enable {curr_printhead} \n') # START EXTRUSION
            f.write(f'Enable {other_printhead} \n') # OTHER START 
            f.write(f'BRAKE {curr_printhead} 0 \n') # START EXTRUSION
            f.write(f'BRAKE {other_printhead} 0 \n') # OTHER START
            f.write(f'DWELL {dwell_start} \n') 
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} F{printspeed} \n')
            curr = 0
          else:
            f.write('; Print Pass 0 \n')
            f.write(f'G92 X{x} Y{y} {curr_axis}{z} \n')
            f.write(f'Enable {curr_printhead} \n') # START EXTRUSION
            f.write('G90 F0.5 \n')
            f.write(f'BRAKE {curr_printhead} 0 \n') # START EXTRUSION
            f.write(f'DWELL {dwell_start} \n')
            f.write(f'G1 X{x} Y{y} {printhead1_axis}{z} F{printspeed} \n')
        # Start of each print pass (except first)
        elif j_counter == 0 and i != 0:
          prev_point = print_passes_processed[i-1][-1]
          prev_x = points_array[prev_point, 0]
          prev_y = points_array[prev_point, 1]
          prev_z = points_array[prev_point, 2]
          f.write(f';Print pass {i} \n')
          if (artven != 0 and curr == 0): # move to arterial if necessary; use != 0 to control for the scaleFactor
            curr_printhead = printhead_1
            curr_axis = printhead1_axis
            other_printhead = printhead_2
            other_axis = printhead2_axis
            f.write(f'; moving to ARTERIAL \n')
            f.write(f'$COM={venous_COM} \n') # "resting"
            f.write(f'$AP={resting_pressure} \n') # "resting"
            f.write('Call setPress P$COM Q$AP \n')
            f.write(f'$COM={arterial_COM} \n') # active
            f.write(f'$AP={active_pressure} \n') # active
            f.write('Call setPress P$COM Q$AP \n')
            f.write(f'G91 G1 {printhead1_axis}{amount_up} {printhead2_axis}{amount_up} F{customJogSpeed} \n') # raise axes 1 and 2
            f.write(f'G91 G1 X{dist_between_printheads} F{customJogSpeedTranslation} \n')
            f.write(f'G91 G1 Y{y_offsetToArt} F{customJogSpeed} \n')
            f.write(f'G91 G1 {printhead1_axis}-{amount_up} {printhead2_axis}-{amount_up} \n')
            f.write(f'G90 \n')
            f.write(f'G92 X{prev_x} Y{prev_y} \n')
            f.write(f'G90 G1 X{x} Y{y} \n')
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} \n')
            f.write(f'Enable {curr_printhead} \n') # START EXTRUSION
            f.write(f'Enable {other_printhead} \n') # OTHER START 
            f.write(f'BRAKE {other_printhead} 0 \n') # OTHER START
            f.write(f'BRAKE {curr_printhead} 0 \n') # START EXTRUSION
            f.write(f'DWELL {dwell_start} \n')
            curr = 1 # update printhead tracker
          elif artven == 0 and curr == 1: # move to venous if necessary
            # if (artven != second_point_artven): # handle instances of repeated point from multimaterial subdivision
            #   continue
            # else:
            curr_printhead = printhead_2 # Ab
            curr_axis = printhead2_axis # B
            other_printhead = printhead_1 # Aa
            other_axis = printhead1_axis # A
            f.write(f'; moving to VENOUS \n')
            f.write(f'$COM={arterial_COM} \n') # "resting"
            f.write(f'$AP={resting_pressure} \n') # "resting"
            f.write('Call setPress P$COM Q$AP \n')
            f.write(f'$COM={venous_COM} \n') # active
            f.write(f'$AP={active_pressure} \n') # active
            f.write('Call setPress P$COM Q$AP \n')
            f.write(f'G91 G1 {printhead1_axis}{amount_up} {printhead2_axis}{amount_up} F{customJogSpeed} \n') # raise axes 1 and 2
            f.write(f'G91 G1 X-{dist_between_printheads} F{customJogSpeedTranslation} \n')
            f.write(f'G91 G1 Y{y_offsetToVen} F{customJogSpeed} \n')
            f.write(f'G91 G1 {printhead1_axis}-{amount_up} {printhead2_axis}-{amount_up} \n')
            f.write(f'G90 \n')
            f.write(f'G92 X{prev_x} Y{prev_y} \n')
            f.write(f'G90 G1 X{x} Y{y} \n')
            f.write(f'G90 G1 X{x} Y{y} {curr_axis}{z} \n')
            f.write(f'Enable {curr_printhead} \n') # START EXTRUSION
            f.write(f'Enable {other_printhead} \n') # OTHER START 
            f.write(f'BRAKE {other_printhead} 0 \n') # OTHER START
            f.write(f'BRAKE {curr_printhead} 0 \n') # START EXTRUSION
            f.write(f'DWELL {dwell_start} \n')
            curr = 0 # update printhead tracker
          else:
            # Extrusion
            f.write(f'G1 X{x} Y{y} \n')
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} \n')
            f.write(f'Enable {curr_printhead} \n') # START EXTRUSION
            f.write(f'Enable {other_printhead} \n') # OTHER START 
            f.write(f'BRAKE {other_printhead} 0 \n') # OTHER START
            f.write(f'BRAKE {curr_printhead} 0 \n') # START EXTRUSION
            f.write(f'DWELL {dwell_start} \n')
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} F{printspeed} \n')
        else:
          if j_counter == 0:
            f.write(f'Enable {curr_printhead} \n') # START EXTRUSION
            f.write(f'Enable {other_printhead} \n') # OTHER START 
            f.write(f'BRAKE {other_printhead} 0 \n') # OTHER START
            f.write(f'BRAKE {curr_printhead} 0 \n') # START EXTRUSION
            f.write(f'DWELL {dwell_start} \n')
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} F{printspeed} \n')
          else:
            f.write(f'G1 X{x} Y{y} {curr_axis}{z} F{printspeed} \n')
        j_counter += 1
      # Optionally extending the end of the print pass for gap closure
      if close_var_MM == 1 and i in gap_pass_MM:
        f.write(f';##### Extra segment #####\n')
        f.write(f'G91\n')
        f.write(f'G1 X{delta_x_MM[gapTracker]} Y{delta_y_MM[gapTracker]} {curr_axis}{delta_z_MM[gapTracker]} F{printspeed}\n')
        f.write(f'G90\n')
        f.write(f';########################\n')
        gapTracker += 1
      # End of print pass (stop extrusion)
      f.write(f'DWELL {dwell_end} \n')
      f.write(f'BRAKE {curr_printhead} 1 \n') # STOP EXTRUSION
      f.write(f'BRAKE {other_printhead} 1 \n') # STOP OTHER
      f.write(f'G91 G1 {curr_axis}{initial_lift} F{customZJogSpeed} \n') # initial nozzle lift
      f.write(f'G90 G1 {printhead1_axis}{networkTop} {printhead2_axis}{networkTop} F{customJogSpeed} \n') # raises axes 1 and 2
      if curr == 1:
        f.write(f'; ending on ARTERIAL \n')
      if curr == 0:
        f.write(f'; ending on VENOUS \n')



    # Footer
    f.write('G90 \n')
    f.write(f'G1 {printhead1_axis}{containerHeight+amount_up} \n')
    f.write('M2 \n')

  f.close()

####################################################### Print Instructions ###############################################################

# x dimensions
min_x = min(points_array[:,0])
max_x = max(points_array[:,0])
total_x = abs(min_x) + abs(max_x)

# y dimensions
min_y = min(points_array[:,1])
max_y = max(points_array[:,1])
total_y = abs(min_y) + abs(max_y)

# z dimensions
min_z = min(points_array[:,2])
max_z = max(points_array[:,2])
total_z = abs(min_z) + abs(max_z)

# starting coordinate
start_node = print_passes_processed[0][0]
x_start = points_array[start_node][0]
y_start = points_array[start_node][1]
z_start = points_array[start_node][2]

# travel dimensions
left = abs(x_start-min_x)
right = abs(max_x-x_start)
forward = abs(y_start-min_y)
backward = abs(max_y-y_start)
up = abs(total_z)

# Instructions for printing in the middle of container:

x_start = (container_x + left - right) / 2
y_start = (container_y + forward - backward) / 2
z_start = (containerHeight - total_z) / 2

print('\n')
print(f'For a container of dimensions x={container_x} mm, y={container_y} mm, z={containerHeight}mm, center the print by following these instructions.')

print('\nFor SINGLE material:')
print('\nIf +x is right, +y is backwards, and +z is upwards (with respect to nozzle\'s movement or relative movement to the printbed):')
print('1. Position nozzle in left corner of the container, of the container face closest to the observer.')
print('\nIf +x is left, +y is forwards, and +z is upwards (with respect to nozzle\'s movement or relative movement to the printbed):')
print('1. Position nozzle in right corner of the container, of the container face farthest from the observer.')
print('\n2. Enter the g-code command: G92 X0 Y0')
print(f'3. Move linearly to X{round(x_start,2)} Y{round(y_start,2)} with g-code command: G1 X{round(x_start,2)} Y{round(y_start,2)}')
print(f'4. Manually maneuver the Z-axis until it is {round(z_start,2)} mm from the bottom of the container.')
print('5. Press start!')

print(f'\nfor MULTIMATERIAL:\n')
print('If you have not already calibrated, calibrate as below:')
print('To find the offset in x- and y- between the two nozzles:')
print(f'1. Position first nozzle (arterial) on the Calibration Tip and enter: G92 X0 Y0 {printhead1_axis}0')
print(f'2. Position second nozzle (venous) on the Calibration Tip and enter: G92 {printhead2_axis}0')
print('3. BEFORE MOVING ANYTHING, record the offset between the nozzles in X and Y, which will be the current x- and y-coordinates of the venous nozzle.')
print('4. Re-run x-cavate, inputting the offsets at the command line as offset_x and offset_y. Use the front_nozzle variable to specify whether the venous nozzle (right printhead) is in front (front_nozzle=1) or behind (front_nozzle=2) the arterial nozzle (left printhead).')
print('\nTo position for multimaterial printing, after completing the calibration:')
print('\nIf +x is right, +y is backwards, and +z is upwards (with respect to nozzle\'s movement or relative movement to the printbed):')
print('1. Position first nozzle (arterial) in left corner of the container, of the container face closest to the observer.')
print('\nIf +x is left, +y is forwards, and +z is upwards (with respect to nozzle\'s movement or relative movement to the printbed):')
print('1. Position second nozzle (venous) in right corner of the container, of the container face farthest from the observer.')
print('\n2. Enter the g-code command: G92 X0 Y0')
print(f'3. Enter: G1 X{round(x_start,2)} Y{round(y_start,2)}')
print(f'4. Enter: G1 {printhead1_axis}0 {printhead2_axis}0')
print(f'5. Manually maneuver FIRST nozzle until it is {round(z_start,2)} mm from the bottom of the container.')
print('6. Record the current z-position of FIRST nozzle, and DO NOT RE-ZERO. Will now move the SECOND nozzle to the same z-position.')
print(f'7. Enter: G1 {printhead2_axis}(current position of FIRST nozzle)')
print('8. Just to reiterate... DO NOT RE-ZERO. Both nozzles are now at the correct starting position.')
print('9. Press start!')

print(f'\n')
print('Your print will have the following padding:\n')
print(f'left padding: {round(x_start - left,2)}')
print(f'right padding: {round(container_x - (x_start + right),2)}')
print(f'back padding: {round(container_y - (y_start + backward),2)}')
print(f'front padding: {round(y_start - forward,2)}')
print('\n')

##### Final output #####

print('This concludes XCAVATE. Enjoy your print!\n')
