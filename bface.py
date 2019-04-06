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

    def set_keyframes(self, result, array, slider_obj, intensity, vgi, hgi):
        global global_sliders

        for m in array:
            if not 'GZ' in slider_obj.name:
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
                if 'GZ0V' in slider_obj.name:
                    # reverse sign to get the correct up/down motion
                    #value = -value
                    gaze_intensity = vgi

                if value > 0:
                    value = value + (value * gaze_intensity)
                elif value < 0:
                    value = value - ((value * -1) * gaze_intensity)
            if intensity > 0 and not 'GZ' in slider_obj.name:
                # don't accept negative values
                if value < 0:
                    value = -value
                value = value + (value * intensity)
            slider_obj.location[0] = value
            slider_obj.keyframe_insert(data_path="location", frame=m, index=0)
            global_sliders[slider_obj.name].append(m)

    def set_every_keyframe(self, result, slider_obj, intensity):
        frame = 1
        for m in result:
            if not 'GZ' in slider_obj.name:
                value = (m / 5) * 0.377
            else:
                value = m
            if intensity > 0:
                value = value + (value * (intensity/100))
            slider_obj.location[0] = value
            if not 'GZ' in slider_obj.name:
                slider_obj.keyframe_insert(data_path="location", frame=frame, index=0)
            frame = frame + 1

    def animate_face(self, mouth, head, animation_data, intensity, vgi, hgi):
        global global_sliders_set

        # animation already done
        if global_sliders_set:
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

            slider_obj = None
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
                slider_obj = bpy.data.objects.get(slider_name)
                if not slider_obj:
                    logger.critical('slider %s not found', slider_name)
                    continue

                self.set_keyframes(result, maximas, slider_obj, intensity, vgi, hgi)
                self.set_keyframes(result, minimas, slider_obj, intensity, vgi, hgi)
                #self.set_every_keyframe(result, slider_obj, intensity, vgi, hgi)

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
            frame_end = facs_data['frame'][facs.VALUES][-1]
            bpy.context.scene.frame_end = frame_end
            return {'FINISHED'}

        self.report({'ERROR'}, msg)
        return {'FINISHED'}

class FACE_OT_pdm2d_del_animate(bpy.types.Operator):
    bl_idname = "yafr.del_pdm2d_animation"
    bl_label = "PDM Delete"
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

class FACE_OT_pdm2d_animate(bpy.types.Operator):
    bl_idname = "yafr.animate_pdm2d_face"
    bl_label = "PDM Plotting"
    bl_description = "Experimental feature"

    def plot_axis(self, obj, axis, result, array, div=800):
        if plot_all:
            f = 0
            for p in result:
                value = p / div
                if axis == 1 or axis == 2:
                    value = value * -1
                obj.location[axis] = value
                obj.keyframe_insert(data_path="location", frame=f, index=axis)
                f = f+1
            return
        for m in array:
            value = result[m] / div
            if axis == 1 or axis == 2:
                value = value * -1
            obj.location[axis] = value
            obj.keyframe_insert(data_path="location", frame=m, index=axis)

    def animate_2d_empty(self, obj, attr, pdm_2d):
        y_name = 'y_'+attr.strip('x_')

        x_info = pdm_2d[attr]
        y_info = pdm_2d[y_name]

        self.plot_axis(obj, 0, x_info[facs.VALUES], x_info[facs.MAXIMAS])
        if not plot_all:
            self.plot_axis(obj, 0, x_info[facs.VALUES], x_info[facs.MINIMAS])
        self.plot_axis(obj, 1, y_info[facs.VALUES], x_info[facs.MAXIMAS])
        if not plot_all:
            self.plot_axis(obj, 1, y_info[facs.VALUES], x_info[facs.MINIMAS])

    def animate_3d_empty(self, obj, attr, pdm_3d):
        y_name = 'Y_'+attr.strip('X_')
        z_name = 'Z_'+attr.strip('X_')
        div = 40

        x_info = pdm_3d[attr]
        y_info = pdm_3d[y_name]
        z_info = pdm_3d[z_name]

        self.plot_axis(obj, 0, x_info[facs.VALUES],
                       x_info[facs.MAXIMAS], div)
        if not plot_all:
            self.plot_axis(obj, 0, x_info[facs.VALUES],
                           x_info[facs.MINIMAS], div)
        self.plot_axis(obj, 1, y_info[facs.VALUES],
                       x_info[facs.MAXIMAS], div)
        if not plot_all:
            self.plot_axis(obj, 1, y_info[facs.VALUES],
                           x_info[facs.MINIMAS], div)
        self.plot_axis(obj, 2, z_info[facs.VALUES],
                       x_info[facs.MAXIMAS], div)
        if not plot_all:
            self.plot_axis(obj, 2, z_info[facs.VALUES],
                           x_info[facs.MINIMAS], div)

    def animate_pdm2d(self, pdm_2d):
        # create all the empties
        for k, v in pdm_2d.items():
            if 'y_' in k or 'frame' in k or 'timestamp' in k:
                continue
            bpy.ops.object.empty_add(type='SPHERE', radius=0.01)
            empty = bpy.context.view_layer.objects.active
            empty.name = 'pdm2d_'+k.strip('x_')
            # animate each empty
            logger.critical('Start plotting %s: %s', k,
                        str(datetime.datetime.now()))
            self.animate_2d_empty(empty, k, pdm_2d)
            # logger.critical('Finished plotting %s: %s', k,
            #            str(datetime.datetime.now()))

    def animate_pdm3d(self, pdm_3d):
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
            self.animate_3d_empty(empty, k, pdm_3d)
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
            self.animate_pdm2d(pdm2d_data)
            logger.critical('Finished plotting 2D: %s',
                        str(datetime.datetime.now()))
        else:
            logger.critical('Start plotting 3D: %s',
                        str(datetime.datetime.now()))
            pdm3d_data = facs.get_pdm3d_data()
            self.animate_pdm3d(pdm3d_data)
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
        col.label(text="FACS CSV file")
        col.prop(scn, "yafr_csvfile", text='')
        col.label(text="Video file")
        col.prop(scn, "yafr_videofile", text='')
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
        col.operator('yafr.del_pdm2d_animation', icon='DECORATE_ANIMATE')


