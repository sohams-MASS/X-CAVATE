
# https://github.com/jessica-herrmann/vesselprint | Skylar-Scott Lab

# Last updated: 11.19.25

############################################################### Import: Dependencies ######################################################################

import pandas as pd
import numpy as np
import plotly.graph_objects as go

############################################################### Percent Error ######################################################################


# This section computes the percent error between the desired filament diameter and the measured filament diameter.

target_diameters = [0.4, 0.375, 0.35, 0.325, 0.3, 0.275, 0.25, 0.225, 0.2, 
                    0.175, 0.15, 0.125, 0.1, 0.075]

measured_diameters = pd.read_csv('inputs/diameters_validation.csv')

diameter = measured_diameters.loc[:, 'Length']

diameter_array = diameter.to_numpy()
diameter_array = diameter_array / 1000 # convert microns to mm

# Average the recorded measurements from a given segment
diameter_averages = np.mean(diameter_array.reshape(-1, 3), axis=1)

# Compute the percent error
percent_error = []
for i in range(0,len(target_diameters)):
    error = ((diameter_averages[i] - target_diameters[i]) / target_diameters[i])*100
    percent_error.append(error)

# Rounding
percent_error_rounded = [round(x, 3) for x in percent_error]
diameter_averages_rounded = np.round(diameter_averages, 3)
target_diameters_rounded = [round(x, 3) for x in target_diameters]


# Define data for the DataFrame
data = {
    'Target Diameters (mm)': target_diameters,
    'Average Measured Diameters (mm)': diameter_averages_rounded,
    'Percent Error (%)': percent_error_rounded
}

# Create the DataFrame
df = pd.DataFrame(data)

# Print the DataFrame
print(df)

df.to_csv(f'outputs/error_pressure.csv')

fig = go.Figure(data=[go.Table(header=dict(values=['Target Diameters (mm)', 'Average Measured Diameters (mm)', 'Percent Error (%)']),
                 cells=dict(values=[target_diameters, diameter_averages_rounded, percent_error_rounded]))
                     ])

fig.update_layout(
    title={
        'text': "Percent Error",
        'y':0.9,
        'x':0.5,
        'xanchor': 'center',
        'yanchor': 'top'})

fig.update_layout(
    font_family="Avenir",
)

fig.write_html(f'outputs/error_pressure.html')

