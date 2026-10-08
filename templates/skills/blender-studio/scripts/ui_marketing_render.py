#!/usr/bin/env python3
"""Reusable Blender UI/marketing render kit.

Run with:
blender --background --python ui_marketing_render.py -- \
  --preset devices|conversation \
  --output <render.png> \
  --blend <source.blend> \
  [--phone-screen <png>] [--laptop-screen <png>] \
  [--width 1800 --height 1100 --transparent]
"""
import argparse
import math
import os
import sys

import bpy
from mathutils import Vector


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--preset", choices=["devices", "conversation"], required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--blend", required=True)
    p.add_argument("--phone-screen")
    p.add_argument("--laptop-screen")
    p.add_argument("--width", type=int, default=1200)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--transparent", action="store_true")
    return p.parse_args(argv)


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        pass


def mat(name, color, metallic=0.0, roughness=0.4, emission=None, emission_strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return m


def image_aspect(path, fallback=16.0 / 9.0):
    if not path or not os.path.isfile(path):
        return fallback
    try:
        img = bpy.data.images.load(path, check_existing=True)
        w, h = img.size
        return (float(w) / float(h)) if h else fallback
    except Exception:
        return fallback


def image_mat(name, path, fallback=(0.035, 0.045, 0.08)):
    if not path or not os.path.isfile(path):
        return mat(name, fallback, roughness=0.2, emission=(0.06, 0.09, 0.2), emission_strength=0.35)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nodes = m.node_tree.nodes
    links = m.node_tree.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path, check_existing=True)
    tex.interpolation = "Linear"
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.9
    bsdf.inputs["Roughness"].default_value = 0.24
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def cube(name, location, scale, material, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(location=location)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        o.data.materials.append(material)
    if bevel > 0:
        mod = o.modifiers.new("SoftEdges", "BEVEL")
        mod.width = bevel
        mod.segments = 3
    return o


def uv(name, location, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=location)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        o.data.materials.append(material)
    return o


def cyl(name, a, b, radius, material):
    a, b = Vector(a), Vector(b)
    mid = (a + b) / 2
    direction = b - a
    length = direction.length
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=radius, depth=length, location=mid)
    o = bpy.context.object
    o.name = name
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = direction.to_track_quat("Z", "Y")
    if material:
        o.data.materials.append(material)
    return o


def plane(name, location, scale, material, rotation=(math.pi / 2, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(size=2, location=location, rotation=rotation)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        o.data.materials.append(material)
    return o


def add_area(name, location, color, energy, size, target=(0, 0, 0)):
    bpy.ops.object.light_add(type="AREA", location=location)
    l = bpy.context.object
    l.name = name
    l.data.energy = energy
    l.data.shape = "DISK"
    l.data.size = size
    l.data.color = color
    direction = Vector(target) - l.location
    l.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return l


def add_camera(location, target, lens=52):
    bpy.ops.object.camera_add(location=location)
    cam = bpy.context.object
    cam.data.lens = lens
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def world_setup():
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.0025, 0.004, 0.012, 1)
    bg.inputs["Strength"].default_value = 0.18


def render_setup(a):
    scene = bpy.context.scene
    selected = None
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            scene.render.engine = candidate
            selected = candidate
            break
        except (TypeError, ValueError):
            continue
    if selected is None:
        raise RuntimeError("No supported Blender render engine is available")
    scene.render.resolution_x = a.width
    scene.render.resolution_y = a.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = bool(a.transparent)
    scene.render.image_settings.color_mode = "RGBA" if a.transparent else "RGB"
    scene.render.filepath = os.path.abspath(a.output)
    scene.render.resolution_percentage = 100
    scene.view_settings.look = "AgX - Medium High Contrast"


def make_wave(material, y=-0.35, z=1.25):
    curve = bpy.data.curves.new("VoiceWave", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.035
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    n = 72
    spline.points.add(n - 1)
    for i in range(n):
        t = i / (n - 1)
        x = -1.45 + 2.9 * t
        amp = 0.13 + 0.26 * math.exp(-((t - 0.5) / 0.27) ** 2)
        zz = z + amp * math.sin(t * math.pi * 7.0)
        yy = y + 0.08 * math.sin(t * math.pi * 3.0)
        spline.points[i].co = (x, yy, zz, 1)
    o = bpy.data.objects.new("VoiceWave", curve)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(material)
    return o


def conversation(a):
    black = mat("MatteBlack", (0.003, 0.004, 0.007), metallic=0.05, roughness=0.3)
    purple = mat("NeonPurple", (0.12, 0.02, 0.28), roughness=0.25, emission=(0.52, 0.12, 1.0), emission_strength=6.0)
    cyan = mat("NeonCyan", (0.01, 0.14, 0.27), roughness=0.25, emission=(0.05, 0.75, 1.0), emission_strength=6.0)

    # Left person: head, neck/torso and a gesturing arm.
    uv("LeftHead", (-1.42, 0, 1.95), (0.46, 0.38, 0.56), black)
    cyl("LeftNeck", (-1.42, 0, 1.52), (-1.42, 0, 1.24), 0.22, black)
    torso = uv("LeftTorso", (-1.42, 0.05, 0.63), (0.82, 0.48, 1.0), black)
    cyl("LeftArm", (-0.9, -0.02, 0.95), (-0.25, -0.18, 1.35), 0.14, black)
    uv("LeftHand", (-0.18, -0.19, 1.4), (0.18, 0.12, 0.16), black)

    # Right person: profile-like head + hair bun + leaning torso.
    uv("RightHead", (1.42, 0, 1.93), (0.44, 0.37, 0.55), black)
    uv("RightHairBun", (1.7, 0.08, 2.42), (0.27, 0.25, 0.3), black)
    cyl("RightNeck", (1.42, 0, 1.52), (1.42, 0, 1.25), 0.2, black)
    torso2 = uv("RightTorso", (1.42, 0.04, 0.62), (0.83, 0.48, 1.0), black)
    torso2.rotation_euler[1] = math.radians(-5)
    cyl("RightArm", (0.96, -0.02, 0.9), (0.48, -0.15, 1.2), 0.13, black)

    make_wave(purple)
    # Duplicate a thinner cyan wave slightly offset for two-tone light.
    wave2 = make_wave(cyan, y=-0.39, z=1.28)
    wave2.scale = (1.02, 1.0, 0.72)

    add_area("BlueRim", (-3.2, -1.2, 2.4), (0.12, 0.38, 1.0), 1050, 4.5, (-1.2, 0, 1.2))
    add_area("PurpleRim", (3.2, -1.0, 2.5), (0.7, 0.12, 1.0), 1100, 4.5, (1.2, 0, 1.2))
    add_area("SoftFront", (0, -5.0, 3.6), (0.24, 0.28, 0.55), 320, 6.0, (0, 0, 1.2))
    add_camera((0, -7.2, 2.65), (0, 0, 1.2), lens=58)


def devices(a):
    dark = mat("DeviceBlack", (0.006, 0.008, 0.014), metallic=0.72, roughness=0.2)
    edge = mat("DeviceEdge", (0.055, 0.07, 0.11), metallic=0.86, roughness=0.16)
    floor = mat("Floor", (0.004, 0.006, 0.013), metallic=0.22, roughness=0.3)
    phone_screen = image_mat("PhoneScreen", a.phone_screen)
    laptop_screen = image_mat("LaptopScreen", a.laptop_screen)
    phone_aspect = image_aspect(a.phone_screen, 390 / 844)
    laptop_aspect = image_aspect(a.laptop_screen, 16 / 9)

    plane("Floor", (0, 0.7, -0.36), (7, 5, 1), floor, rotation=(0, 0, 0))

    phone_x = 0.72
    phone_z = phone_x / phone_aspect
    phone_rot_z = math.radians(-8)
    phone = cube("PhoneBody", (-2.05, 0.0, 1.08), (phone_x + 0.09, 0.10, phone_z + 0.12), dark, bevel=0.16)
    phone.rotation_euler = (0, 0, phone_rot_z)
    plane("PhoneScreen", (-2.05, -0.111, 1.08), (phone_x, phone_z, 1), phone_screen, rotation=(math.pi / 2, 0, phone_rot_z))
    pill=cube("PhonePill", (-2.05, -0.139, 1.08 + phone_z - 0.14), (0.18, 0.02, 0.055), edge, bevel=0.045)
    pill.rotation_euler=(0,0,phone_rot_z)

    laptop_x = 2.50
    laptop_z = laptop_x / laptop_aspect
    base = cube("LaptopBase", (1.35, 0.2, -0.02), (2.72, 1.42, 0.08), edge, bevel=0.09)
    base.rotation_euler[2] = math.radians(2)
    cube("LaptopDisplay", (1.35, 0.98, laptop_z + 0.08), (laptop_x + 0.12, 0.10, laptop_z + 0.12), dark, bevel=0.09)
    plane("LaptopScreen", (1.35, 0.867, laptop_z + 0.08), (laptop_x, laptop_z, 1), laptop_screen, rotation=(math.pi / 2, 0, 0))
    cube("LaptopHinge", (1.35, 0.82, 0.12), (2.0, 0.07, 0.06), edge, bevel=0.035)

    add_area("PurpleKey", (-3.6, -2.6, 4.7), (0.45, 0.16, 1.0), 1500, 5.2, (-1.0, 0.0, 1.1))
    add_area("CyanKey", (4.0, -1.8, 4.0), (0.05, 0.6, 1.0), 1350, 5.2, (1.0, 0.0, 1.0))
    add_area("TopSoft", (0, 0, 6.4), (0.35, 0.3, 0.62), 950, 5.5, (0, 0, 0.8))
    add_camera((0.15, -10.6, 3.45), (0.1, 0.35, 1.05), lens=50)


def build_and_render(preset, output, blend, phone_screen=None, laptop_screen=None, width=1200, height=720, transparent=False):
    class A:
        pass
    a = A()
    a.preset = preset
    a.output = output
    a.blend = blend
    a.phone_screen = phone_screen
    a.laptop_screen = laptop_screen
    a.width = int(width)
    a.height = int(height)
    a.transparent = bool(transparent)

    clear()
    world_setup()
    render_setup(a)
    if a.preset == "devices":
        devices(a)
    else:
        conversation(a)

    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(a.blend)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.blend))
    bpy.ops.render.render(write_still=True)
    return {
        "preset": a.preset,
        "blend": os.path.abspath(a.blend),
        "output": os.path.abspath(a.output),
        "resolution": [a.width, a.height],
    }


def main():
    a = args()
    result = build_and_render(
        a.preset,
        a.output,
        a.blend,
        phone_screen=a.phone_screen,
        laptop_screen=a.laptop_screen,
        width=a.width,
        height=a.height,
        transparent=a.transparent,
    )
    print("SYNAPSE_UI_RENDER_RESULT=" + repr(result))


if __name__ == "__main__":
    main()
