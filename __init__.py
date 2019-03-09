# ##### BEGIN GPL LICENSE BLOCK #####
#
#  Copyright (C) 2018 Amir Shehata
#  http://www.openmovie.com
#  amir.shehata@gmail.com

#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
import traceback
from bpy.props import EnumProperty, StringProperty, BoolVectorProperty
from . import byasp

bl_info = {
    "name": "YASP",
    "version": (0, 1),
    "blender": (2, 80, 0),
    "location": "View3D > UI > YASP",
    "author": "Amir Shehata <amir.shehata@gmail.com>",
    "description": "Yet Another Speech Parser",
    "category": "Speech Parser"
}

classes = (
    byasp.VIEW3D_PT_tools_mb_yasp,
    byasp.YASP_OT_mark,
    byasp.YASP_OT_unmark,
    byasp.YASP_OT_set,
    byasp.YASP_OT_unset,
    byasp.YASP_OT_next,
    byasp.YASP_OT_prev,
    byasp.YASP_OT_setallKeyframes,
    byasp.YASP_OT_deleteallKeyframes,
    byasp.YASP_OT_delete_seq,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.yasp_phoneme_rig = StringProperty(
        name="Phoneme Rig Name",
        subtype='FILE_NAME',
        default='',
        description='name of phoneme rig')

    bpy.types.Scene.yasp_wave_path = StringProperty(
        name="Path to wave file",
        subtype='FILE_PATH',
        default='',
        description='Path to wave file')

    bpy.types.Scene.yasp_transcript_path = StringProperty(
        name="Path to transcript file",
        subtype='FILE_PATH',
        default='',
        description='Path to transcript file')

    bpy.types.Scene.yasp_start_frame = StringProperty(
        name="Start frame",
        subtype='FILE_NAME',
        default='',
        description='Start audio on specified frame')

    bpy.types.Scene.yasp_avg_window_size = StringProperty(
        name="Avg Window",
        subtype='FILE_NAME',
        default='0',
        description='Average keyframe values within the window')

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
