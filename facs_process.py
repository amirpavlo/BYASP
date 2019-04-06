import sys
import csv
import json
from scipy.signal import savgol_filter
from scipy.ndimage import gaussian_filter1d
import numpy as np
import matplotlib.pyplot as plt

# https://github.com/NumesSanguis/FACSvatar
# https://github.com/TadasBaltrusaitis/OpenFace/wiki/Action-Units
# https://www.cs.cmu.edu/~face/facs.htm
# https://en.wikipedia.org/wiki/Facial_Action_Coding_System
# https://github.com/TadasBaltrusaitis/OpenFace/wiki/Output-Format
# https://facsvatar.readthedocs.io/en/latest/defaultsetup.html
#

# There are 68 points 0-67
MAX_PDM_ENTRIES = 68
VALUES = 0
MAXIMAS = 1
MINIMAS = 2

facs_data_items = ['frame', 'timestamp', 'AU01_r', 'AU02_r',
                   'AU04_r', 'AU05_r', 'AU06_r', 'AU07_r',
                   'AU09_r', 'AU10_r', 'AU12_r', 'AU14_r',
                   'AU15_r', 'AU17_r', 'AU20_r', 'AU23_r',
                   'AU25_r', 'AU26_r', 'AU45_r', 'gaze_angle_x',
                   'gaze_angle_y', 'pose_Rx', 'pose_Ry', 'pose_Rz']

animation_data = {}
pdm_2d = {}
pdm_3d = {}

#animation_data = {'frame': [[], [], []], 'timestamp': [[], [], []], 'AU01_r': [[], [], []], 'AU02_r': [[], [], []], 'AU04_r': [[], [], []], 'AU05_r': [[], [], []], 'AU06_r': [[], [], []], 'AU07_r': [[], [], []], 'AU09_r': [[], [], []], 'AU10_r': [[], [], []], 'AU12_r': [[], [], []], 'AU14_r': [[], [], []], 'AU15_r': [[], [], []], 'AU17_r': [[], [], []], 'AU20_r': [[], [], []], 'AU23_r': [[], [], []], 'AU25_r': [[], [], []], 'AU26_r': [[], [], []], 'AU45_r': [[], [], []], 'gaze_0_x': [[], [], []], 'gaze_0_y': [[], [], []], 'gaze_0_z': [[], [], []], 'gaze_1_x': [[], [], []], 'gaze_1_y': [[], [], []], 'gaze_1_z': [[], [], []], 'gaze_angle_x': [[], [], []], 'gaze_angle_y': [[], [], []], 'pose_Tx': [[], [], []], 'pose_Ty': [[], [], []], 'pose_Tz': [[], [], []], 'pose_Rx': [[], [], []], 'pose_Ry': [[], [], []], 'pose_Rz': [[], [], []]}

def init_database():
    for e in facs_data_items:
        animation_data[e] = [[], [], []]

    pdm_2d['frame'] = [[], [], []]
    pdm_2d['timestamp'] = [[], [], []]
    for i in range(0, MAX_PDM_ENTRIES):
        name = 'x_'+str(i)
        pdm_2d[name] = [[], [], []]
    for i in range(0, MAX_PDM_ENTRIES):
        name = 'y_'+str(i)
        pdm_2d[name] = [[], [], []]

    pdm_3d['frame'] = [[], [], []]
    pdm_3d['timestamp'] = [[], [], []]
    for i in range(0, MAX_PDM_ENTRIES):
        name = 'X_'+str(i)
        pdm_3d[name] = [[], [], []]
    for i in range(0, MAX_PDM_ENTRIES):
        name = 'Y_'+str(i)
        pdm_3d[name] = [[], [], []]
    for i in range(0, MAX_PDM_ENTRIES):
        name = 'Z_'+str(i)
        pdm_3d[name] = [[], [], []]

def smooth_array(ar, window_size, polyorder):
    # use savgol_filter() to do first path on smooth
    # https://scipy.github.io/devdocs/generated/scipy.signal.savgol_filter.html
    result = savgol_filter(ar, window_size, polyorder)
    # to avoid high frequency/small-amplitude oscillations to help in
    # finding peaks and troughs run a gaussian_filter.
    # I'm not a math wiz so I got this from here:
    # https://stackoverflow.com/questions/47962044/how-to-get-the-correct-peaks-and-troughs-from-an-1d-array
    result = gaussian_filter1d(result, window_size).tolist()

    #https://stackoverflow.com/questions/52125211/find-peaks-and-bottoms-of-graph-and-label-them
    minimas = (np.diff(np.sign(np.diff(result))) > 0).nonzero()[0] + 1
    maximas = (np.diff(np.sign(np.diff(result))) < 0).nonzero()[0] + 1

    return result, maximas.tolist(), minimas.tolist()

def reset_database():
    global animation_data
    global pdm_2d

    for k, v in animation_data.items():
        for i in range(0, 3):
            v[i].clear()

    for k, v in pdm_2d.items():
        for i in range(0, 3):
            v[i].clear()

    for k, v in pdm_3d.items():
        for i in range(0, 3):
            v[i].clear()

def plot_graph(animation_data, name, show=True, pdf_path=''):
    # plot the first entry
    plt.plot(animation_data['frame'][0], animation_data[name][0], label=name)

    for minima in animation_data[name][2]:
        plt.plot(minima, animation_data[name][0][minima], marker="o")
    for maxima in animation_data[name][1]:
        plt.plot(maxima, animation_data[name][0][maxima], marker="o")

    plt.legend()
    if show:
        plt.show()
    elif pdf_path:
        f = plt.figure()
        f.savefig(pdf_path, bbox_inches='tight')

def get_facs_data():
    global animation_data
    return animation_data

def get_pdm2d_data():
    global pdm_2d
    return pdm_2d

def get_pdm3d_data():
    global pdm_3d
    return pdm_3d

def process_openface_csv(csv_name, window_size = 5, polyorder = 2):
    global animation_data
    global pdm_2d

    with open(csv_name, 'r') as fcsv:
        reader = csv.DictReader(fcsv, delimiter=',')
        reader = (dict((k.strip(), v.strip()) for k, v in row.items() if v) \
                  for row in reader)
        for row in reader:
            # ignore entries with low confidence
            if float(row['confidence']) < 0.7:
                continue
            # build my local data base
            for k, v in animation_data.items():
                v[VALUES].append(float(row[k]))
            for k, v in pdm_2d.items():
                v[VALUES].append(float(row[k]))
            for k, v in pdm_3d.items():
                v[VALUES].append(float(row[k]))

        # smooth all the data
        for k, v in animation_data.items():
            if k == 'frame' or k == 'timestamp':
                continue
            if 'pose_' in k:
                animation_data[k][VALUES], \
                animation_data[k][MAXIMAS], \
                animation_data[k][MINIMAS] = \
                    smooth_array(v[VALUES], 11, 5)
            else:
                animation_data[k][VALUES], \
                animation_data[k][MAXIMAS], \
                animation_data[k][MINIMAS] = \
                    smooth_array(v[VALUES], window_size, polyorder)

        # smooth all the data
        for k, v in pdm_2d.items():
            if k == 'frame' or k == 'timestamp':
                continue
            pdm_2d[k][VALUES], \
            pdm_2d[k][MAXIMAS], \
            pdm_2d[k][MINIMAS] = \
                smooth_array(v[0], window_size, polyorder)

        # smooth all the data
        for k, v in pdm_3d.items():
            if k == 'frame' or k == 'timestamp':
                continue
            pdm_3d[k][VALUES], \
            pdm_3d[k][MAXIMAS], \
            pdm_3d[k][MINIMAS] = \
                smooth_array(v[0], window_size, polyorder)

        # export data to JSON
        js = json.dumps(animation_data, indent=4)

    return js

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: smooth </path/to/csv> [</path/to/outputJSON>]")
        exit(1)

    csv_name = sys.argv[1]
    json_name = ''

    if len(sys.argv) >= 3:
        json_name = sys.argv[2]

    js, ad, pdm = process_openface_csv(csv_name)

    if json_name:
        jf = open(json_name, 'w')
        jf.write(js)
        jf.close()

    plot_graph(ad, 'AU04_r')
