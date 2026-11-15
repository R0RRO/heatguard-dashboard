"""
HeatGuard Clip v3 — carcasa imprimible en 3D, ajustada al hardware del prototipo.
Blender 4.2+ / 5.x · 1 unidad = 1 mm.

Piezas imprimibles (colección "IMPRIMIR"):
  - Tapa_Frontal      : sensor ventilado, LEDs, logo, motor, XIAO, MPU6050, antena
  - Base_Trasera      : alojamiento de la batería 50 x 40 x 6 mm y del módulo TP4056
  - Clip_Chaleco      : accesorio con lengüeta elástica (PETG)
  - Placa_Casco       : accesorio cóncavo para cinta VHB en el casco
Componentes de referencia (colección "COMPONENTES_REF", no se imprimen).

Uso: Blender > Scripting > abrir > Run Script   ·   o: blender -b -P heatguard_clip_v3.py
"""
import bpy, math
from mathutils import Vector

# ============ PARÁMETROS (mm) ============
# v3: batería LiPo 1500 mAh de 50 x 40 x 6 mm + módulo TP4056 con USB-C + cierre con ceja (media madera)
L, H = 94.0, 46.0                    # exterior: largo X, alto Z
FRONT, BACK = -8.5, 10.5             # caras: frontal (mira a -Y) y trasera; espesor T = 19
T = BACK - FRONT
WALL = 2.0
R_OUT = 4.0                          # redondeo exterior (interior = R_OUT - WALL)
SPLIT_Y = 0.5                        # plano de unión tapa / base
YBI = BACK - WALL                    # cara interior trasera
CAV = (L/2 - WALL, -(FRONT + WALL), H/2 - WALL)   # semi-dimensiones; CAV[1] = cara interior frontal (|y|)
LIP_H, LIP_T, LIP_CLR = 2.0, 0.8, 0.2   # ceja de la base: alto, espesor, holgura con la tapa

CH_X0, CH_X1 = -CAV[0], -29.0        # cámara del sensor (aislada)
DIV_X1 = -27.4                       # tabique divisor X[-29, -27.4]
SENSOR_C = (-37.0, 0.0)              # centro de la rejilla frontal (X, Z)

SCREWS = [(-40.0, 16.0), (-40.0, -16.0), (40.0, 16.0)]   # tornillos M2 x 18 (M2 x 14 sin accesorio)
BOSS_R, PILOT_R, CLEAR_R, CBORE_R = 2.5, 0.85, 1.2, 2.1

LEDS = {"LED_Estado_RGB": (5.0, -12.0), "LED_Bateria": (12.5, -12.0)}
LED_HOLE_R = 2.6
MOTOR_C = (33.0, 9.5)

XIAO = dict(x0=23.0, x1=44.0, z0=-19.8, z1=-2.0, y_back=-0.5)   # placa 21 x 17.8
USB_C = ((XIAO['z0'] + XIAO['z1']) / 2, XIAO['y_back'] - 1.0 - 1.63)   # (Z, Y) centro
SWITCH = dict(x0=28.0, x1=36.6, y0=-4.3, y1=-0.8, z0=17.4, z1=21.0)
BAT = dict(x0=-26.6, x1=24.4, y0=1.0, y1=7.2, z0=-20.5, z1=20.5)   # bahía 51 x 41 x 7 para LiPo de 50 x 40 x 6
# Módulo TP4056 con USB-C: PCB 17 x 26 x 1,4 pegado a la pared trasera, componentes hacia el frente,
# conector USB-C hacia la pared inferior.
TP = dict(x0=26.4, x1=43.4, z0=-19.0, z1=7.0, y0=YBI - 1.4, y1=YBI)
TP_USB = dict(x=(TP['x0'] + TP['x1']) / 2, y=TP['y0'] - 1.6)        # centro del conector

PLATE_T = 3.0                        # espesor base de accesorios
PLATE_X, PLATE_Z = 44.0, 20.0        # semi-medidas de la placa del accesorio
HELMET_R = 110.0                     # radio de curvatura del casco

# ============ UTILIDADES ============
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    u = bpy.context.scene.unit_settings
    u.system, u.scale_length, u.length_unit = 'METRIC', 0.001, 'MILLIMETERS'

def coll(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c

def move_to(o, c):
    for x in list(o.users_collection):
        x.objects.unlink(o)
    c.objects.link(o)
    return o

def act(o):
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o

def apply_all(o):
    act(o)
    for m in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return o

def box(name, x0, x1, y0, y1, z0, z1, r=0.0, segs=6):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0+x1)/2, (y0+y1)/2, (z0+z1)/2))
    o = bpy.context.active_object
    o.name = name
    o.scale = (x1-x0, y1-y0, z1-z0)
    bpy.ops.object.transform_apply(scale=True)
    if r > 0:
        b = o.modifiers.new("bev", 'BEVEL')
        b.width, b.segments, b.limit_method, b.affect = r, segs, 'NONE', 'EDGES'
        apply_all(o)
    return o

def cyl(name, axis, c, r, a0, a1, verts=48):
    """Cilindro con eje 'X', 'Y' o 'Z'; c = coordenadas de las otras dos ejes; a0..a1 = extensión en el eje."""
    mid, d = (a0+a1)/2, abs(a1-a0)
    if axis == 'Y':
        loc, rot = (c[0], mid, c[1]), (math.pi/2, 0, 0)
    elif axis == 'X':
        loc, rot = (mid, c[0], c[1]), (0, math.pi/2, 0)
    else:
        loc, rot = (c[0], c[1], mid), (0, 0, 0)
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d, location=loc, rotation=rot, vertices=verts)
    o = bpy.context.active_object
    o.name = name
    return apply_all(o)

def join(objs, name):
    act(objs[0])
    for o in objs:
        o.select_set(True)
    bpy.ops.object.join()
    o = bpy.context.active_object
    o.name = name
    return o

def boolean(target, tools, op):
    if not isinstance(tools, (list, tuple)):
        tools = [tools]
    for t in tools:
        m = target.modifiers.new("b", 'BOOLEAN')
        m.operation, m.object, m.solver = op, t, 'EXACT'
        act(target)
        bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.data.objects.remove(t, do_unlink=True)
    return target

def diff(t, tools):  return boolean(t, tools, 'DIFFERENCE')
def union(t, tools): return boolean(t, tools, 'UNION')
def inter(t, tools): return boolean(t, tools, 'INTERSECT')

def mat(name, rgb, metal=0.0, rough=0.5, emit=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = strength
    m.diffuse_color = (*rgb, 1)
    return m

def paint(o, m):
    o.data.materials.clear()
    o.data.materials.append(m)
    return o

def smooth(o, deg=30):
    act(o)
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(deg))
    except Exception:
        bpy.ops.object.shade_flat()

def text_mesh(s, size, loc, depth):
    bpy.ops.object.text_add(location=loc, rotation=(math.pi/2, 0, 0))
    t = bpy.context.active_object
    t.data.body, t.data.size, t.data.extrude = s, size, depth/2
    t.data.align_x, t.data.align_y = 'CENTER', 'CENTER'
    act(t)
    bpy.ops.object.convert(target='MESH')
    o = bpy.context.active_object
    import bmesh
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.01)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=0.01)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data); bm.free()
    return o

# ============ ESCENA ============
reset()
C_PRINT = coll("IMPRIMIR")
C_REF = coll("COMPONENTES_REF")

M_SHELL = mat("PETG_ASA_Gris_Claro", (0.62, 0.64, 0.66), rough=0.55)
M_BASE = mat("PETG_ASA_Gris_Base", (0.50, 0.52, 0.55), rough=0.55)
M_ACC = mat("PETG_Negro", (0.02, 0.02, 0.022), rough=0.5)
M_PCB_BLUE = mat("PCB_Azul", (0.02, 0.12, 0.45), rough=0.4)
M_PCB_PURP = mat("PCB_Morado", (0.25, 0.05, 0.4), rough=0.4)
M_PCB_BLK = mat("PCB_Negro", (0.02, 0.02, 0.02), rough=0.4)
M_METAL = mat("Metal", (0.8, 0.8, 0.82), metal=1, rough=0.25)
M_BATT = mat("Bateria_LiPo", (0.75, 0.72, 0.6), metal=0.6, rough=0.35)
M_FPC = mat("Antena_FPC", (0.9, 0.55, 0.1), rough=0.35)
M_SW = mat("Switch", (0.1, 0.1, 0.1), rough=0.6)
M_LED = mat("LED_RGB", (0.2, 1.0, 0.3), rough=0.1, emit=(0.2, 1.0, 0.3), strength=8)
M_LEDB = mat("LED_Bat", (1.0, 0.1, 0.05), rough=0.1, emit=(1.0, 0.1, 0.05), strength=6)

# ---------- 1. Carcasa completa ----------
shell = box("Carcasa", -L/2, L/2, FRONT, BACK, -H/2, H/2, r=R_OUT, segs=8)
cav = box("cav", -CAV[0], CAV[0], -CAV[1], YBI, -CAV[2], CAV[2], r=R_OUT-WALL, segs=8)
diff(shell, cav)

# Refuerzos internos (se unen a la carcasa)
adds = [box("tabique", CH_X1, DIV_X1, -CAV[1]-0.2, YBI+0.2, -CAV[2]-0.2, CAV[2]+0.2)]
for (x, z) in SCREWS:                                   # torres de tornillo
    adds.append(cyl("torre", 'Y', (x, z), BOSS_R, -CAV[1]-0.2, YBI+0.2, 32))
for (x, z) in LEDS.values():                            # porta-LED (3 mm)
    adds.append(cyl("portaLED", 'Y', (x, z), 3.5, -CAV[1]-0.2, -3.5, 40))
for z0, z1 in ((-15.0, -13.0), (-8.0, -6.0)):          # apoyos de la XIAO
    adds.append(box("apoyoXIAO", XIAO['x0']-0.4, XIAO['x0']+1.0, -CAV[1]-0.2, XIAO['y_back']-1.05, z0, z1))
for x0, x1 in ((SWITCH['x0']-1, SWITCH['x0']), (SWITCH['x1'], SWITCH['x1']+1)):   # guías del switch
    adds.append(box("guiaSW", x0, x1, -CAV[1]-0.2, SWITCH['y1'], SWITCH['z0']-1, CAV[2]+0.2))
ring_o = cyl("anilloMotor", 'Y', MOTOR_C, 5.9, -CAV[1]-0.2, -CAV[1]+0.8, 48)
diff(ring_o, cyl("x", 'Y', MOTOR_C, 5.3, -CAV[1]-1, 0, 48))
adds.append(ring_o)
for s in (1, -1):                                       # rieles del sensor HTU21D
    adds.append(box("rielHTU", -42.0, -32.0, -CAV[1]-0.2, -3.55, *sorted((s*4.5, s*6.85))))
    adds.append(box("pestañaHTU", -42.0, -32.0, -3.56, -1.2, *sorted((s*5.8, s*6.85))))
# Soporte del módulo TP4056 (pegado a la pared trasera, componentes hacia el frente)
tp_ribs = [
    box("nervioTP_izq", TP['x0']-1.4, TP['x0']-0.2, TP['y0']-0.6, YBI+0.2, TP['z0']-1.0, TP['z1']-0.5),
    box("nervioTP_der", TP['x1']+0.2, CAV[0]+0.2, TP['y0']-0.6, YBI+0.2, TP['z0']-1.0, TP['z1']-0.5),
    box("topeTP_a", TP['x0']+1.0, TP['x0']+4.5, TP['y0']-0.6, YBI+0.2, TP['z1']+0.2, TP['z1']+1.4),
    box("topeTP_b", TP['x1']-4.5, TP['x1']-1.0, TP['y0']-0.6, YBI+0.2, TP['z1']+0.2, TP['z1']+1.4),
]
adds += tp_ribs
union(shell, adds)

# Cortes
def make_cuts(front_side=True):
    cuts = []
    if front_side:
        for (x, z) in LEDS.values():
            cuts.append(cyl("hLED", 'Y', (x, z), LED_HOLE_R, FRONT-1, -3.4, 40))
        holes = []                                     # rejilla hexagonal del sensor
        p = 1.9
        for i in range(-4, 5):
            for j in range(-4, 5):
                dx = i*p + (p/2 if j % 2 else 0)
                dz = j*p*0.866
                if math.hypot(dx, dz) <= 4.3:
                    holes.append(cyl("h", 'Y', (SENSOR_C[0]+dx, SENSOR_C[1]+dz), 0.65, FRONT-1, -CAV[1]+0.5, 12))
        cuts.append(join(holes, "rejilla"))
        groove = cyl("ranura", 'Y', SENSOR_C, 6.4, FRONT-1, FRONT+0.6, 64)   # anillo grabado
        diff(groove, cyl("x", 'Y', SENSOR_C, 5.6, FRONT-2, FRONT+2, 64))
        cuts.append(groove)
    vents = []
    for x in (-41.0, -37.0, -33.0):                     # ventilación superior e inferior
        for zs in (-1, 1):
            vents.append(box("v", x-0.8, x+0.8, -4.5, 4.5, *sorted((zs*(H/2+1), zs*(CAV[2]-1)))))
    for z in (-6.0, -2.0, 2.0, 6.0):                    # ventilación lateral
        vents.append(box("v", -L/2-1, -CAV[0]+1, -4.5, 4.5, z-0.8, z+0.8))
    cuts.append(join(vents, "ventilacion"))
    uz, uy = USB_C                                      # abertura USB-C de la XIAO (pared derecha)
    cuts.append(box("usb", CAV[0]-1, L/2+1, uy-3.25, uy+3.25, uz-5.75, uz+5.75, r=1.2, segs=4))
    # abertura USB-C del TP4056 (pared inferior), con holgura para el enchufe
    cuts.append(box("usbTP", TP_USB['x']-6.2, TP_USB['x']+6.2, TP_USB['y']-3.4, TP_USB['y']+3.4,
                    -H/2-1, -CAV[2]+1, r=1.2, segs=4))
    return cuts

sx = (SWITCH['x0']+SWITCH['x1'])/2
cuts = make_cuts(True)
cuts.append(box("slotSW", sx-2.0, sx+2.0, -3.5, -1.6, CAV[2]-1, H/2+1))   # ranura del switch
cuts.append(box("pasoCables", CH_X1-0.5, DIV_X1+0.5, -1.5, 1.5, -2.5, 2.5))
logo = text_mesh("HEATGUARD CLIP", 4.4, (-7.2, FRONT, 10.5), 1.2)   # logo grabado 0,6 mm
cuts.append(logo)
diff(shell, cuts)

# ---------- 2. División en tapa y base ----------
front = shell.copy(); front.data = shell.data.copy(); bpy.context.collection.objects.link(front)
inter(front, box("k", -L, L, -T, SPLIT_Y, -H, H))
front.name = "Tapa_Frontal"
inter(shell, box("k", -L, L, SPLIT_Y, T, -H, H))
back = shell
back.name = "Base_Trasera"
diff(front, [cyl("piloto", 'Y', (x, z), PILOT_R, -CAV[1]-1.0, SPLIT_Y+1, 24) for x, z in SCREWS])
diff(back, [cyl("pasante", 'Y', (x, z), CLEAR_R, 0, T, 24) for x, z in SCREWS])

# muescas para palanca (destornillador plano) en el borde inferior, a caballo de la junta
for o in (front, back):
    diff(o, [box("muesca", -5, 5, SPLIT_Y-LIP_H-0.6, SPLIT_Y+1.6, -H/2-1, -H/2+1.0)])

# Cierre de media madera: la base lleva una ceja exterior que entra en un rebaje de la tapa
def rim(inset, y0, y1):
    """Anillo de pared exterior (espesor = inset) entre y0 e y1, con esquinas redondeadas en el plano XZ."""
    o = box("o", -L/2, L/2, y0-6, y1+6, -H/2, H/2, r=R_OUT, segs=8)
    i = box("i", -L/2+inset, L/2-inset, y0-7, y1+7, -H/2+inset, H/2-inset, r=max(R_OUT-inset, 0.5), segs=8)
    diff(o, i)
    return inter(o, box("slab", -L, L, y0, y1, -H, H))
lip = rim(LIP_T, SPLIT_Y-LIP_H, SPLIT_Y)
diff(lip, [box("muesca", -5, 5, SPLIT_Y-LIP_H-0.6, SPLIT_Y+1.6, -H/2-1, -H/2+1.0)])
union(back, [lip])
diff(front, [rim(LIP_T+LIP_CLR, SPLIT_Y-LIP_H-LIP_CLR, SPLIT_Y+0.5)])
# la ceja no debe tapar las aberturas de la base
diff(back, make_cuts(False))
def repair(o):
    import bmesh
    bm = bmesh.new(); bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.02)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=0.02)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data); bm.free()
repair(front)
repair(back)
for o, m in ((front, M_SHELL), (back, M_BASE)):
    paint(o, m); smooth(o); move_to(o, C_PRINT)

# ---------- 3. Clip para chaleco ----------
def accessory_plate(name):
    return box(name, -PLATE_X, PLATE_X, BACK, BACK+PLATE_T, -PLATE_Z, PLATE_Z, r=1.0, segs=3)

clip = accessory_plate("Clip_Chaleco")
gap_root, gap_tip, tongue_len, tw = 3.0, 0.6, 27.0, 2.2
y_in = BACK + PLATE_T + gap_root
parts = [box("puente", -11, 11, BACK+PLATE_T-0.5, y_in+tw, PLATE_Z-5.0, PLATE_Z, r=0.8, segs=3)]
th = math.atan((gap_root-gap_tip)/tongue_len)
tg = box("lengueta", -11, 11, 0, tw, -tongue_len, 0.0)
tg.rotation_euler.x = -th; tg.location = (0, y_in, PLATE_Z); apply_all(tg)
act(tg); bpy.ops.object.transform_apply(location=True)
parts.append(tg)
tip_y = y_in - tongue_len*math.sin(th)
tip_z = PLATE_Z - tongue_len*math.cos(th)
fl = box("punta", -11, 11, 0, tw, -5.0, 0.4)
fl.rotation_euler.x = math.radians(35); fl.location = (0, tip_y, tip_z); apply_all(fl)
act(fl); bpy.ops.object.transform_apply(location=True)
parts.append(fl)
parts.append(cyl("resalte", 'X', (tip_y-0.1, tip_z+1.2), 0.9, -11, 11, 24))
union(clip, parts)
diff(clip, [cyl("h", 'Y', (x, z), CLEAR_R, BACK-1, BACK+PLATE_T+1, 24) for x, z in SCREWS]
          + [cyl("cb", 'Y', (x, z), CBORE_R, BACK+1.0, BACK+PLATE_T+1, 32) for x, z in SCREWS])
paint(clip, M_ACC); smooth(clip); move_to(clip, C_PRINT)

# ---------- 4. Placa para casco (cóncava, cinta VHB) ----------
sag = HELMET_R - math.sqrt(HELMET_R**2 - PLATE_X**2)
helmet = box("Placa_Casco", -PLATE_X, PLATE_X, BACK, BACK+PLATE_T+sag+1, -PLATE_Z, PLATE_Z, r=1.0, segs=3)
diff(helmet, cyl("casco", 'Z', (0, BACK+PLATE_T+HELMET_R), HELMET_R, -30, 30, 256))
diff(helmet, [cyl("h", 'Y', (x, z), CLEAR_R, BACK-1, BACK+20, 24) for x, z in SCREWS]
            + [cyl("cb", 'Y', (x, z), CBORE_R, BACK+1.0, BACK+20, 32) for x, z in SCREWS])
paint(helmet, M_ACC); smooth(helmet); move_to(helmet, C_PRINT)
helmet.hide_set(True); helmet.hide_render = True        # alternativa al clip

# ---------- 5. Componentes de referencia ----------
E = 0.05   # holgura para chequeo de interferencias
refs = []
def ref(o, m, name):
    o.name = name; paint(o, m); move_to(o, C_REF); refs.append(o); return o

uz, uy = USB_C
x = XIAO
xiao = box("p", x['x0'], x['x1'], x['y_back']-1.0, x['y_back'], x['z0'], x['z1'], r=0.6, segs=2)
union(xiao, [box("shield", x['x0']+3.5, x['x0']+14.0, x['y_back']-1.8, x['y_back']-0.9, x['z0']+3.3, x['z1']-3.0)])
ref(xiao, M_PCB_BLK, "REF_XIAO_ESP32C3")
ref(box("p", x['x1']-7.3, x['x1']+0.2, uy-1.63, uy+1.63, uz-4.47, uz+4.47, r=0.8, segs=3), M_METAL, "REF_USB-C_XIAO")
ref(box("p", BAT['x0']+0.5, BAT['x1']-0.5, BAT['y0'], BAT['y1']-0.2, BAT['z0']+0.5, BAT['z1']-0.5, r=0.8, segs=3), M_BATT, "REF_Bateria_LiPo_1500mAh_50x40x6")
gy = box("p", -27.2, -6.2, -5.4, -3.8, -20.4, -4.6)
union(gy, [box("chip", -19, -15, -3.85, -2.9, -14.5, -10.5)])
ref(gy, M_PCB_BLUE, "REF_GY-521_MPU6050")
htu = box("p", -43.75+E, -30.25-E, -3.5, -1.9, -5.25, 5.25)
union(htu, [box("chip", -38, -36, -3.9, -3.45, -1, 1)])
ref(htu, M_PCB_PURP, "REF_HTU21D_GY-21")
ref(cyl("p", 'Y', MOTOR_C, 5.0, -CAV[1]+E, -CAV[1]+3.0, 40), M_METAL, "REF_Motor_Vibracion_10x3")
ref(box("p", -27.2, 12.8, -CAV[1]+E, -CAV[1]+0.25, 1.1, 19.0), M_FPC, "REF_Antena_FPC_40x20")
sw = box("p", SWITCH['x0']+E, SWITCH['x1']-E, SWITCH['y0'], SWITCH['y1'], SWITCH['z0'], SWITCH['z1']-E)
union(sw, [box("palanca", sx-0.75, sx+0.75, -3.3, -1.8, SWITCH['z1']-0.2, H/2+1.5)])
ref(sw, M_SW, "REF_Switch_SS12D00")
for (nm, (lx, lz)), m in zip(LEDS.items(), (M_LED, M_LEDB)):
    body = cyl("p", 'Y', (lx, lz), 2.5, FRONT-0.1, -3.5, 40)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=2.5, location=(lx, FRONT-0.1, lz), segments=24, ring_count=12)
    dome = bpy.context.active_object
    flange = cyl("f", 'Y', (lx, lz), 2.9, -3.45, -2.45, 40)
    led = join([body, dome, flange], "p")
    ref(led, m, "REF_" + nm)
# módulo TP4056 (PCB + conector USB-C + dos chips)
tp = box("p", TP['x0'], TP['x1'], TP['y0'], TP['y1'], TP['z0'], TP['z1'])
union(tp, [box("chip1", TP['x0']+3, TP['x0']+8, TP['y0']-1.2, TP['y0'], TP['z1']-10, TP['z1']-5),
           box("chip2", TP['x1']-9, TP['x1']-4, TP['y0']-1.0, TP['y0'], TP['z1']-18, TP['z1']-14)])
ref(tp, M_PCB_BLUE, "REF_TP4056_PCB")
ref(box("p", TP_USB['x']-4.5, TP_USB['x']+4.5, TP_USB['y']-1.6, TP_USB['y']+1.6, TP['z0']-1.5, TP['z0']+6.0, r=0.8, segs=3),
    M_METAL, "REF_TP4056_USB-C")
for o in refs:
    smooth(o)

# ---------- 6. Exportación (STL orientados para imprimir) ----------
import os
OUT = os.environ.get("HG_OUT", "/tmp/hg_out")
os.makedirs(OUT, exist_ok=True)
import mathutils
def export_stl(o, name, M):
    """Copia el objeto, aplica la matriz de orientación M (3x3 + traslación) y exporta."""
    c = o.copy(); c.data = o.data.copy(); bpy.context.collection.objects.link(c)
    c.hide_set(False)
    c.data.transform(M)
    c.matrix_world = mathutils.Matrix.Identity(4)
    act(c)
    bpy.ops.wm.stl_export(filepath=os.path.join(OUT, name), export_selected_objects=True)
    bpy.data.objects.remove(c, do_unlink=True)
def Mx(rows, t):
    return mathutils.Matrix([[*rows[0], t[0]], [*rows[1], t[1]], [*rows[2], t[2]], [0, 0, 0, 1]])
# tapa: cara frontal sobre la cama; +Z impresión = hacia la base
export_stl(front, "HeatGuard_Tapa_Frontal.stl", Mx([(1, 0, 0), (0, 0, -1), (0, 1, 0)], (0, 0, -FRONT)))
# base: dorso sobre la cama
export_stl(back, "HeatGuard_Base_Trasera.stl", Mx([(1, 0, 0), (0, 0, 1), (0, -1, 0)], (0, 0, BACK)))
# clip: de canto (los pliegues de capa siguen el perfil de la lengüeta)
export_stl(clip, "HeatGuard_Clip_Chaleco.stl", Mx([(0, 0, 1), (0, 1, 0), (-1, 0, 0)], (0, -BACK, PLATE_X)))
# placa casco: cara plana sobre la cama
helmet.hide_set(False)
export_stl(helmet, "HeatGuard_Placa_Casco.stl", Mx([(1, 0, 0), (0, 0, -1), (0, 1, 0)], (0, 0, -BACK)))
helmet.hide_set(True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "heatguard_clip_v3.blend"))
print("OK", OUT)
