import sys
import csv
import json
from scipy.signal import savgol_filter
from scipy.ndimage import gaussian_filter1d
import numpy as np
plt_unsupported = False
try:
    import matplotlib.pyplot as plt
except:
    plt_unsupported = True
# https://github.com/NumesSanguis/FACSvatar
# https://github.com/TadasBaltrusaitis/OpenFace/wiki/Action-Units
# https://www.cs.cmu.edu/~face/facs.htm
# https://en.wikipedia.org/wiki/Facial_Action_Coding_System
# https://github.com/TadasBaltrusaitis/OpenFace/wiki/Output-Format
# https://facsvatar.readthedocs.io/en/latest/defaultsetup.html
#

# There are 68 points 0-67
MAX_PDM_ENTRIES = 68
MAX_PDM_NON_RIGID_ENTRIES = 34
MAX_PDM_EYE_LMK = 56
VALUES = 0
MAXIMAS = 1
MINIMAS = 2

facs_data_items = ['frame', 'timestamp', 'AU01_r', 'AU02_r',
                   'AU04_r', 'AU05_r', 'AU06_r', 'AU07_r',
                   'AU09_r', 'AU10_r', 'AU12_r', 'AU14_r',
                   'AU15_r', 'AU17_r', 'AU20_r', 'AU23_r',
                   'AU25_r', 'AU26_r', 'AU45_r', 'gaze_angle_x',
                   'gaze_angle_y', 'pose_Rx', 'pose_Ry', 'pose_Rz',
                   'pose_Tx', 'pose_Ty', 'pose_Tz']

rigid_data_items = ['frame', 'timestamp', 'p_scale', 'p_rx',
                    'p_ry', 'p_rz', 'p_tx', 'p_ty']

animation_data = {}
pdm_2d = {}
pdm_3d = {}
rigid_data = {}
non_rigid_data = {}
eye_lmk_2d = {}
eye_lmk_3d = {}

def init_database():
    global animation_data
    global pdm_2d
    global pdm_3d
    global rigid_data
    global non_rigid_data
    global eye_lmk_2d
    global eye_lmk_3d

    for e in facs_data_items:
        animation_data[e] = [[], [], []]

    for e in rigid_data_items:
        rigid_data[e] = [[], [], []]

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

    non_rigid_data['frame'] = [[], [], []]
    non_rigid_data['timestamp'] = [[], [], []]
    for i in range(0, MAX_PDM_NON_RIGID_ENTRIES):
        name = 'p_'+str(i)
        non_rigid_data[name] = [[], [], []]

    for i in range(0, MAX_PDM_EYE_LMK):
        name = 'eye_lmk_x_'+str(i)
        eye_lmk_2d[name] = [[], [], []]
    for i in range(0, MAX_PDM_EYE_LMK):
        name = 'eye_lmk_y_'+str(i)
        eye_lmk_2d[name] = [[], [], []]

    for i in range(0, MAX_PDM_EYE_LMK):
        name = 'eye_lmk_X_'+str(i)
        eye_lmk_3d[name] = [[], [], []]
    for i in range(0, MAX_PDM_EYE_LMK):
        name = 'eye_lmk_Y_'+str(i)
        eye_lmk_3d[name] = [[], [], []]
    for i in range(0, MAX_PDM_EYE_LMK):
        name = 'eye_lmk_Z_'+str(i)
        eye_lmk_3d[name] = [[], [], []]

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
    global rigid_data
    global non_rigid_data
    global eye_lmk_2d
    global eye_lmk_3d

    for k, v in animation_data.items():
        for i in range(0, 3):
            v[i].clear()

    for k, v in pdm_2d.items():
        for i in range(0, 3):
            v[i].clear()

    for k, v in pdm_3d.items():
        for i in range(0, 3):
            v[i].clear()

    for k, v in rigid_data.items():
        for i in range(0, 3):
            v[i].clear()

    for k, v in non_rigid_data.items():
        for i in range(0, 3):
            v[i].clear()

    for k, v in eye_lmk_2d.items():
        for i in range(0, 3):
            v[i].clear()

    for k, v in eye_lmk_3d.items():
        for i in range(0, 3):
            v[i].clear()

def plot_graph(animation_data, name, show=True, pdf_path=''):
    if plt_unsupported:
        return
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

def get_rigid_data():
    global rigid_data
    return rigid_data

def get_non_rigid_data():
    global non_rigid_data
    return non_rigid_data

def get_eye_lmk_2d():
    global eye_lmk_2d
    return eye_lmk_2d

def get_eye_lmk_3d():
    global eye_lmk_3d
    return eye_lmk_3d

def smooth_data(d, window_size, polyorder):
    # smooth all the data
    for k, v in d.items():
        if k == 'frame' or k == 'timestamp':
            continue
        d[k][VALUES], \
        d[k][MAXIMAS], \
        d[k][MINIMAS] = \
            smooth_array(v[0], window_size, polyorder)

def process_openface_csv(csv_name, window_size = 5, polyorder = 2):
    global animation_data
    global pdm_2d
    global rigid_data
    global non_rigid_data

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
            for k, v in rigid_data.items():
                v[VALUES].append(float(row[k]))
            for k, v in non_rigid_data.items():
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
        smooth_data(pdm_2d, window_size, polyorder)
        smooth_data(pdm_3d, window_size, polyorder)
        smooth_data(rigid_data, window_size, polyorder)
        smooth_data(non_rigid_data, window_size, polyorder)

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
