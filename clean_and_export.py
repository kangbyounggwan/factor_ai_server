
import bpy, os, sys, traceback
from mathutils import Vector

def log(msg):
    print(msg, flush=True)

def bbox_volume(o):
    d = o.dimensions
    return float(d.x*d.y*d.z)

def import_any(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.glb', '.gltf'):
        bpy.ops.preferences.addon_enable(module='io_scene_gltf2')
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == '.obj':
        bpy.ops.preferences.addon_enable(module='io_scene_obj')
        bpy.ops.import_scene.obj(filepath=path, axis_forward='-Z', axis_up='Y')
    elif ext == '.stl':
        bpy.ops.preferences.addon_enable(module='io_mesh_stl')
        bpy.ops.import_mesh.stl(filepath=path)
    else:
        raise RuntimeError(f'Unsupported format: {ext}')

def main(in_path, out_glb, min_verts, min_bbox_vol, max_part_ratio, decimate_ratio, solidify_thickness, auto_orient):
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        import_any(in_path)

        meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
        if not meshes:
            raise RuntimeError("No mesh found")

        # Select all and join
        bpy.ops.object.select_all(action='DESELECT')
        for o in meshes: o.select_set(True)
        bpy.context.view_layer.objects.active = meshes[0]
        if len(meshes)>1:
            bpy.ops.object.join()
        obj = bpy.context.view_layer.objects.active

        # Apply transforms
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

        # Get model dimensions
        bb = obj.dimensions
        log(f"Model dimensions: {bb.x:.2f} x {bb.y:.2f} x {bb.z:.2f}")

        # ========== BASIC CLEANING (MINIMAL PROCESSING) ==========

        # 1) Weld - 중복 버텍스 병합 (기본 정리)
        log("[1/4] Welding duplicate vertices...")
        weld = obj.modifiers.new("Weld","WELD")
        weld.merge_threshold = 0.0008
        bpy.ops.object.modifier_apply(modifier=weld.name)

        # 2) Fix non-manifold - 기본 수정만 (구멍 메우기, 노멀 통일)
        log("[2/4] Fixing non-manifold geometry...")
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        try:
            bpy.ops.mesh.select_non_manifold()
            bpy.ops.mesh.fill_holes(sides=0)
        except Exception as _:
            pass
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.mesh.remove_doubles(threshold=0.0001)
        bpy.ops.object.mode_set(mode='OBJECT')

        # 3) Separate and remove only very small loose parts (optional)
        log("[3/4] Removing very small loose parts...")
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.separate(type='LOOSE')
        except Exception as _:
            pass
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.update()

        # Remove only extremely small parts (very strict threshold)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        to_delete = []
        parts = [o for o in bpy.context.scene.objects if o.type == 'MESH']

        for o in parts:
            try:
                eval_obj = o.evaluated_get(depsgraph)
                me = eval_obj.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
                vcount = len(me.vertices)
                vol = float(o.dimensions.x * o.dimensions.y * o.dimensions.z)
                eval_obj.to_mesh_clear()
            except ReferenceError:
                continue

            # 매우 작은 파트만 제거 (기본 임계값의 1/10)
            if vcount < min_verts // 10 or vol < min_bbox_vol:
                to_delete.append(o)
                log(f"  - Remove tiny part: verts={vcount}, vol={vol:.6f}")

        if to_delete:
            bpy.ops.object.select_all(action='DESELECT')
            for o in to_delete:
                if o.name in bpy.context.scene.objects:
                    o.select_set(True)
            bpy.ops.object.delete()
        log(f"Removed {len(to_delete)} tiny parts")
        bpy.context.view_layer.update()

        # 4) Join remaining parts
        log("[4/4] Joining remaining parts...")
        parts=[o for o in bpy.context.scene.objects if o.type=='MESH']
        if not parts:
            raise RuntimeError("No mesh after cleaning")
        bpy.ops.object.select_all(action='DESELECT')
        for o in parts: o.select_set(True)
        bpy.context.view_layer.objects.active = parts[0]
        if len(parts)>1:
            bpy.ops.object.join()
        obj = bpy.context.view_layer.objects.active

        # Apply smooth shading
        bpy.ops.object.shade_smooth()

        # 최종 통계
        final_verts = len(obj.data.vertices)
        final_faces = len(obj.data.polygons)
        log(f"Final mesh: {final_verts} vertices, {final_faces} faces")

        # ========== BASIC CLEANING END ==========

        # Export as GLB
        bpy.ops.export_scene.gltf(filepath=out_glb, export_format='GLB', use_selection=False)
        if not os.path.exists(out_glb) or os.path.getsize(out_glb)==0:
            raise RuntimeError("GLB export failed")
        log(f"EXPORTED: {out_glb}")

    except Exception as e:
        log("ERROR: " + str(e))
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    # Args: -- in_path out_glb min_verts min_bbox_vol max_part_ratio decimate_ratio solidify_thickness auto_orient
    args = sys.argv
    if "--" in args:
        idx = args.index("--")
        in_path            = args[idx+1]
        out_glb            = args[idx+2]
        min_verts          = int(args[idx+3])
        min_bbox_vol       = float(args[idx+4])
        max_part_ratio     = float(args[idx+5])
        decimate_ratio     = float(args[idx+6])
        solidify_thickness = float(args[idx+7])
        auto_orient        = args[idx+8].lower() == 'true'
        main(in_path, out_glb, min_verts, min_bbox_vol, max_part_ratio, decimate_ratio, solidify_thickness, auto_orient)
    else:
        print("No arguments"); sys.exit(1)
