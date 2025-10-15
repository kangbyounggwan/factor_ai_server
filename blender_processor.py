import os
import logging
import asyncio
import textwrap
from pathlib import Path
from typing import Tuple
import subprocess

logger = logging.getLogger("uvicorn.error")

# Environment variables
BLENDER_PATH = os.getenv("BLENDER_PATH", "").strip()
BLENDER_MIN_VERTS = int(os.getenv("BLENDER_MIN_VERTS", "300"))
BLENDER_MIN_BBOX_VOL = float(os.getenv("BLENDER_MIN_BBOX_VOL", "0.0000001"))
BLENDER_VOXEL_DIVISOR = float(os.getenv("BLENDER_VOXEL_DIVISOR", "200.0"))
BLENDER_WELD_THRESHOLD = float(os.getenv("BLENDER_WELD_THRESHOLD", "0.0008"))

# 3D Printing optimization settings
BLENDER_MIN_WALL_THICKNESS = float(os.getenv("BLENDER_MIN_WALL_THICKNESS", "0.4"))
BLENDER_DECIMATE_RATIO = float(os.getenv("BLENDER_DECIMATE_RATIO", "0.15"))
BLENDER_MAX_PART_RATIO = float(os.getenv("BLENDER_MAX_PART_RATIO", "0.05"))
BLENDER_SOLIDIFY_THICKNESS = float(os.getenv("BLENDER_SOLIDIFY_THICKNESS", "0.4"))
BLENDER_ENABLE_AUTO_ORIENT = os.getenv("BLENDER_ENABLE_AUTO_ORIENT", "True").lower() == "true"

OUTPUT_DIR_RAW = os.getenv("OUTPUT_DIR", "./output").strip()
OUTPUT_DIR = Path(OUTPUT_DIR_RAW)

logger.info(
    "[BlenderCfg] path=%s min_verts=%d min_vol=%.2e voxel_div=%.1f weld=%.4f wall_thick=%.2f decimate=%.2f",
    BLENDER_PATH or "(not configured)",
    BLENDER_MIN_VERTS,
    BLENDER_MIN_BBOX_VOL,
    BLENDER_VOXEL_DIVISOR,
    BLENDER_WELD_THRESHOLD,
    BLENDER_MIN_WALL_THICKNESS,
    BLENDER_DECIMATE_RATIO,
)


def is_blender_available() -> bool:
    """Check if Blender is available and configured."""
    if not BLENDER_PATH:
        return False
    return Path(BLENDER_PATH).exists()


def generate_blender_script(
    weld_threshold: float,
    voxel_divisor: float,
    min_wall_thickness: float,
    decimate_ratio: float,
    max_part_ratio: float,
    solidify_thickness: float,
    auto_orient: bool,
) -> str:
    """Generate Blender Python script for 3D printing optimized mesh cleaning."""
    return textwrap.dedent(f"""
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
        raise RuntimeError(f'Unsupported format: {{ext}}')

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
        log(f"Model dimensions: {{bb.x:.2f}} x {{bb.y:.2f}} x {{bb.z:.2f}} (base={{base_size:.2f}})")

        # ========== 3D PRINTING OPTIMIZATION START ==========

        # 1) Weld - 중복 버텍스 병합
        log("[1/10] Welding duplicate vertices...")
        weld = obj.modifiers.new("Weld","WELD")
        weld.merge_threshold = {weld_threshold}
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
        log(f"[3/10] Decimating mesh (ratio={{decimate_ratio}})...")
        decimate = obj.modifiers.new("Decimate", "DECIMATE")
        decimate.ratio = decimate_ratio
        decimate.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=decimate.name)

        # 4) Voxel Remesh - 균일한 메시 재구성
        log("[4/10] Voxel remeshing...")
        voxel = max(base_size/{voxel_divisor}, 0.0005)
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
                log(f"  - Remove: verts={{vcount}}, vol={{vol:.6f}}, ratio={{vol_ratio:.3f}}")

        if to_delete:
            bpy.ops.object.select_all(action='DESELECT')
            for o in to_delete:
                if o.name in bpy.context.scene.objects:
                    o.select_set(True)
            bpy.ops.object.delete()
        log(f"Removed {{len(to_delete)}} parts (small/internal)")
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
        log(f"[9/10] Solidifying walls (thickness={{solidify_thickness}})...")
        try:
            solidify = obj.modifiers.new("Solidify", "SOLIDIFY")
            solidify.thickness = solidify_thickness
            solidify.offset = 0  # 중앙
            solidify.use_even_offset = True
            solidify.use_quality_normals = True
            bpy.ops.object.modifier_apply(modifier=solidify.name)
        except Exception as e:
            log(f"  Warning: Solidify failed: {{e}}")

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

            log(f"  Optimized orientation: base area={{max_base_area:.2f}}")

        # 마지막 스무딩
        bpy.ops.object.shade_smooth()

        # 최종 통계
        final_verts = len(obj.data.vertices)
        final_faces = len(obj.data.polygons)
        log(f"Final mesh: {{final_verts}} vertices, {{final_faces}} faces")

        # ========== 3D PRINTING OPTIMIZATION END ==========

        # Export as GLB
        bpy.ops.export_scene.gltf(filepath=out_glb, export_format='GLB', use_selection=False)
        if not os.path.exists(out_glb) or os.path.getsize(out_glb)==0:
            raise RuntimeError("GLB export failed")
        log(f"EXPORTED: {{out_glb}}")

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
""")


async def run_blender_process(
    input_glb: Path,
    output_glb: Path,
    min_verts: int,
    min_bbox_vol: float,
) -> Tuple[bool, str]:
    """
    Run Blender to clean and process the GLB file.

    Returns:
        Tuple[success: bool, log_output: str]
    """
    logger.info("[Blender] ===== Starting Blender Process =====")
    logger.info("[Blender] Input GLB: %s (exists: %s)", input_glb, input_glb.exists())
    logger.info("[Blender] Output GLB: %s", output_glb)
    logger.info("[Blender] Min verts: %d, Min bbox vol: %.2e", min_verts, min_bbox_vol)

    if not is_blender_available():
        logger.error("[Blender] Blender not configured or not found")
        return False, "Blender not configured or not found"

    logger.info("[Blender] Blender path: %s", BLENDER_PATH)
    logger.info("[Blender] Blender exists: %s", Path(BLENDER_PATH).exists())

    # Use fixed Blender script from project root
    script_path = Path(__file__).parent / "clean_and_export.py"
    if not script_path.exists():
        logger.error("[Blender] Script not found: %s", script_path)
        return False, f"Blender script not found: {script_path}"
    logger.info("[Blender] Using Blender script: %s", script_path)

    # Prepare log file
    log_path = OUTPUT_DIR / f"blender_log_{output_glb.stem}.txt"
    logger.info("[Blender] Log will be saved to: %s", log_path)

    # Build command with all parameters - use absolute paths
    cmd = [
        str(BLENDER_PATH), "-b", "--factory-startup", "--log-level", "0",
        "--python", str(script_path.absolute()),
        "--",
        str(input_glb.absolute()),
        str(output_glb.absolute()),
        str(min_verts),
        str(min_bbox_vol),
        str(BLENDER_MAX_PART_RATIO),
        str(BLENDER_DECIMATE_RATIO),
        str(BLENDER_SOLIDIFY_THICKNESS),
        str(BLENDER_ENABLE_AUTO_ORIENT).lower(),
    ]

    logger.info("[Blender] Command: %s", " ".join(cmd))
    logger.info("[Blender] Command length: %d characters", len(" ".join(cmd)))

    # Run Blender process
    try:
        logger.info("[Blender] Creating subprocess...")

        # Use sync subprocess for Windows compatibility
        import subprocess

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()

        def run_subprocess():
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            stdout, _ = process.communicate()
            return process.returncode, stdout

        returncode, stdout = await loop.run_in_executor(None, run_subprocess)

        logger.info("[Blender] Process completed with return code: %d", returncode)
        logger.info("[Blender] Stdout size: %d bytes", len(stdout))

        log_output = stdout.decode("utf-8", errors="ignore")
        logger.info("[Blender] Decoded output size: %d characters", len(log_output))

        # Save log
        try:
            log_path.write_text(log_output, encoding="utf-8", errors="ignore")
            logger.info("[Blender] Log saved successfully: %s", log_path)
        except Exception as e:
            logger.error("[Blender] Failed to save log: %s", str(e))

        if returncode != 0:
            logger.error("[Blender] Process failed with return code: %d", returncode)
            logger.error("[Blender] Full output log:\n%s", log_output)
            return False, log_output

        # Check if output file exists
        logger.info("[Blender] Checking output file: %s", output_glb)
        logger.info("[Blender] Output exists: %s", output_glb.exists())
        if output_glb.exists():
            logger.info("[Blender] Output size: %d bytes", output_glb.stat().st_size)

        if not output_glb.exists() or output_glb.stat().st_size == 0:
            logger.error("[Blender] Output file missing or empty")
            logger.error("[Blender] Full output log:\n%s", log_output)
            return False, log_output

        logger.info("[Blender] ===== Blender Process Successful =====")
        logger.info("[Blender] Output: %s", output_glb)
        return True, log_output

    except asyncio.CancelledError:
        logger.error("[Blender] Process was cancelled")
        raise
    except Exception as e:
        logger.error("[Blender] Exception during subprocess execution")
        logger.error("[Blender] Exception type: %s", type(e).__name__)
        logger.error("[Blender] Exception message: %s", str(e))
        import traceback
        error_msg = f"Blender execution error: {str(e)}\n{traceback.format_exc()}"
        logger.error("[Blender] Full traceback:\n%s", traceback.format_exc())
        return False, error_msg


async def convert_glb_to_stl(glb_path: Path, stl_path: Path) -> bool:
    """
    Convert GLB to STL using Trimesh with advanced 3D printing optimization.

    Returns:
        bool: Success status
    """
    try:
        import trimesh
        import numpy as np

        logger.info("[Trimesh] Converting GLB to STL with 3D printing optimization...")

        # Load GLB
        scene = trimesh.load(str(glb_path), file_type='glb')

        # Concatenate all geometries
        if hasattr(scene, "geometry"):
            mesh = trimesh.util.concatenate(tuple(scene.geometry.values()))
        else:
            mesh = scene

        logger.info("[Trimesh] Original: %d vertices, %d faces", len(mesh.vertices), len(mesh.faces))

        # ===== 3D PRINTING OPTIMIZATION =====

        # 1. 기본 수리
        logger.info("[Trimesh] Step 1/7: Basic repairs...")
        trimesh.repair.fix_inversion(mesh)
        trimesh.repair.fill_holes(mesh)
        mesh.remove_degenerate_faces()
        mesh.remove_duplicate_faces()
        mesh.remove_unreferenced_vertices()

        # 2. 법선 수정 (외부 방향)
        logger.info("[Trimesh] Step 2/7: Fixing normals...")
        trimesh.repair.fix_normals(mesh)

        # 3. 물리적 유효성 검증
        logger.info("[Trimesh] Step 3/7: Validating mesh...")
        mesh.process(validate=True)

        # 4. Watertight 체크 (3D 프린팅 필수)
        is_watertight = mesh.is_watertight
        logger.info("[Trimesh] Watertight: %s", is_watertight)
        if not is_watertight:
            logger.warning("[Trimesh] Mesh is not watertight - attempting to fix...")
            try:
                trimesh.repair.fill_holes(mesh)
                mesh.process(validate=True)
                is_watertight = mesh.is_watertight
                logger.info("[Trimesh] After fix, watertight: %s", is_watertight)
            except Exception as e:
                logger.warning("[Trimesh] Could not make watertight: %s", e)

        # 5. 바닥으로 이동 (Z=0)
        logger.info("[Trimesh] Step 4/7: Moving to ground...")
        minz = mesh.bounds[0, 2]
        if minz != 0:
            mesh.apply_translation((0, 0, -minz))

        # 6. 중심 정렬 (XY 평면)
        logger.info("[Trimesh] Step 5/7: Centering on build plate...")
        center_xy = mesh.bounds.mean(axis=0)
        center_xy[2] = 0  # Z축은 유지
        mesh.apply_translation(-center_xy)

        # 7. 프린팅 가능성 확인
        logger.info("[Trimesh] Step 6/7: Checking printability...")
        volume = mesh.volume
        surface_area = mesh.area
        logger.info("[Trimesh] Volume: %.2f mm³, Surface area: %.2f mm²", volume, surface_area)

        if volume <= 0:
            logger.warning("[Trimesh] Volume is zero or negative - mesh may have inverted normals")

        # 8. STL 내보내기 (Binary 형식 - 파일 크기 최소화)
        logger.info("[Trimesh] Step 7/7: Exporting STL...")
        mesh.export(str(stl_path), file_type='stl')

        if not stl_path.exists() or stl_path.stat().st_size == 0:
            logger.warning("[Trimesh] STL file missing or empty")
            return False

        file_size_mb = stl_path.stat().st_size / 1024 / 1024
        logger.info("[Trimesh] ✅ STL saved: %s (%.2f MB)", stl_path, file_size_mb)
        logger.info("[Trimesh] Final: %d vertices, %d faces", len(mesh.vertices), len(mesh.faces))
        logger.info("[Trimesh] Watertight: %s, Volume: %.2f mm³", is_watertight, volume)

        return True

    except ImportError:
        logger.error("[Trimesh] trimesh library not installed")
        return False
    except Exception as e:
        logger.error("[Trimesh] Conversion failed: %s", str(e))
        import traceback
        traceback.print_exc()
        return False


async def process_model_with_blender(
    input_glb_path: str,
    task_id: str,
) -> dict:
    """
    Complete Blender post-processing pipeline: clean GLB + convert to STL.

    Args:
        input_glb_path: Path to the input GLB file
        task_id: Task ID for naming output files

    Returns:
        dict with 'cleaned_glb_path', 'stl_path', 'blender_log'
    """
    if not is_blender_available():
        raise RuntimeError("Blender is not configured or not available")

    input_path = Path(input_glb_path)
    if not input_path.exists():
        raise RuntimeError(f"Input GLB file not found: {input_glb_path}")

    # Output paths
    cleaned_glb = OUTPUT_DIR / f"cleaned_{task_id}.glb"
    stl_output = OUTPUT_DIR / f"cleaned_{task_id}.stl"

    # Step 1: Clean with Blender
    logger.info("[BlenderProcess] Starting for task_id=%s", task_id)
    success, blender_log = await run_blender_process(
        input_path,
        cleaned_glb,
        BLENDER_MIN_VERTS,
        BLENDER_MIN_BBOX_VOL,
    )

    if not success:
        # Extract the most relevant error info
        error_lines = [line for line in blender_log.split('\n') if 'ERROR' in line or 'Error' in line or '❌' in line]
        error_summary = '\n'.join(error_lines[-10:]) if error_lines else blender_log[-500:]
        raise RuntimeError(f"Blender processing failed:\n{error_summary}")

    # Step 2: Convert to STL
    logger.info("[BlenderProcess] Converting to STL for task_id=%s", task_id)
    stl_success = await convert_glb_to_stl(cleaned_glb, stl_output)

    if not stl_success:
        raise RuntimeError("STL conversion failed")

    result = {
        "cleaned_glb_path": str(cleaned_glb),
        "stl_path": str(stl_output),
        "blender_log": blender_log,
    }

    logger.info("[BlenderProcess] Completed for task_id=%s", task_id)
    return result
