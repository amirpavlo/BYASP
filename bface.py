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
from bpy.props import EnumProperty, StringProperty, BoolVectorProperty
from . import facs_process as facs

logger = logging.getLogger(__name__)

# TODO
# create a face_map similar to phoneme_map in yasp_mapy.py
# Each entry in the map corresponds to an FACS AU/gaze and it's
# corresponding bone name with its max/min range. The map includes
# whether the bone should be rotated or moved
# Load this map
# parse the cvs to get the animation data
# insert keyframe for the first point and each entry in the minima and
# maxima lists
#

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

    def animate_face(self, animation_data):
        print('animate face')
        return

    def execute(self, context):
        scn = context.scene
        dirname = os.path.dirname(os.path.realpath(__file__))
        openface = os.path.join(dirname, "openface", "FeatureExtraction")
        video = scn.yasp_videofile
        ws = scn.yasp_openface_ws
        po = scn.yasp_openface_polyorder

        if po >= ws:
            msg = "polyorder must be less than window_length."
            logger.critical(msg)
            self.report({'ERROR'}, msg)
            return {'FINISHED'}

        # run openface on the videofile
        if not os.path.isfile(openface):
            msg = "Bad path to openFace: " + openface
            self.report({'ERROR'}, msg)
            return {'FINISHED'}
        if not os.path.isfile(video):
            msg = "Bad path to video file: " + video
            self.report({'ERROR'}, 'Bad path to video file')
            return {'FINISHED'}

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

        try:
            js, animation_data = facs.process_facs_csv(csv, ws, po)
        except Exception as e:
            logger.critical(e)
            msg = 'failed to process results\n'+traceback.format_exc()
            self.report({'ERROR'}, msg)
            return {'FINISHED'}

        if not js:
            self.report({'ERROR'}, 'Failed to process results')
            return {'FINISHED'}

        # animate the data
        self.animate_face(animation_data)

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
        col.label(text="Video file")
        col.prop(scn, "yasp_videofile", text='')
        col.label(text="Smoothing Window Size")
        col.prop(scn, "yasp_openface_ws", text='')
        col.label(text="Polynomial Order")
        col.prop(scn, "yasp_openface_polyorder", text='')
        col = layout.column(align=False)
        col.operator('yafr.animate_face', icon='ANIM_DATA')


