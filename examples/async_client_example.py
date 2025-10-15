"""
Async Client Example - Image to 3D with Progress Tracking
"""
import requests
import time
import sys


BASE_URL = "http://localhost:7000"


def upload_image_async(image_path: str, should_remesh: bool = True):
    """
    Upload image and start 3D generation in async mode.
    Returns task_id immediately.
    """
    with open(image_path, 'rb') as f:
        files = {'image_file': f}
        data = {
            'task': 'image_to_3d',
            'json': f'{{"should_remesh": {str(should_remesh).lower()}}}'
        }

        # Use async_mode=true to get task_id immediately
        response = requests.post(
            f'{BASE_URL}/v1/process/modelling?async_mode=true',
            files=files,
            data=data
        )

        if response.status_code != 200:
            raise Exception(f"Failed to start task: {response.text}")

        result = response.json()
        if result['status'] != 'ok':
            raise Exception(f"API error: {result.get('error')}")

        return result['data']


def check_progress(task_id: str):
    """
    Check the progress of a task.
    Returns status, progress, and result URLs if completed.
    """
    response = requests.get(f'{BASE_URL}/v1/process/modelling/{task_id}')

    if response.status_code != 200:
        raise Exception(f"Failed to check progress: {response.text}")

    result = response.json()
    return result['data']


def wait_for_completion(task_id: str, poll_interval: int = 5, timeout: int = 1200):
    """
    Poll task status until completion or timeout.

    Args:
        task_id: Task ID to monitor
        poll_interval: Seconds between polls (default: 5)
        timeout: Maximum seconds to wait (default: 1200 = 20 minutes)

    Returns:
        Final result data when completed
    """
    start_time = time.time()
    last_progress = -1

    print(f"⏳ Waiting for task {task_id} to complete...")
    print("=" * 60)

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"Task did not complete within {timeout} seconds")

        try:
            data = check_progress(task_id)
            status = data.get('status', 'UNKNOWN')
            progress = data.get('progress', 0)

            # Print progress if changed
            if progress != last_progress:
                bar_length = 40
                filled = int(bar_length * progress / 100)
                bar = '█' * filled + '░' * (bar_length - filled)
                print(f"\r[{bar}] {progress}% - {status}", end='', flush=True)
                last_progress = progress

            # Check completion
            if status == 'SUCCEEDED':
                print("\n" + "=" * 60)
                print("✅ Task completed successfully!")
                return data

            elif status == 'FAILED':
                print("\n" + "=" * 60)
                print("❌ Task failed!")
                error = data.get('raw', {}).get('task_error', 'Unknown error')
                raise Exception(f"Task failed: {error}")

            # Still processing
            time.sleep(poll_interval)

        except KeyboardInterrupt:
            print("\n⚠️  Cancelled by user")
            print(f"Task {task_id} is still running in the background.")
            print(f"You can check its status later with: GET /v1/process/modelling/{task_id}")
            sys.exit(0)


def download_file(url: str, output_path: str):
    """Download file from URL to local path."""
    response = requests.get(url, stream=True)
    response.raise_for_status()

    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"   Downloaded: {output_path}")


def main():
    """Main example workflow."""
    print("=" * 60)
    print("🚀 Async Image-to-3D Example")
    print("=" * 60)

    # 1. Start async task
    print("\n📤 Step 1: Uploading image and starting task...")
    image_path = "test_image.png"  # Replace with your image path

    try:
        task_data = upload_image_async(image_path, should_remesh=True)
        task_id = task_data['task_id']
        print(f"✅ Task started!")
        print(f"   Task ID: {task_id}")
        print(f"   Message: {task_data.get('message')}")

    except FileNotFoundError:
        print(f"❌ Image file not found: {image_path}")
        print("   Please provide a valid image path")
        return
    except Exception as e:
        print(f"❌ Failed to start task: {e}")
        return

    # 2. Poll for progress
    print(f"\n📊 Step 2: Monitoring progress...")
    try:
        result = wait_for_completion(task_id, poll_interval=5)

    except TimeoutError as e:
        print(f"⏱️  Timeout: {e}")
        print(f"Task {task_id} may still be running. Check manually.")
        return
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    # 3. Display results
    print(f"\n📦 Step 3: Results")
    print("=" * 60)

    # GLB download
    glb_url = result.get('download_url') or result.get('glb_download_url')
    if glb_url:
        full_url = f"{BASE_URL}{glb_url}" if glb_url.startswith('/') else glb_url
        print(f"📥 GLB Model: {full_url}")
        # download_file(full_url, "output_model.glb")

    # Cleaned GLB download
    cleaned_glb_url = result.get('glb_download_url')
    if cleaned_glb_url and cleaned_glb_url != glb_url:
        full_url = f"{BASE_URL}{cleaned_glb_url}"
        print(f"📥 Cleaned GLB: {full_url}")
        # download_file(full_url, "output_cleaned.glb")

    # STL download
    stl_url = result.get('stl_download_url')
    if stl_url:
        full_url = f"{BASE_URL}{stl_url}"
        print(f"📥 STL Model: {full_url}")
        # download_file(full_url, "output_model.stl")

    # File sizes
    glb_size = result.get('glb_file_size')
    stl_size = result.get('stl_file_size')
    if glb_size:
        print(f"   GLB Size: {glb_size / 1024 / 1024:.2f} MB")
    if stl_size:
        print(f"   STL Size: {stl_size / 1024 / 1024:.2f} MB")

    print("\n" + "=" * 60)
    print("✅ All done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
