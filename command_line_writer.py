################################### About ################################### 

# This file writes command line prompts for X-CAVATE.

# Last updated: 11/30/25

###################################  Required parameters ################################### 

# Required Parameters
required_parameters = {
'network_file': "inputs/multimaterial_network.txt", # Path to .txt file containing network coordinates
'inletoutlet_file': "inputs/inlet_outlet_multimaterial.txt", # Path to .txt file containing inlet and outlet coordinates
'multimaterial': 1, # 1 if two inks (arterial & venous), 0 if only one
'tolerance_flag': 0, # 1 if including tolerance value that differs from the nozzle outer diameter, 0 if not
'nozzle_diameter': 0.25, # Nozzle outer diameter (mm)
'container_height': 50, # Height of the print container (mm)
'amount_up': 10, # Amount to raise nozzles in z-direction before switching the inactive/active nozzles, in mm --> Default is 10
'num_decimals': 2, # Number of decimals places for rounding output values
'speed_calc': 0, # 1 if computing print speeds for changing radii, 0 if not
'plots': 1, # Generate plots of network print paths? 1=Yes, 0=No
'downsample': 0, # Downsample interpolated network? 1=Yes, 0=No
'custom': 0, # Including custom g-code? 1=Yes, 0=No
'printer_type': 2, # Type of custom printer? 2=Aerotech, 1=Positive ink displacement, 0=Pressure-based
}


################################### Specify which optional parameters to include ###################################

# To EXCLUDE an optional parameter, type "#" to the left of its name. Excluded parameters will take on default values (see GitHub).

# To INCLUDE an optional parameter, remove the "#" to the left of its name.

# Optional Parameters
include_optional = {
# 'tolerance': 0, # Amount of tolerance, in mm (see explanation of tolerance in README) --> Default is 0
'container_x': 50, # Dimensions of print container in x, in mm --> Default is 50
'container_y': 50, # Dimensions of print container in y, in mm --> Default is 50
'scale_factor': 1, # Multiple by which to scale the input network --> Default is 1
'downsample_factor': 1, # Factor to downsample the interpolated network --> Default is 1
'flow': 0.127, # Volumetric flow rate of the ink through the syringe, in mm^3/s --> Default is 0.127
'top_padding': 0, # Amount of padding to add above the maximum z-coordinate, in mm --> Default is 0
'dwell_start': 0.08, # Dwell time at start of print segments, in s --> Default is 0.08
'dwell_end': 0.08, # Dwell time at end of print segments, in s --> Default is 0.08
'printhead_1': 'LEFT', # Name of printhead holding arterial ink --> Default is Aa
'printhead_2': 'RIGHT', # Name of printhead holding venous ink --> Default is Ab
'axis_1': 'Arterial', # Name of z-axis holding arterial ink --> Default is A
'axis_2': 'Venous', # Name of z-axis holding venous ink --> Default is B
'print_speed': 50, # Custom print speed, in mm/s --> Default is 1
'resting_pressure': 10, # Extrusion pressure for non-active nozzle during multimaterial printing, in psi --> Default is 10
'active_pressure': 5, # Extrusion pressure for active nozzle during multimaterial printing, in psi --> Default is 5
'offset_x': 100, # Distance between the printhead nozzles in x for multimaterial, in mm --> Default is 103
'offset_y': 5, # Distance between the printhead nozzles in y for multimaterial, in mm --> Default is 0.5
'front_nozzle': 1, # 1 if venous is in front of the arterial printhead in y, 2 otherwise --> Default is 1
# 'num_overlap': 4, # Number of nodes by which to overlap segments --> Default is 0
# 'close_sm': 1, # 1 if including additional gap closure file for single material printing, 0 if not --> No default;
# 'close_mm': 0, # 1 if including additional gap closure file for multimaterial printing, 0 if not --> No default;
# 'jog_speed': 200, # Custom jog speed, in mm/s --> Default is 5
# 'jog_translation': 200, # Jog speed for translating between nozzles in multimaterial, in mm/s --> Default is 10
# 'jog_speed_lift': 50, # Custom jog speed, in mm/s --> Default is 1
# 'initial_lift': 3, # Distance over which to use jogSpeedLift when lifting the nozzle, in mm --> Default is 0.5
# 'positiveInk_start': 0.30, # Extrusion start value for positive ink displacement-based printing (mm) --> Default is 0
# 'positiveInk_end': -0.30, # Extrusion stop value (mm) for positive ink displacement-based printing (mm) --> Default is 0
# 'positiveInk_radii': 1, # Use vessel radii for extrusion calculations? 1 = Yes, 0 = No --> Default is 0
# 'positiveInk_diam': 0.25, # Vessel diameter (mm) for positive ink displacement-based printing (not using SimVascular radii) --> Default is 1
# 'positiveInk_syringe_diam': 4.61, # Syringe diameter (mm) for positive ink displacement-based printing --> Default is 1
# 'positiveInk_factor': 1.2, # Extrusion value multiplier for positive ink displacement-based printing --> Default is 1
# 'positiveInk_start_arterial': 0.30, # Extrusion start value for arterial ink in positive ink displacement-based printing (mm) --> Default is 0
# 'positiveInk_start_venous': 0.30, # Extrusion start value for venous ink in positive ink displacement-based printing (mm) --> Default is 0
# 'positiveInk_end_arterial': 0.30, # Extrusion stop value for arterial ink in positive ink displacement-based printing (mm) --> Default is 0
# 'positiveInk_end_venous': 0.30, # Extrusion stop value for venous ink in positive ink displacement-based printing (mm) --> Default is 0
}


###################################  Write parameters to a string that can be used for the command line ################################### 
 
# Write the parameters in the specified format
cmdText = ""
optionalText = ""

# Iterate through required and optional parameters
for key, value in required_parameters.items():
    cmdText += f"--{key} {value} "
# Remove the trailing comma and space
cmdText = cmdText.rstrip(', ')
for key, value in include_optional.items():
    optionalText += f"--{key} {value} "
# Remove the trailing comma and space
optionalText = optionalText.rstrip(', ')

# Print output to console
print(cmdText + ' ' + optionalText)
