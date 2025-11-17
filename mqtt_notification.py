"""
MQTT Notification Helper

Sends notifications to users via MQTT when AI model generation completes or fails
"""
import paho.mqtt.client as mqtt
import json
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("uvicorn.error")

# MQTT Broker configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_CLIENT_ID = "factor-ai-server"

# Topic templates
TOPIC_AI_MODEL_COMPLETED = "ai/model/completed/{user_id}"
TOPIC_AI_MODEL_FAILED = "ai/model/failed/{user_id}"
TOPIC_AI_MODEL_PROGRESS = "ai/model/progress/{user_id}"


def create_mqtt_client() -> mqtt.Client:
    """
    Create and configure MQTT client

    Returns:
        mqtt.Client: Configured MQTT client
    """
    client = mqtt.Client(client_id=MQTT_CLIENT_ID)

    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # Set callbacks
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info(f"[MQTT] Connected to broker: {MQTT_BROKER}:{MQTT_PORT}")
        else:
            logger.error(f"[MQTT] Connection failed with code: {rc}")

    def on_disconnect(client, userdata, rc):
        if rc != 0:
            logger.warning(f"[MQTT] Unexpected disconnection: {rc}")

    def on_publish(client, userdata, mid):
        logger.debug(f"[MQTT] Message published: mid={mid}")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish

    return client


def send_model_completion_notification(
    user_id: str,
    model_id: str,
    download_url: str,
    thumbnail_url: Optional[str] = None,
    stl_download_url: Optional[str] = None,
    model_name: Optional[str] = None,
    generation_type: Optional[str] = None
) -> bool:
    """
    Send MQTT notification when model generation completes

    Args:
        user_id: User ID
        model_id: Model ID (UUID)
        download_url: Public GLB download URL
        thumbnail_url: Thumbnail URL (optional)
        stl_download_url: STL download URL (optional)
        model_name: Model name (optional)
        generation_type: 'text_to_3d' or 'image_to_3d'

    Returns:
        bool: True if sent successfully
    """
    if not user_id:
        logger.warning("[MQTT] Cannot send notification: user_id is missing")
        return False

    try:
        client = create_mqtt_client()
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()

        topic = TOPIC_AI_MODEL_COMPLETED.format(user_id=user_id)

        payload = {
            "model_id": model_id,
            "status": "completed",
            "download_url": download_url,
            "thumbnail_url": thumbnail_url,
            "stl_download_url": stl_download_url,
            "model_name": model_name or f"AI Model {model_id[:8]}",
            "generation_type": generation_type,
            "timestamp": None  # Will be set by client
        }

        message = json.dumps(payload)
        result = client.publish(topic, message, qos=1, retain=False)

        # Wait for publish to complete
        result.wait_for_publish(timeout=5)

        if result.is_published():
            logger.info(f"[MQTT] Sent completion notification: user_id={user_id[:8]}..., model_id={model_id[:8]}...")
            success = True
        else:
            logger.error(f"[MQTT] Failed to publish message: topic={topic}")
            success = False

        client.loop_stop()
        client.disconnect()

        return success

    except Exception as e:
        logger.error(f"[MQTT] Error sending completion notification: {e}")
        return False


def send_model_failure_notification(
    user_id: str,
    model_id: str,
    error_message: str,
    generation_type: Optional[str] = None
) -> bool:
    """
    Send MQTT notification when model generation fails

    Args:
        user_id: User ID
        model_id: Model ID (UUID)
        error_message: Error message
        generation_type: 'text_to_3d' or 'image_to_3d'

    Returns:
        bool: True if sent successfully
    """
    if not user_id:
        logger.warning("[MQTT] Cannot send notification: user_id is missing")
        return False

    try:
        client = create_mqtt_client()
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()

        topic = TOPIC_AI_MODEL_FAILED.format(user_id=user_id)

        payload = {
            "model_id": model_id,
            "status": "failed",
            "error_message": error_message,
            "generation_type": generation_type,
            "timestamp": None  # Will be set by client
        }

        message = json.dumps(payload)
        result = client.publish(topic, message, qos=1, retain=False)

        # Wait for publish to complete
        result.wait_for_publish(timeout=5)

        if result.is_published():
            logger.info(f"[MQTT] Sent failure notification: user_id={user_id[:8]}..., model_id={model_id[:8]}...")
            success = True
        else:
            logger.error(f"[MQTT] Failed to publish message: topic={topic}")
            success = False

        client.loop_stop()
        client.disconnect()

        return success

    except Exception as e:
        logger.error(f"[MQTT] Error sending failure notification: {e}")
        return False


def send_model_progress_notification(
    user_id: str,
    model_id: str,
    progress: int,
    message: str = "",
    generation_type: Optional[str] = None
) -> bool:
    """
    Send MQTT notification for model generation progress

    Args:
        user_id: User ID
        model_id: Model ID (UUID)
        progress: Progress percentage (0-100)
        message: Progress message
        generation_type: 'text_to_3d' or 'image_to_3d'

    Returns:
        bool: True if sent successfully
    """
    if not user_id:
        return False

    try:
        client = create_mqtt_client()
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()

        topic = TOPIC_AI_MODEL_PROGRESS.format(user_id=user_id)

        payload = {
            "model_id": model_id,
            "status": "processing",
            "progress": progress,
            "message": message,
            "generation_type": generation_type,
            "timestamp": None
        }

        message_json = json.dumps(payload)
        result = client.publish(topic, message_json, qos=0, retain=False)

        result.wait_for_publish(timeout=5)

        client.loop_stop()
        client.disconnect()

        return result.is_published()

    except Exception as e:
        logger.error(f"[MQTT] Error sending progress notification: {e}")
        return False


if __name__ == "__main__":
    # Test MQTT notifications
    import uuid

    print("Testing MQTT notifications...")

    test_user_id = str(uuid.uuid4())
    test_model_id = str(uuid.uuid4())

    # Test completion notification
    success = send_model_completion_notification(
        user_id=test_user_id,
        model_id=test_model_id,
        download_url="https://example.com/model.glb",
        thumbnail_url="https://example.com/thumb.png",
        model_name="Test Model",
        generation_type="text_to_3d"
    )
    print(f"Completion notification: {'✅' if success else '❌'}")

    # Test failure notification
    success = send_model_failure_notification(
        user_id=test_user_id,
        model_id=test_model_id,
        error_message="Test error",
        generation_type="text_to_3d"
    )
    print(f"Failure notification: {'✅' if success else '❌'}")

    # Test progress notification
    success = send_model_progress_notification(
        user_id=test_user_id,
        model_id=test_model_id,
        progress=50,
        message="Processing...",
        generation_type="text_to_3d"
    )
    print(f"Progress notification: {'✅' if success else '❌'}")
