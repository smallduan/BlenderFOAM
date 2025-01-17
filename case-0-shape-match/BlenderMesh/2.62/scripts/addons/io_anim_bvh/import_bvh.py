# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

# Script copyright (C) Campbell Barton

from math import radians

import bpy
from mathutils import Vector, Euler, Matrix


class BVH_Node(object):
    __slots__ = (
    'name',  # bvh joint name
    'parent',  # BVH_Node type or None for no parent
    'children',  # a list of children of this type.
    'rest_head_world',  # worldspace rest location for the head of this node
    'rest_head_local',  # localspace rest location for the head of this node
    'rest_tail_world',  # worldspace rest location for the tail of this node
    'rest_tail_local',  # worldspace rest location for the tail of this node
    'channels',  # list of 6 ints, -1 for an unused channel, otherwise an index for the BVH motion data lines, lock triple then rot triple
    'rot_order',  # a triple of indices as to the order rotation is applied. [0,1,2] is x/y/z - [None, None, None] if no rotation.
    'rot_order_str',  # same as above but a string 'XYZ' format.
    'anim_data',  # a list one tuple's one for each frame. (locx, locy, locz, rotx, roty, rotz), euler rotation ALWAYS stored xyz order, even when native used.
    'has_loc',  # Conveinience function, bool, same as (channels[0]!=-1 or channels[1]!=-1 channels[2]!=-1)
    'has_rot',  # Conveinience function, bool, same as (channels[3]!=-1 or channels[4]!=-1 channels[5]!=-1)
    'temp')  # use this for whatever you want

    _eul_order_lookup = {(0, 1, 2): 'XYZ',
                         (0, 2, 1): 'XZY',
                         (1, 0, 2): 'YXZ',
                         (1, 2, 0): 'YZX',
                         (2, 0, 1): 'ZXY',
                         (2, 1, 0): 'ZYX',
                         }

    def __init__(self, name, rest_head_world, rest_head_local, parent, channels, rot_order):
        self.name = name
        self.rest_head_world = rest_head_world
        self.rest_head_local = rest_head_local
        self.rest_tail_world = None
        self.rest_tail_local = None
        self.parent = parent
        self.channels = channels
        self.rot_order = tuple(rot_order)
        self.rot_order_str = BVH_Node._eul_order_lookup[self.rot_order]

        # convenience functions
        self.has_loc = channels[0] != -1 or channels[1] != -1 or channels[2] != -1
        self.has_rot = channels[3] != -1 or channels[4] != -1 or channels[5] != -1

        self.children = []

        # list of 6 length tuples: (lx,ly,lz, rx,ry,rz)
        # even if the channels arnt used they will just be zero
        #
        self.anim_data = [(0, 0, 0, 0, 0, 0)]

    def __repr__(self):
        return 'BVH name:"%s", rest_loc:(%.3f,%.3f,%.3f), rest_tail:(%.3f,%.3f,%.3f)' %\
        (self.name,\
        self.rest_head_world.x, self.rest_head_world.y, self.rest_head_world.z,\
        self.rest_head_world.x, self.rest_head_world.y, self.rest_head_world.z)


def read_bvh(context, file_path, rotate_mode='XYZ', global_scale=1.0):
    # File loading stuff
    # Open the file for importing
    file = open(file_path, 'rU')

    # Seperate into a list of lists, each line a list of words.
    file_lines = file.readlines()
    # Non standard carrage returns?
    if len(file_lines) == 1:
        file_lines = file_lines[0].split('\r')

    # Split by whitespace.
    file_lines = [ll for ll in [l.split() for l in file_lines] if ll]

    # Create hierarchy as empties
    if file_lines[0][0].lower() == 'hierarchy':
        #print 'Importing the BVH Hierarchy for:', file_path
        pass
    else:
        raise 'ERROR: This is not a BVH file'

    bvh_nodes = {None: None}
    bvh_nodes_serial = [None]

    channelIndex = -1

    lineIdx = 0  # An index for the file.
    while lineIdx < len(file_lines) - 1:
        #...
        if file_lines[lineIdx][0].lower() == 'root' or file_lines[lineIdx][0].lower() == 'joint':

            # Join spaces into 1 word with underscores joining it.
            if len(file_lines[lineIdx]) > 2:
                file_lines[lineIdx][1] = '_'.join(file_lines[lineIdx][1:])
                file_lines[lineIdx] = file_lines[lineIdx][:2]

            # MAY NEED TO SUPPORT MULTIPLE ROOT's HERE!!!, Still unsure weather multiple roots are possible.??

            # Make sure the names are unique- Object names will match joint names exactly and both will be unique.
            name = file_lines[lineIdx][1]

            #print '%snode: %s, parent: %s' % (len(bvh_nodes_serial) * '  ', name,  bvh_nodes_serial[-1])

            lineIdx += 2  # Increment to the next line (Offset)
            rest_head_local = Vector((float(file_lines[lineIdx][1]), float(file_lines[lineIdx][2]), float(file_lines[lineIdx][3]))) * global_scale
            lineIdx += 1  # Increment to the next line (Channels)

            # newChannel[Xposition, Yposition, Zposition, Xrotation, Yrotation, Zrotation]
            # newChannel references indecies to the motiondata,
            # if not assigned then -1 refers to the last value that will be added on loading at a value of zero, this is appended
            # We'll add a zero value onto the end of the MotionDATA so this is always refers to a value.
            my_channel = [-1, -1, -1, -1, -1, -1]
            my_rot_order = [None, None, None]
            rot_count = 0
            for channel in file_lines[lineIdx][2:]:
                channel = channel.lower()
                channelIndex += 1  # So the index points to the right channel
                if channel == 'xposition':
                    my_channel[0] = channelIndex
                elif channel == 'yposition':
                    my_channel[1] = channelIndex
                elif channel == 'zposition':
                    my_channel[2] = channelIndex

                elif channel == 'xrotation':
                    my_channel[3] = channelIndex
                    my_rot_order[rot_count] = 0
                    rot_count += 1
                elif channel == 'yrotation':
                    my_channel[4] = channelIndex
                    my_rot_order[rot_count] = 1
                    rot_count += 1
                elif channel == 'zrotation':
                    my_channel[5] = channelIndex
                    my_rot_order[rot_count] = 2
                    rot_count += 1

            channels = file_lines[lineIdx][2:]

            my_parent = bvh_nodes_serial[-1]  # account for none

            # Apply the parents offset accumulatively
            if my_parent is None:
                rest_head_world = Vector(rest_head_local)
            else:
                rest_head_world = my_parent.rest_head_world + rest_head_local

            bvh_node = bvh_nodes[name] = BVH_Node(name, rest_head_world, rest_head_local, my_parent, my_channel, my_rot_order)

            # If we have another child then we can call ourselves a parent, else
            bvh_nodes_serial.append(bvh_node)

        # Account for an end node
        if file_lines[lineIdx][0].lower() == 'end' and file_lines[lineIdx][1].lower() == 'site':  # There is sometimes a name after 'End Site' but we will ignore it.
            lineIdx += 2  # Increment to the next line (Offset)
            rest_tail = Vector((float(file_lines[lineIdx][1]), float(file_lines[lineIdx][2]), float(file_lines[lineIdx][3]))) * global_scale

            bvh_nodes_serial[-1].rest_tail_world = bvh_nodes_serial[-1].rest_head_world + rest_tail
            bvh_nodes_serial[-1].rest_tail_local = bvh_nodes_serial[-1].rest_head_local + rest_tail

            # Just so we can remove the Parents in a uniform way- End has kids
            # so this is a placeholder
            bvh_nodes_serial.append(None)

        if len(file_lines[lineIdx]) == 1 and file_lines[lineIdx][0] == '}':  # == ['}']
            bvh_nodes_serial.pop()  # Remove the last item

        if len(file_lines[lineIdx]) == 1 and file_lines[lineIdx][0].lower() == 'motion':
            #print '\nImporting motion data'
            lineIdx += 3  # Set the cursor to the first frame
            break

        lineIdx += 1

    # Remove the None value used for easy parent reference
    del bvh_nodes[None]
    # Dont use anymore
    del bvh_nodes_serial

    bvh_nodes_list = bvh_nodes.values()

    while lineIdx < len(file_lines):
        line = file_lines[lineIdx]
        for bvh_node in bvh_nodes_list:
            #for bvh_node in bvh_nodes_serial:
            lx = ly = lz = rx = ry = rz = 0.0
            channels = bvh_node.channels
            anim_data = bvh_node.anim_data
            if channels[0] != -1:
                lx = global_scale * float(line[channels[0]])

            if channels[1] != -1:
                ly = global_scale * float(line[channels[1]])

            if channels[2] != -1:
                lz = global_scale * float(line[channels[2]])

            if channels[3] != -1 or channels[4] != -1 or channels[5] != -1:

                rx = radians(float(line[channels[3]]))
                ry = radians(float(line[channels[4]]))
                rz = radians(float(line[channels[5]]))

            # Done importing motion data #
            anim_data.append((lx, ly, lz, rx, ry, rz))
        lineIdx += 1

    # Assign children
    for bvh_node in bvh_nodes.values():
        bvh_node_parent = bvh_node.parent
        if bvh_node_parent:
            bvh_node_parent.children.append(bvh_node)

    # Now set the tip of each bvh_node
    for bvh_node in bvh_nodes.values():

        if not bvh_node.rest_tail_world:
            if len(bvh_node.children) == 0:
                # could just fail here, but rare BVH files have childless nodes
                bvh_node.rest_tail_world = Vector(bvh_node.rest_head_world)
                bvh_node.rest_tail_local = Vector(bvh_node.rest_head_local)
            elif len(bvh_node.children) == 1:
                bvh_node.rest_tail_world = Vector(bvh_node.children[0].rest_head_world)
                bvh_node.rest_tail_local = bvh_node.rest_head_local + bvh_node.children[0].rest_head_local
            else:
                # allow this, see above
                #if not bvh_node.children:
                #	raise 'error, bvh node has no end and no children. bad file'

                # Removed temp for now
                rest_tail_world = Vector((0.0, 0.0, 0.0))
                rest_tail_local = Vector((0.0, 0.0, 0.0))
                for bvh_node_child in bvh_node.children:
                    rest_tail_world += bvh_node_child.rest_head_world
                    rest_tail_local += bvh_node_child.rest_head_local

                bvh_node.rest_tail_world = rest_tail_world * (1.0 / len(bvh_node.children))
                bvh_node.rest_tail_local = rest_tail_local * (1.0 / len(bvh_node.children))

        # Make sure tail isnt the same location as the head.
        if (bvh_node.rest_tail_local - bvh_node.rest_head_local).length <= 0.001 * global_scale:
            print("\tzero length node found:", bvh_node.name)
            bvh_node.rest_tail_local.y = bvh_node.rest_tail_local.y + global_scale / 10
            bvh_node.rest_tail_world.y = bvh_node.rest_tail_world.y + global_scale / 10

    return bvh_nodes


def bvh_node_dict2objects(context, bvh_name, bvh_nodes, rotate_mode='NATIVE', frame_start=1, IMPORT_LOOP=False):

    if frame_start < 1:
        frame_start = 1

    scene = context.scene
    for obj in scene.objects:
        obj.select = False

    objects = []

    def add_ob(name):
        obj = bpy.data.objects.new(name, None)
        scene.objects.link(obj)
        objects.append(obj)
        obj.select = True

        # nicer drawing.
        obj.empty_draw_type = 'CUBE'
        obj.empty_draw_size = 0.1

        return obj

    # Add objects
    for name, bvh_node in bvh_nodes.items():
        bvh_node.temp = add_ob(name)
        bvh_node.temp.rotation_mode = bvh_node.rot_order_str[::-1]

    # Parent the objects
    for bvh_node in bvh_nodes.values():
        for bvh_node_child in bvh_node.children:
            bvh_node_child.temp.parent = bvh_node.temp

    # Offset
    for bvh_node in bvh_nodes.values():
        # Make relative to parents offset
        bvh_node.temp.location = bvh_node.rest_head_local

    # Add tail objects
    for name, bvh_node in bvh_nodes.items():
        if not bvh_node.children:
            ob_end = add_ob(name + '_end')
            ob_end.parent = bvh_node.temp
            ob_end.location = bvh_node.rest_tail_world - bvh_node.rest_head_world

    for name, bvh_node in bvh_nodes.items():
        obj = bvh_node.temp

        for frame_current in range(len(bvh_node.anim_data)):

            lx, ly, lz, rx, ry, rz = bvh_node.anim_data[frame_current]

            if bvh_node.has_loc:
                obj.delta_location = Vector((lx, ly, lz)) - bvh_node.rest_head_world
                obj.keyframe_insert("delta_location", index=-1, frame=frame_start + frame_current)

            if bvh_node.has_rot:
                obj.delta_rotation_euler = rx, ry, rz
                obj.keyframe_insert("delta_rotation_euler", index=-1, frame=frame_start + frame_current)

    return objects


def bvh_node_dict2armature(context,
                           bvh_name,
                           bvh_nodes,
                           rotate_mode='XYZ',
                           frame_start=1,
                           IMPORT_LOOP=False,
                           global_matrix=None,
                           ):

    if frame_start < 1:
        frame_start = 1

    # Add the new armature,
    scene = context.scene
    for obj in scene.objects:
        obj.select = False

    arm_data = bpy.data.armatures.new(bvh_name)
    arm_ob = bpy.data.objects.new(bvh_name, arm_data)

    scene.objects.link(arm_ob)

    arm_ob.select = True
    scene.objects.active = arm_ob

    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    bpy.ops.object.mode_set(mode='EDIT', toggle=False)

    # Get the average bone length for zero length bones, we may not use this.
    average_bone_length = 0.0
    nonzero_count = 0
    for bvh_node in bvh_nodes.values():
        l = (bvh_node.rest_head_local - bvh_node.rest_tail_local).length
        if l:
            average_bone_length += l
            nonzero_count += 1

    # Very rare cases all bones couldbe zero length???
    if not average_bone_length:
        average_bone_length = 0.1
    else:
        # Normal operation
        average_bone_length = average_bone_length / nonzero_count

    # XXX, annoying, remove bone.
    while arm_data.edit_bones:
        arm_ob.edit_bones.remove(arm_data.edit_bones[-1])

    ZERO_AREA_BONES = []
    for name, bvh_node in bvh_nodes.items():
        # New editbone
        bone = bvh_node.temp = arm_data.edit_bones.new(name)

        bone.head = bvh_node.rest_head_world
        bone.tail = bvh_node.rest_tail_world

        # Zero Length Bones! (an exceptional case)
        if (bone.head - bone.tail).length < 0.001:
            print("\tzero length bone found:", bone.name)
            if bvh_node.parent:
                ofs = bvh_node.parent.rest_head_local - bvh_node.parent.rest_tail_local
                if ofs.length:  # is our parent zero length also?? unlikely
                    bone.tail = bone.tail - ofs
                else:
                    bone.tail.y = bone.tail.y + average_bone_length
            else:
                bone.tail.y = bone.tail.y + average_bone_length

            ZERO_AREA_BONES.append(bone.name)

    for bvh_node in bvh_nodes.values():
        if bvh_node.parent:
            # bvh_node.temp is the Editbone

            # Set the bone parent
            bvh_node.temp.parent = bvh_node.parent.temp

            # Set the connection state
            if((not bvh_node.has_loc) and
               (bvh_node.parent.temp.name not in ZERO_AREA_BONES) and
               (bvh_node.parent.rest_tail_local == bvh_node.rest_head_local)):

                bvh_node.temp.use_connect = True

    # Replace the editbone with the editbone name,
    # to avoid memory errors accessing the editbone outside editmode
    for bvh_node in bvh_nodes.values():
        bvh_node.temp = bvh_node.temp.name

    # Now Apply the animation to the armature

    # Get armature animation data
    bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

    pose = arm_ob.pose
    pose_bones = pose.bones

    if rotate_mode == 'NATIVE':
        for bvh_node in bvh_nodes.values():
            bone_name = bvh_node.temp  # may not be the same name as the bvh_node, could have been shortened.
            pose_bone = pose_bones[bone_name]
            pose_bone.rotation_mode = bvh_node.rot_order_str

    elif rotate_mode != 'QUATERNION':
        for pose_bone in pose_bones:
            pose_bone.rotation_mode = rotate_mode
    else:
        # Quats default
        pass

    context.scene.update()

    arm_ob.animation_data_create()
    action = bpy.data.actions.new(name=bvh_name)
    arm_ob.animation_data.action = action

    # Replace the bvh_node.temp (currently an editbone)
    # With a tuple  (pose_bone, armature_bone, bone_rest_matrix, bone_rest_matrix_inv)
    for bvh_node in bvh_nodes.values():
        bone_name = bvh_node.temp  # may not be the same name as the bvh_node, could have been shortened.
        pose_bone = pose_bones[bone_name]
        rest_bone = arm_data.bones[bone_name]
        bone_rest_matrix = rest_bone.matrix_local.to_3x3()

        bone_rest_matrix_inv = Matrix(bone_rest_matrix)
        bone_rest_matrix_inv.invert()

        bone_rest_matrix_inv.resize_4x4()
        bone_rest_matrix.resize_4x4()
        bvh_node.temp = (pose_bone, bone, bone_rest_matrix, bone_rest_matrix_inv)

    # Make a dict for fast access without rebuilding a list all the time.

    # KEYFRAME METHOD, SLOW, USE IPOS DIRECT
    # TODO: use f-point samples instead (Aligorith)
    if rotate_mode != 'QUATERNION':
        prev_euler = [Euler() for i in range(len(bvh_nodes))]

    # Animate the data, the last used bvh_node will do since they all have the same number of frames
    for frame_current in range(len(bvh_node.anim_data) - 1):  # skip the first frame (rest frame)
        # print frame_current

        # if frame_current==40: # debugging
        # 	break

        scene.frame_set(frame_start + frame_current)

        # Dont neet to set the current frame
        for i, bvh_node in enumerate(bvh_nodes.values()):
            pose_bone, bone, bone_rest_matrix, bone_rest_matrix_inv = bvh_node.temp
            lx, ly, lz, rx, ry, rz = bvh_node.anim_data[frame_current + 1]

            if bvh_node.has_rot:
                # apply rotation order and convert to XYZ
                # note that the rot_order_str is reversed.
                bone_rotation_matrix = Euler((rx, ry, rz), bvh_node.rot_order_str[::-1]).to_matrix().to_4x4()
                bone_rotation_matrix = bone_rest_matrix_inv * bone_rotation_matrix * bone_rest_matrix

                if rotate_mode == 'QUATERNION':
                    pose_bone.rotation_quaternion = bone_rotation_matrix.to_quaternion()
                else:
                    euler = bone_rotation_matrix.to_euler(pose_bone.rotation_mode, prev_euler[i])
                    pose_bone.rotation_euler = euler
                    prev_euler[i] = euler

            if bvh_node.has_loc:
                pose_bone.location = (bone_rest_matrix_inv * Matrix.Translation(Vector((lx, ly, lz)) - bvh_node.rest_head_local)).to_translation()

            if bvh_node.has_loc:
                pose_bone.keyframe_insert("location")
            if bvh_node.has_rot:
                if rotate_mode == 'QUATERNION':
                    pose_bone.keyframe_insert("rotation_quaternion")
                else:
                    pose_bone.keyframe_insert("rotation_euler")

    for cu in action.fcurves:
        if IMPORT_LOOP:
            pass  # 2.5 doenst have cyclic now?

        for bez in cu.keyframe_points:
            bez.interpolation = 'LINEAR'

    # finally apply matrix
    arm_ob.matrix_world = global_matrix
    bpy.ops.object.transform_apply(rotation=True)

    return arm_ob


def load(operator,
         context,
         filepath="",
         target='ARMATURE',
         rotate_mode='NATIVE',
         global_scale=1.0,
         use_cyclic=False,
         frame_start=1,
         global_matrix=None,
         ):

    import time
    t1 = time.time()
    print('\tparsing bvh %r...' % filepath, end="")

    bvh_nodes = read_bvh(context, filepath,
            rotate_mode=rotate_mode,
            global_scale=global_scale)

    print('%.4f' % (time.time() - t1))

    frame_orig = context.scene.frame_current

    t1 = time.time()
    print('\timporting to blender...', end="")

    bvh_name = bpy.path.display_name_from_filepath(filepath)

    if target == 'ARMATURE':
        bvh_node_dict2armature(context, bvh_name, bvh_nodes,
                               rotate_mode=rotate_mode,
                               frame_start=frame_start,
                               IMPORT_LOOP=use_cyclic,
                               global_matrix=global_matrix,
                               )

    elif target == 'OBJECT':
        bvh_node_dict2objects(context, bvh_name, bvh_nodes,
                              rotate_mode=rotate_mode,
                              frame_start=frame_start,
                              IMPORT_LOOP=use_cyclic,
                              # global_matrix=global_matrix,  # TODO
                              )

    else:
        raise Exception("invalid type")

    print('Done in %.4f\n' % (time.time() - t1))

    context.scene.frame_set(frame_orig)

    return {'FINISHED'}
