import bpy
import logging
import os
import json
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.app.handlers import persistent
import traceback
import time
import ctypes
import sys
import platform
import random
import math
import subprocess
import datetime
from bpy.props import EnumProperty, StringProperty, BoolVectorProperty
from . import facs_process as facs

logger = logging.getLogger(__name__)

# Global sliders
global_sliders_set = False
global_sliders = {}
init_state = False
plot_all = False

def set_rotation_type(rtype):
    rotation_types = ('BOUNDING_BOX_CENTER', 'CURSOR', 'INDIVIDUAL_ORIGINS', 'MEDIAN_POINT', 'ACTIVE_ELEMENT')
    if not rtype in rotation_types:
        raise RuntimeError(rtype, 'not a valid rotation type. Should be: ', rotation_types)
    bpy.context.scene.tool_settings.transform_pivot_point = rtype

def get_rotation_type():
    return bpy.context.scene.tool_settings.transform_pivot_point

def get_override(area_type, region_type):
    for area in bpy.context.screen.areas:
        if area.type == area_type:
            for region in area.regions:
                if region.type == region_type:
                    override = {'area': area, 'region': region}
                    return override
    #error message if the area or region wasn't found
    raise RuntimeError("Wasn't able to find", region_type," in area ", area_type,
                        "\n Make sure it's open while executing script.")

def rotate_obj_quaternion(obj, axis='Z', value=0.0):
    bpy.context.scene.cursor.location = (0,0,0)
    if not axis in ['X', 'Y', 'Z']:
        return
    for o in bpy.data.objects:
        o.select_set(False)
    obj.select_set(True)
    orig_rt = get_rotation_type()
    set_rotation_type('CURSOR')
    override = get_override('VIEW_3D', 'WINDOW')
    obj.rotation_mode = 'QUATERNION'
    bpy.ops.transform.rotate(override, value=value, orient_axis=axis,
                             orient_type='CURSOR')
    set_rotation_type(orig_rt)

def set_init_state(state):
    global init_state

    init_state = state
    if init_state:
        facs.init_database()

class FACE_OT_clear_animation(bpy.types.Operator):
    bl_idname = "yafr.del_animation"
    bl_label = "Delete Animation"
    bl_description = "Clear Facial Animation"

    def execute(self, context):
        global global_sliders_set
        global global_sliders
        global init_state

        for obj in bpy.data.objects:
            if 'facs_rig_slider_' in obj.name:
                obj.animation_data_clear()
        obj = get_mb_rig()
        if obj:
            obj.animation_data_clear()

        global_sliders_set = False
        global_sliders = {}
        facs.reset_database()
        return {'FINISHED'}

def get_mb_rig():
    rig_names = ['MBLab_skeleton_muscle_ik', 'MBLab_skeleton_base_ik', 'MBLab_skeleton_muscle_fk', 'MBLab_skeleton_base_fk']
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE' and obj.data.name in rig_names:
            return obj
    return None

def process_csv_file(csv, ws, po):
    try:
        js = facs.process_openface_csv(csv, ws, po)
    except Exception as e:
        msg = 'failed to process results\n'+traceback.format_exc()
        logger.critical(msg)
        return False, msg

    if not js:
        msg = 'Failed to process results'
        return False, msg

    return True, 'Success'

class FACE_OT_animate(bpy.types.Operator):
    bl_idname = "yafr.animate_face"
    bl_label = "Animate Face"
    bl_description = "Create Facial Animation"

    def run_openface(self, openface, video):
        outdir = os.path.join(os.path.dirname(openface),
            os.path.splitext(os.path.basename(video))[0]+"_processed")
        if not os.path.exists(outdir):
            os.makedirs(outdir)
        rc = subprocess.run([openface, '-verbose', '-f', video, '-out_dir', outdir],
                            stdout=subprocess.PIPE)
        return rc.returncode, rc.stdout.decode(), outdir

    def set_keyframes_hr(self, result, array, attr, head_bone, intensity):
        rotation = {'Rx': 1, 'Ry': 2, 'Rz': 3}

        for m in array:
            # angle in radians
            val = result[m] + (result[m] * intensity)
            head_bone.rotation_quaternion[rotation[attr]] = val
            head_bone.keyframe_insert('rotation_quaternion', index=rotation[attr], frame=m)

    def get_head_bone(self, mb_rig):
        for obj in bpy.data.objects:
            obj.select_set(False)
        mb_rig.select_set(True)
        bpy.context.view_layer.objects.active = mb_rig
        bpy.ops.object.mode_set(mode='POSE')
        head_bone = None
        msg = "Success"
        try:
            head_bone = bpy.context.object.pose.bones['head']
        except:
            msg = "no head bone found"
            return None, msg

        return head_bone, msg

    def set_keyframes(self, result, array, slider_bone, intensity, vgi, hgi):
        global global_sliders
        if bpy.context.scene.yafr_start_frame > 0:
            frame_offset = bpy.context.scene.yafr_start_frame - 1
        else:
            frame_offset = 0

        for m in array:
            if not 'GZ' in slider_bone.name:
                value = (result[m] / 5) * 0.377
            else:
                # normalize the gaze values to fit in the -0.189 - 0.189
                # range of the gaze slider
                # TODO: if we're going to fit that with other rig systems
                # we need to be a bit smarter than this.
                value = result[m]
                if value > 0:
                    value = min(value, 1)
                    value = value * 0.189
                elif value < 0:
                    value = max(value, -1)
                    value = value * 0.189

                gaze_intensity = hgi
                # intensify the gaze motion independently
                if 'GZ0V' in slider_bone.name:
                    # reverse sign to get the correct up/down motion
                    #value = -value
                    gaze_intensity = vgi

                if value > 0:
                    value = value + (value * gaze_intensity)
                elif value < 0:
                    value = value - ((value * -1) * gaze_intensity)
            if intensity > 0 and not 'GZ' in slider_bone.name:
                # don't accept negative values
                if value < 0:
                    value = -value
                value = value + (value * intensity)
            slider_bone.location[0] = value
            slider_bone.keyframe_insert(data_path="location",
                frame=m+frame_offset, index=0)
            global_sliders[slider_bone.name].append(m)

    def set_every_keyframe(self, result, slider_bone, intensity):
        frame = 1
        for m in result:
            if not 'GZ' in slider_bone.name:
                value = (m / 5) * 0.377
            else:
                value = m
            if intensity > 0:
                value = value + (value * (intensity/100))
            slider_bone.location[0] = value
            if not 'GZ' in slider_bone.name:
                slider_bone.keyframe_insert(data_path="location", frame=frame, index=0)
            frame = frame + 1

    def set_animation_prereq(self, scn):
        if not scn.yafr_facs_rig:
            facs_rig = bpy.data.objects.get('MBLab_skeleton_facs_rig')
        else:
            facs_rig = bpy.data.objects.get(scn.yafr_facs_rig)
        if not facs_rig:
            return False

        # select the rig and put it in POSE mode
        for obj in bpy.data.objects:
            obj.select_set(False)
        facs_rig.select_set(True)
        bpy.context.view_layer.objects.active = facs_rig
        bpy.ops.object.mode_set(mode='POSE')
        return True

    def animate_face(self, mouth, head, animation_data, intensity, vgi, hgi):
        global global_sliders_set

        if not self.set_animation_prereq(bpy.context.scene):
            print("Animation prerequisites not set")
            return

        # animation already done
        if global_sliders_set:
            print("Animation already set. Delete animation first")
            return

        mouth_aus = ['AU10', 'AU12', 'AU13', 'AU14', 'AU15', 'AU16', 'AU17', 'AU20', 'AU23']

        for key, value in animation_data.items():
            # don't use specific AUs if mouth is not selected
            if key.strip('_r') in mouth_aus and not mouth:
                continue

            if 'pose_' in key and not head:
                continue

            slider_name = ''
            head_animation = False
            if 'AU' in key:
                slider_name = 'facs_rig_slider_' + key.strip('_r')
            elif key == 'gaze_angle_x':
                slider_name = 'facs_rig_slider_GZ0H'
            elif key == 'gaze_angle_y':
                slider_name = 'facs_rig_slider_GZ0V'
            elif 'pose_R' in key:
                # only look at the head rotation for now
                head_animation = True
            else:
                continue

            result = value[facs.VALUES]
            maximas = value[facs.MAXIMAS]
            minimas = value[facs.MINIMAS]

            slider_bone = None
            mb_rig = None
            if head_animation:
                mb_rig = get_mb_rig()
                if not mb_rig:
                    msg = "no MB rig found"
                    logger.critical(msg)
                    self.report({'ERROR'}, msg)
                    return
                head_bone, msg = self.get_head_bone(mb_rig)
                if not head_bone:
                    logger.critical(msg)
                    self.report({'ERROR'}, msg)
                    return
                self.set_keyframes_hr(result, maximas, key.strip('pose_'), head_bone, intensity)
                self.set_keyframes_hr(result, minimas, key.strip('pose_'), head_bone, intensity)
            else:
                global_sliders[slider_name] = []
                slider_bone = bpy.context.object.pose.bones.get(slider_name)
                if not slider_bone:
                    logger.critical('slider %s not found', slider_name)
                    continue

                self.set_keyframes(result, maximas, slider_bone, intensity, vgi, hgi)
                self.set_keyframes(result, minimas, slider_bone, intensity, vgi, hgi)
                #self.set_every_keyframe(result, slider_bone, intensity, vgi, hgi)

        global_sliders_set = True

    def execute(self, context):
        global global_sliders_set

        set_init_state(False)

        scn = context.scene
        dirname = os.path.dirname(os.path.realpath(__file__))
        openface = os.path.join(dirname, "openface", "FeatureExtraction")
        video = scn.yafr_videofile
        csv = scn.yafr_csvfile
        ws = scn.yafr_openface_ws
        po = scn.yafr_openface_polyorder
        intensity = scn.yafr_openface_au_intensity
        hgi = scn.yafr_openface_hgaze_intensity
        vgi = scn.yafr_openface_vgaze_intensity
        mouth = scn.yafr_openface_mouth
        head = scn.yafr_openface_head

        if global_sliders_set:
            self.report({'ERROR'}, "Delete current animation first")
            return {'FINISHED'}

        if po >= ws:
            msg = "polyorder must be less than window_length."
            logger.critical(msg)
            self.report({'ERROR'}, msg)
            return {'FINISHED'}

        if ws % 2 == 0:
            msg = "window size needs to be an odd number"
            logger.critical(msg)
            self.report({'ERROR'}, msg)
            return {'FINISHED'}

        # csv file provided use that instead of the video file
        if csv:
            if not os.path.isfile(csv):
                if not os.path.isfile(dirname+csv):
                    msg = "bad csv file provided "+csv
                    logger.critical(msg)
                    self.report({'ERROR'}, msg)
                    return {'FINISHED'}
                else:
                    csv = dirname+csv

            rc, msg = process_csv_file(csv, ws, po)
            # animate the data
            if rc:
                facs_data = facs.get_facs_data()
                self.animate_face(mouth, head, facs_data, intensity, vgi, hgi)
                return {'FINISHED'}

            self.report({'ERROR'}, msg)
            return {'FINISHED'}

        # run openface on the videofile
        # TODO: check if openface is an executable and videofile is a video
        # file.
        if not os.path.isfile(openface):
            if not os.path.isfile(dirname+openface):
                msg = "Bad path to openFace: " + openface
                self.report({'ERROR'}, msg)
                return {'FINISHED'}
            else:
                openface = dirname+openface
        if not os.path.isfile(video):
            # try another tac
            if not os.path.isfile(dirname+video):
                msg = "Bad path to video file: " + video
                self.report({'ERROR'}, 'Bad path to video file')
                return {'FINISHED'}
            else:
                video = dirname+video

        outdir = ''
        try:
            rc, output, outdir = self.run_openface(openface, video)
            if rc:
                self.report({'ERROR'}, ouput)
                return {'FINISHED'}
        except Exception as e:
            logger.critical(e)
            msg = 'failed to run openface\n'+traceback.format_exc()
            self.report({'ERROR'}, msg)
            return {'FINISHED'}

        # process the csv file
        csv = os.path.join(outdir,
            os.path.splitext(os.path.basename(video))[0]+'.csv')
        if not os.path.isfile(csv):
            msg = "Failed to process video. No csv file found: "+csv
            self.report({'ERROR'}, msg)
            return {'FINISHED'}

        # animate the data
        rc, msg = process_csv_file(csv, ws, po)
        # animate the data
        if rc:
            facs_data = facs.get_facs_data()
            self.animate_face(mouth, head, facs_data, intensity, vgi, hgi)
            #frame_end = facs_data['frame'][facs.VALUES][-1]
            #bpy.context.scene.frame_end = frame_end
            return {'FINISHED'}

        self.report({'ERROR'}, msg)
        return {'FINISHED'}

class FACE_OT_pdm_del_animate(bpy.types.Operator):
    bl_idname = "yafr.del_pdm_animation"
    bl_label = "Delete"
    bl_description = "Experimental feature"

    def execute(self, context):
        for obj in bpy.data.objects:
            obj.select_set(False)

        for obj in bpy.data.objects:
            if 'pdm2d_' in obj.name or 'pdm3d_' in obj.name:
                obj.animation_data_clear()
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.delete(use_global=True)
        return {'FINISHED'}

class FACE_OT_pdm3d_rm_rotation(bpy.types.Operator):
    bl_idname = "yafr.rm_pdm3d_rotation"
    bl_label = "Remove Rotation"
    bl_description = "Experimental feature"

    def rotate_obj(self, obj, rx, ry, rz):
        if len(rx) != len(ry) or len(rx) != len(rz):
            self.report({'ERROR'}, "bad rotation information")
            return
        for f in range(0, len(rx)):
            rotate_obj_quaternion(obj, 'X', rx[f])
            rotate_obj_quaternion(obj, 'Y', ry[f])
            rotate_obj_quaternion(obj, 'Z', rz[f])
            obj.keyframe_insert(data_path="location", frame=f)
            #obj.keyframe_insert(data_path="rotation_quaternion", frame=f)
            #obj.rotation_mode = 'QUATERNION'
            #obj.rotation_quaternion[1] = rx[f]
            #obj.rotation_quaternion[2] = ry[f] * -1
            #obj.rotation_quaternion[3] = rz[f] * -1
            #obj.keyframe_insert(data_path="rotation_quaternion", frame=f, index=1)
            #obj.keyframe_insert(data_path="rotation_quaternion", frame=f, index=2)
            #obj.keyframe_insert(data_path="rotation_quaternion", frame=f, index=3)

    def execute(self, context):
        data = facs.get_facs_data()

        rx = data['pose_Rx'][facs.VALUES]
        ry = data['pose_Ry'][facs.VALUES]
        rz = data['pose_Rz'][facs.VALUES]

        # Store the current location of the object for this frame.
        # find out the 3D location of the object after applying the
        # rotation.
        # The delta between the current location and the rotated location
        # is eliminated by subtracting the X,Y,Z locations.
        for obj in bpy.data.objects:
            if not 'amir' in obj.name:
            #if not 'pdm3d_' in obj.name:
                continue
            logger.critical("Rotating object %s: %s", obj.name,
                            str(datetime.datetime.now()))
            self.rotate_obj(obj, rx, ry, rz)

        return {'FINISHED'}

class FACE_OT_pdm2d_animate(bpy.types.Operator):
    bl_idname = "yafr.animate_pdm2d_face"
    bl_label = "Plot"
    bl_description = "Experimental feature"

    def plot_axis(self, obj, axis, result, array, adj=[], div=400):
        if plot_all:
            f = 0
            values = []
            for p in result:
                # the adjustment array brings the points to the center
                # point.
                if len(adj) == len(result):
                    av = adj[f]
                    value = (p - av) / div
                else:
                    value = p / div

                if axis == 1 or axis == 2:
                    value = value * -1
                obj.location[axis] = value
                obj.keyframe_insert(data_path="location", frame=f, index=axis)
                values.append(value)
                f = f+1
            return values
        for m in array:
            value = result[m] / div
            if axis == 1 or axis == 2:
                value = value * -1
            obj.location[axis] = value
            obj.keyframe_insert(data_path="location", frame=m, index=axis)

    def animate_2d_empty(self, obj, attr, pdm_2d, rigid_data):
        y_name = 'y_'+attr.strip('x_')

        x_info = pdm_2d[attr]
        y_info = pdm_2d[y_name]
        p_tx = rigid_data['p_tx'][facs.VALUES]
        p_ty = rigid_data['p_ty'][facs.VALUES]

        x_values = self.plot_axis(obj, 0, x_info[facs.VALUES],
                       x_info[facs.MAXIMAS], adj=p_tx)
        if not plot_all:
            self.plot_axis(obj, 0, x_info[facs.VALUES],
                           x_info[facs.MINIMAS], adj=p_tx)
        y_values = self.plot_axis(obj, 1, y_info[facs.VALUES],
                       y_info[facs.MAXIMAS], adj=p_ty)
        if not plot_all:
            self.plot_axis(obj, 1, y_info[facs.VALUES],
                           y_info[facs.MINIMAS], adj=p_ty)

        return x_values, y_values

    def animate_3d_empty(self, obj, attr, pdm_3d, head_pose):
        y_name = 'Y_'+attr.strip('X_')
        z_name = 'Z_'+attr.strip('X_')
        div = 40

        x_info = pdm_3d[attr]
        y_info = pdm_3d[y_name]
        z_info = pdm_3d[z_name]
        tx_adj = head_pose['pose_Tx'][facs.VALUES]
        ty_adj = head_pose['pose_Ty'][facs.VALUES]
        tz_adj = head_pose['pose_Tz'][facs.VALUES]

        self.plot_axis(obj, 0, x_info[facs.VALUES],
                       x_info[facs.MAXIMAS], adj=tx_adj, div=div)
        if not plot_all:
            self.plot_axis(obj, 0, x_info[facs.VALUES],
                           x_info[facs.MINIMAS], adj=tx_adj, div=div)
        self.plot_axis(obj, 1, y_info[facs.VALUES],
                       x_info[facs.MAXIMAS], adj=ty_adj, div=div)
        if not plot_all:
            self.plot_axis(obj, 1, y_info[facs.VALUES],
                           x_info[facs.MINIMAS], adj=ty_adj, div=div)
        self.plot_axis(obj, 2, z_info[facs.VALUES],
                       x_info[facs.MAXIMAS], adj=tz_adj,  div=div)
        if not plot_all:
            self.plot_axis(obj, 2, z_info[facs.VALUES],
                           x_info[facs.MINIMAS], adj=tz_adj, div=div)

    def delta(self, pp, startpoint, endpoints):
        sp = pp[startpoint]
        num_frames = len(sp[0])
        resutl = []
        for i in range(0, len(num_frames)):
            a = np.array(sp[0][i], sp[1][i])
            eps = []
            for e in endpoints:
                eps.append(pp[e][0][i] + pp[e][1][i])
            b = np.array(eps)
            dist = scipy.spatial.distance.cdist(a,b)
            flat_dist = [item for sublist in dist.tolist() for item in sublist]
            avg = sum(flat_dist) / len(flat_dist)
            result.append(avg)
        return result

    def animate_pdm2d(self, pdm_2d, rigid_data):
        # create all the empties
        pp = {}
        for k, v in pdm_2d.items():
            if 'y_' in k or 'frame' in k or 'timestamp' in k:
                continue
            bpy.ops.object.empty_add(type='SPHERE', radius=0.01)
            empty = bpy.context.view_layer.objects.active
            entry = k.strip('x_')
            empty.name = 'pdm2d_'+k.strip('x_')
            # animate each empty
            logger.critical('Start plotting %s: %s', k,
                        str(datetime.datetime.now()))
            x_values, y_values = self.animate_2d_empty(empty, k, pdm_2d, rigid_data)

            # post process the values
            if len(x_values) != len(y_values):
                print("Unexpected array lengths")
                continue

            if not plot_all:
                continue

            if int(entry) in [51, 62, 57, 66, 54, 12, 48, 4, 54, 11, 5, 57, 8, 53, 29, 49, 55, 9, 59, 7] + \
                              list(range(13, 15)) + list(range(3,1)):
                pp[int(entry)] = [x_values, y_values]

        if not plot_all:
            return

        # keeping deltas on the following points
        # The array is indexed by frames
        # upper lip roll: 51-62
        # lower lip roll: 57-66
        # left lip side: 54-12
        # Right lip side: 48-4
        # left lip up: 54-[13-15]
        # right lip up: 48-[3-1]
        # Left lip down: 54-11
        # Right lip down: 48-5
        # Chin: 57-8
        # left upper lip curl: 53-29
        # right upper lip curl: 49-29
        # left lower lip curl: 55-9
        # right lower lip curl: 59-7
        deltas = [{'upper-lip-roll': self.delta(pp, 51, [62]), 'lower-lip-roll': self.delta(pp, 57, [66]),
                'left-lip-side': self.delta(pp, 54, [12]), 'right-lip-side': self.delta(pp, 48, [4]),
                'left-lip-up': self.delta(pp, 54, list(range(13-16))), 'right-lip-up': self.delta(pp, 48, list(range(1, 4))),
                'left-lip-down': self.delta(pp, 48, [5]), 'right-lip-down': self.delta(pp, 48, [5]),
                'chin': self.delta(pp, 57, [8]), 'left-upper-lip-curl': self.delta(pp, 53, [29]),
                'right-upper-lip-curl': self.delta(pp, 49, [29]),
                'left-lower-lip-curl': self.delta(pp, 55, [9]),
                'right-lower-lip-curl': self.delta(pp, 59, [7])}]
        print(deltas)
        # The idea now is that we can use that delta in comparison with
        # the basis delta we collected to calculate the percentage of 

    def animate_pdm3d(self, pdm_3d, head_pose):
        # create all the empties
        for k, v in pdm_3d.items():
            if 'Y_' in k or 'Z_' in k or \
               'frame' in k or 'timestamp' in k:
                continue
            bpy.ops.object.empty_add(type='SPHERE', radius=0.05)
            empty = bpy.context.view_layer.objects.active
            empty.name = 'pdm3d_'+k.strip('X_')
            # animate each empty
            logger.critical('Start plotting %s: %s', k,
                        str(datetime.datetime.now()))
            self.animate_3d_empty(empty, k, pdm_3d, head_pose)
            #logger.critical('Finished plotting %s: %s', k,
            #            str(datetime.datetime.now()))

    def execute(self, context):
        global plot_all

        scn = context.scene
        dirname = os.path.dirname(os.path.realpath(__file__))
        csv = scn.yafr_csvfile
        ws = scn.yafr_openface_ws
        po = scn.yafr_openface_polyorder
        two_d = scn.yafr_pdm_2d
        plot_all = scn.yafr_pdm_plot_all

        set_init_state(False)

        if po >= ws:
            msg = "polyorder must be less than window_length."
            logger.critical(msg)
            self.report({'ERROR'}, msg)
            return {'FINISHED'}

        if ws % 2 == 0:
            msg = "window size needs to be an odd number"
            logger.critical(msg)
            self.report({'ERROR'}, msg)
            return {'FINISHED'}

        if not csv:
            self.report({'ERROR'}, 'No CSV file specified')
            return {'FINISHED'}

        if not os.path.isfile(csv):
            if not os.path.isfile(dirname+csv):
                msg = "bad csv file provided "+csv
                logger.critical(msg)
                self.report({'ERROR'}, msg)
                return {'FINISHED'}
            else:
                csv = dirname+csv

        # reset and reload the data base
        facs.reset_database()

        logger.critical('Start processing CSV: %s',
                    str(datetime.datetime.now()))
        rc, msg = process_csv_file(csv, ws, po)
        logger.critical('Finished processing CSV: %s',
                    str(datetime.datetime.now()))
        # animate the data
        if not rc:
            self.report({'ERROR'}, msg)
            return {'FINISHED'}
        if two_d:
            logger.critical('Start plotting 2D: %s',
                        str(datetime.datetime.now()))
            pdm2d_data = facs.get_pdm2d_data()
            rigid_data = facs.get_rigid_data()
            self.animate_pdm2d(pdm2d_data, rigid_data)
            logger.critical('Finished plotting 2D: %s',
                        str(datetime.datetime.now()))
        else:
            logger.critical('Start plotting 3D: %s',
                        str(datetime.datetime.now()))
            pdm3d_data = facs.get_pdm3d_data()
            head_pose = facs.get_facs_data()
            self.animate_pdm3d(pdm3d_data, head_pose)
            logger.critical('Finished plotting 3D: %s',
                        str(datetime.datetime.now()))

        if two_d:
            frame_end = pdm2d_data['frame'][facs.VALUES][-1]
        else:
            frame_end = pdm3d_data['frame'][facs.VALUES][-1]
        bpy.context.scene.frame_end = frame_end

        return {'FINISHED'}

class VIEW3D_PT_tools_openface(bpy.types.Panel):
    bl_label = "Open Face"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "YAFR"
    #bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        scn = context.scene
        layout = self.layout
        wm = context.window_manager
        col = layout.column(align=True)
        col.label(text="FACS Rig Name")
        col.prop(scn, "yafr_facs_rig", text='')
        col.label(text="FACS CSV file")
        col.prop(scn, "yafr_csvfile", text='')
        col.label(text="Video file")
        col.prop(scn, "yafr_videofile", text='')
        col.label(text="Animation Start Frame")
        col.prop(scn, "yafr_start_frame", text='')
        col.label(text="Smoothing Window Size")
        col.prop(scn, "yafr_openface_ws", text='')
        col.label(text="Polynomial Order")
        col.prop(scn, "yafr_openface_polyorder", text='')
        col.label(text="Animation Intensity")
        col.prop(scn, "yafr_openface_au_intensity", text='')
        col.label(text="Vertical Gaze Intensity")
        col.prop(scn, "yafr_openface_vgaze_intensity", text='')
        col.label(text="Horizontal Gaze Intensity")
        col.prop(scn, "yafr_openface_hgaze_intensity", text='')
        col.prop(scn, "yafr_openface_mouth", text='Mouth Animation')
        col.prop(scn, "yafr_openface_head", text='Head Animation')
        col = layout.column(align=False)
        col.operator('yafr.animate_face', icon='ANIM_DATA')
        col = layout.column(align=False)
        col.operator('yafr.del_animation', icon='DECORATE_ANIMATE')

class VIEW3D_PT_pdm2d_openface(bpy.types.Panel):
    bl_label = "PDM Experimental"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "YAFR"
    #bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        scn = context.scene
        layout = self.layout
        wm = context.window_manager
        col = layout.column(align=True)
        col.label(text="Experimental")
        col.prop(scn, "yafr_pdm_2d", text='2D Plotting')
        col.prop(scn, "yafr_pdm_plot_all", text='Plot All')
        col.operator('yafr.animate_pdm2d_face', icon='ANIM_DATA')
        col = layout.column(align=False)
        col.operator('yafr.rm_pdm3d_rotation', icon='ANIM_DATA')
        col = layout.column(align=False)
        col.operator('yafr.del_pdm_animation', icon='DECORATE_ANIMATE')


