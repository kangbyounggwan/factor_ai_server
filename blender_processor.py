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
    """Generate Blender Python script for basic mesh cleaning (minimal processing)."""
    return textwrap.dedent(f"""
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

        # Get model dimensions
        bb = obj.dimensions
        log(f"Model dimensions: {{bb.x:.2f}} x {{bb.y:.2f}} x {{bb.z:.2f}}")

        # ========== BASIC CLEANING (MINIMAL PROCESSING) ==========

        # 1) Weld - 중복 버텍스 병합 (기본 정리)
        log("[1/4] Welding duplicate vertices...")
        weld = obj.modifiers.new("Weld","WELD")
        weld.merge_threshold = {weld_threshold}
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
                log(f"  - Remove tiny part: verts={{vcount}}, vol={{vol:.6f}}")

        if to_delete:
            bpy.ops.object.select_all(action='DESELECT')
            for o in to_delete:
                if o.name in bpy.context.scene.objects:
                    o.select_set(True)
            bpy.ops.object.delete()
        log(f"Removed {{len(to_delete)}} tiny parts")
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
        log(f"Final mesh: {{final_verts}} vertices, {{final_faces}} faces")

        # ========== BASIC CLEANING END ==========

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

        # 원본 GLB 크기 확인
        original_bounds = mesh.bounds
        original_size_x = original_bounds[1, 0] - original_bounds[0, 0]
        original_size_y = original_bounds[1, 1] - original_bounds[0, 1]
        original_size_z = original_bounds[1, 2] - original_bounds[0, 2]

        logger.info("="*80)
        logger.info("[Trimesh] 📦 ORIGINAL GLB SIZE (before optimization):")
        logger.info("[Trimesh]   X: %.2f mm", original_size_x)
        logger.info("[Trimesh]   Y: %.2f mm", original_size_y)
        logger.info("[Trimesh]   Z: %.2f mm", original_size_z)
        logger.info("[Trimesh]   Original: %d vertices, %d faces", len(mesh.vertices), len(mesh.faces))
        logger.info("="*80)

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

        # 모델 크기 확인 (변환 후 최종 크기)
        bounds = mesh.bounds  # [[min_x, min_y, min_z], [max_x, max_y, max_z]]
        model_size_x = bounds[1, 0] - bounds[0, 0]
        model_size_y = bounds[1, 1] - bounds[0, 1]
        model_size_z = bounds[1, 2] - bounds[0, 2]
        logger.info("="*80)
        logger.info("[Trimesh] 📏 MODEL SIZE (after conversion to STL):")
        logger.info("[Trimesh]   X: %.2f mm", model_size_x)
        logger.info("[Trimesh]   Y: %.2f mm", model_size_y)
        logger.info("[Trimesh]   Z: %.2f mm", model_size_z)
        logger.info("[Trimesh]   Bounding box: (%.2f, %.2f, %.2f) mm", model_size_x, model_size_y, model_size_z)
        logger.info("="*80)

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
