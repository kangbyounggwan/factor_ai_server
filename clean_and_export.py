
import bpy, os, sys, traceback, math
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

        # 📐 Get model dimensions for calculations
        bb = obj.dimensions
        base_size = max(bb.x, bb.y, bb.z)
        total_bbox_vol = float(bb.x * bb.y * bb.z)
        log(f"Model dimensions: {bb.x:.2f} x {bb.y:.2f} x {bb.z:.2f} (base={base_size:.2f})")

        # ========== 3D PRINTING OPTIMIZATION START ==========

        # 1) Weld - 중복 버텍스 병합
        log("[1/10] Welding duplicate vertices...")
        weld = obj.modifiers.new("Weld","WELD")
        weld.merge_threshold = 0.0008
        bpy.ops.object.modifier_apply(modifier=weld.name)

        # 2) Fix non-manifold - 구멍 메우기 및 노멀 통일
        log("[2/10] Fixing non-manifold geometry...")
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        try:
            bpy.ops.mesh.select_non_manifold()
            bpy.ops.mesh.fill_holes(sides=0)  # 모든 구멍 메우기
        except Exception as _:
            pass
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.mesh.remove_doubles(threshold=0.0001)  # 중복 제거
        bpy.ops.object.mode_set(mode='OBJECT')

        # 3) Decimate - 불필요한 디테일 제거 (3D 프린터 해상도에 맞게)
        log(f"[3/10] Decimating mesh (ratio={decimate_ratio})...")
        decimate = obj.modifiers.new("Decimate", "DECIMATE")
        decimate.ratio = decimate_ratio
        decimate.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=decimate.name)

        # 4) Voxel Remesh - 균일한 메시 재구성
        log("[4/10] Voxel remeshing...")
        voxel = max(base_size/200.0, 0.0005)
        rm = obj.modifiers.new("Remesh","REMESH")
        rm.mode = 'VOXEL'
        rm.voxel_size = voxel
        rm.use_remove_disconnected = True
        rm.use_smooth_shade = True
        bpy.ops.object.modifier_apply(modifier=rm.name)

        # 5) 다시 한번 Non-manifold 수정 (Remesh 후 발생 가능)
        log("[5/10] Second manifold check...")
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.fill_holes(sides=0)
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode='OBJECT')

        # 6) Separate loose parts - 분리된 파트 검출
        log("[6/10] Separating loose parts...")
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.separate(type='LOOSE')
        except Exception as _:
            pass
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.context.view_layer.update()

        # 7) 작은 파트 및 내부 파트 제거 (비율 기반 + 절대값 기반)
        log("[7/10] Removing small and internal parts...")
        depsgraph = bpy.context.evaluated_depsgraph_get()
        to_delete = []
        parts = [o for o in bpy.context.scene.objects if o.type == 'MESH']

        # 가장 큰 파트 찾기
        max_vol = 0.0
        for o in parts:
            try:
                vol = float(o.dimensions.x * o.dimensions.y * o.dimensions.z)
                if vol > max_vol:
                    max_vol = vol
            except:
                continue

        for o in parts:
            try:
                eval_obj = o.evaluated_get(depsgraph)
                me = eval_obj.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
                vcount = len(me.vertices)
                vol = float(o.dimensions.x * o.dimensions.y * o.dimensions.z)
                eval_obj.to_mesh_clear()
            except ReferenceError:
                continue

            # 제거 조건:
            # 1. 버텍스 수가 너무 적음
            # 2. 볼륨이 너무 작음
            # 3. 가장 큰 파트 대비 비율이 작음 (내부 파트 제거)
            vol_ratio = vol / max_vol if max_vol > 0 else 0
            should_remove = (
                vcount < min_verts or
                vol < min_bbox_vol or
                vol_ratio < max_part_ratio
            )

            if should_remove:
                to_delete.append(o)
                log(f"  - Remove: verts={vcount}, vol={vol:.6f}, ratio={vol_ratio:.3f}")

        if to_delete:
            bpy.ops.object.select_all(action='DESELECT')
            for o in to_delete:
                if o.name in bpy.context.scene.objects:
                    o.select_set(True)
            bpy.ops.object.delete()
        log(f"Removed {len(to_delete)} parts (small/internal)")
        bpy.context.view_layer.update()

        # 8) Join remaining parts
        log("[8/10] Joining parts...")
        parts=[o for o in bpy.context.scene.objects if o.type=='MESH']
        if not parts:
            raise RuntimeError("No mesh after cleaning")
        bpy.ops.object.select_all(action='DESELECT')
        for o in parts: o.select_set(True)
        bpy.context.view_layer.objects.active = parts[0]
        if len(parts)>1:
            bpy.ops.object.join()
        obj = bpy.context.view_layer.objects.active

        # 9) Solidify - 벽 두께 강제 (얇은 벽 보강)
        log(f"[9/10] Solidifying walls (thickness={solidify_thickness})...")
        try:
            solidify = obj.modifiers.new("Solidify", "SOLIDIFY")
            solidify.thickness = solidify_thickness
            solidify.offset = 0  # 중앙
            solidify.use_even_offset = True
            solidify.use_quality_normals = True
            bpy.ops.object.modifier_apply(modifier=solidify.name)
        except Exception as e:
            log(f"  Warning: Solidify failed: {e}")

        # 10) 바닥 평탄화 및 최적 방향 (선택적)
        log("[10/10] Optimizing orientation for 3D printing...")
        if auto_orient:
            # Z축 바닥으로 이동
            bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
            minz = min([v.co.z for v in obj.data.vertices])
            if minz != 0:
                obj.location.z -= minz
                bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

            # 바닥 면적 최대화 (안정성)
            # X, Y, Z 축으로 회전해보고 바닥 면적이 가장 큰 방향 선택
            best_rotation = (0, 0, 0)
            max_base_area = 0

            for rot_x in [0, 90, -90]:
                for rot_y in [0, 90, -90]:
                    obj.rotation_euler = (math.radians(rot_x), math.radians(rot_y), 0)
                    bpy.context.view_layer.update()
                    bb = obj.dimensions
                    base_area = bb.x * bb.y
                    if base_area > max_base_area:
                        max_base_area = base_area
                        best_rotation = (rot_x, rot_y, 0)

            obj.rotation_euler = (math.radians(best_rotation[0]), math.radians(best_rotation[1]), 0)
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

            # 다시 바닥으로
            minz = min([v.co.z for v in obj.data.vertices])
            if minz != 0:
                obj.location.z -= minz
                bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

            log(f"  Optimized orientation: base area={max_base_area:.2f}")

        # 마지막 스무딩
        bpy.ops.object.shade_smooth()

        # 최종 통계
        final_verts = len(obj.data.vertices)
        final_faces = len(obj.data.polygons)
        log(f"Final mesh: {final_verts} vertices, {final_faces} faces")

        # ========== 3D PRINTING OPTIMIZATION END ==========

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
