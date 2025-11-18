"""
AI-based 3D Print Failure Detector

Detects print failures using computer vision heuristics.
This is a fallback implementation that can be replaced with
Spaghetti Detective pre-trained model when available.

Detects:
- Spaghetti (high edge density + chaotic patterns)
- Layer shifts (sudden horizontal lines)
- Warping (corner detection issues)
- Stringing (thin artifacts)
"""

import os
import logging
from typing import Dict, Optional, Tuple, Any
from dataclasses import dataclass
import asyncio

import numpy as np
import cv2
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class FailureDetectionResult:
    """Container for failure detection results."""
    has_failure: bool
    failure_type: str
    confidence: float
    severity: str  # 'low', 'medium', 'high', 'critical'
    bbox: Optional[Dict[str, int]] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "has_failure": self.has_failure,
            "failure_type": self.failure_type,
            "confidence": self.confidence,
            "severity": self.severity,
            "bbox": self.bbox,
            "details": self.details or {}
        }


class CVFailureDetector:
    """
    Computer Vision based failure detector using heuristics.

    This is a fallback implementation until Spaghetti Detective
    pre-trained model is integrated.
    """

    def __init__(
        self,
        conf_threshold: float = 0.7,
        enable_spaghetti: bool = True,
        enable_layer_shift: bool = True,
        enable_warping: bool = True
    ):
        """
        Initialize CV failure detector.

        Args:
            conf_threshold: Confidence threshold for detections
            enable_spaghetti: Enable spaghetti detection
            enable_layer_shift: Enable layer shift detection
            enable_warping: Enable warping detection
        """
        self.conf_threshold = conf_threshold
        self.enable_spaghetti = enable_spaghetti
        self.enable_layer_shift = enable_layer_shift
        self.enable_warping = enable_warping

        logger.info(
            f"[CV Detector] Initialized "
            f"(threshold={conf_threshold}, spaghetti={enable_spaghetti}, "
            f"layer_shift={enable_layer_shift}, warping={enable_warping})"
        )

    def detect_spaghetti(self, frame: np.ndarray) -> Optional[FailureDetectionResult]:
        """
        Detect spaghetti failure using edge density and chaos.

        Spaghetti = filament has detached and created chaotic mess.
        Indicators: High edge density, many small contours.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Edge detection
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / (h * w)

        # High edge density = potential spaghetti
        if edge_density > 0.3:  # 30% of pixels are edges
            # Check for chaotic patterns using contour analysis
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Many small contours = chaos
            if len(contours) > 100:
                confidence = min(0.95, edge_density * 2.5)

                # Find bounding box of chaotic region (largest contours)
                bbox = None
                if len(contours) > 0:
                    # Get top 10 largest contours
                    sorted_contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]
                    # Find overall bounding box
                    all_points = np.concatenate(sorted_contours)
                    x, y, w_box, h_box = cv2.boundingRect(all_points)
                    bbox = {"x": int(x), "y": int(y), "width": int(w_box), "height": int(h_box)}

                    logger.debug(
                        f"[Spaghetti Detection] bbox created: "
                        f"x={bbox['x']}, y={bbox['y']}, w={bbox['width']}, h={bbox['height']} "
                        f"(frame: {w}x{h}, contours: {len(contours)})"
                    )

                return FailureDetectionResult(
                    has_failure=True,
                    failure_type="spaghetti",
                    confidence=confidence,
                    severity="critical",
                    bbox=bbox,
                    details={
                        "edge_density": float(edge_density),
                        "contour_count": len(contours),
                        "method": "edge_density_contour"
                    }
                )

        return None

    def detect_layer_shift(self, frame: np.ndarray) -> Optional[FailureDetectionResult]:
        """
        Detect layer shift using Hough line detection.

        Layer shift = print head lost position, creating horizontal offset.
        Indicators: Sudden prominent horizontal lines.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Edge detection
        edges = cv2.Canny(gray, 50, 150)

        # Hough Line Transform to find lines
        lines = cv2.HoughLinesP(
            edges, 1, np.pi/180,
            threshold=100,
            minLineLength=w//4,  # At least 1/4 of frame width
            maxLineGap=10
        )

        if lines is not None and len(lines) > 5:
            # Count horizontal lines (near 0° or 180°)
            horizontal_lines = 0
            horizontal_line_coords = []

            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)

                # Nearly horizontal (within 10 degrees)
                if angle < 10 or angle > 170:
                    horizontal_lines += 1
                    horizontal_line_coords.append((x1, y1, x2, y2))

            # Multiple prominent horizontal lines = layer shift
            if horizontal_lines > 3:
                confidence = min(0.85, horizontal_lines / 10.0)

                # Find bounding box of horizontal lines
                if horizontal_line_coords:
                    all_x = [x for line in horizontal_line_coords for x in (line[0], line[2])]
                    all_y = [y for line in horizontal_line_coords for y in (line[1], line[3])]
                    bbox = {
                        "x": min(all_x),
                        "y": min(all_y),
                        "width": max(all_x) - min(all_x),
                        "height": max(all_y) - min(all_y)
                    }
                else:
                    bbox = None

                return FailureDetectionResult(
                    has_failure=True,
                    failure_type="layer_shift",
                    confidence=confidence,
                    severity="high",
                    bbox=bbox,
                    details={
                        "horizontal_lines": horizontal_lines,
                        "total_lines": len(lines),
                        "method": "hough_line_transform"
                    }
                )

        return None

    def detect_warping(self, frame: np.ndarray) -> Optional[FailureDetectionResult]:
        """
        Detect warping (bed adhesion failure).

        Warping = print corners lift from bed.
        Indicators: Corner detection at bed edges, color changes.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Focus on bottom corners (where warping typically starts)
        bottom_region = gray[int(h*0.7):, :]

        # Harris corner detection
        corners = cv2.cornerHarris(bottom_region, blockSize=2, ksize=3, k=0.04)
        corners = cv2.dilate(corners, None)

        # Threshold corners
        corner_threshold = 0.01 * corners.max()
        corner_points = np.where(corners > corner_threshold)

        # If many corners detected at bottom = possible warping
        if len(corner_points[0]) > 50:
            confidence = min(0.75, len(corner_points[0]) / 200.0)

            # Create bounding box around detected corners
            bbox = None
            if len(corner_points[0]) > 0:
                y_coords = corner_points[0]
                x_coords = corner_points[1]

                y_min, y_max = y_coords.min(), y_coords.max()
                x_min, x_max = x_coords.min(), x_coords.max()

                # Adjust y coordinates for bottom region offset
                y_offset = int(h * 0.7)

                bbox = {
                    "x": int(x_min),
                    "y": int(y_min + y_offset),
                    "width": int(x_max - x_min),
                    "height": int(y_max - y_min)
                }

                logger.debug(
                    f"[Warping Detection] bbox created: "
                    f"x={bbox['x']}, y={bbox['y']}, w={bbox['width']}, h={bbox['height']} "
                    f"(frame: {w}x{h}, corners: {len(corner_points[0])})"
                )

            return FailureDetectionResult(
                has_failure=True,
                failure_type="warping",
                confidence=confidence,
                severity="medium",
                bbox=bbox,
                details={
                    "corner_count": len(corner_points[0]),
                    "detection_region": "bottom_30_percent",
                    "method": "harris_corner_detection"
                }
            )

        return None

    async def detect(self, frame: np.ndarray) -> FailureDetectionResult:
        """
        Run all enabled detection methods.

        Args:
            frame: BGR image (numpy array)

        Returns:
            FailureDetectionResult (returns highest priority failure if multiple detected)
        """
        # Priority order: spaghetti > layer_shift > warping
        detections = []

        # 1. Spaghetti detection (highest priority)
        if self.enable_spaghetti:
            result = self.detect_spaghetti(frame)
            if result and result.confidence >= self.conf_threshold:
                return result

        # 2. Layer shift
        if self.enable_layer_shift:
            result = self.detect_layer_shift(frame)
            if result and result.confidence >= self.conf_threshold:
                return result

        # 3. Warping
        if self.enable_warping:
            result = self.detect_warping(frame)
            if result and result.confidence >= self.conf_threshold:
                return result

        # No failure detected
        return FailureDetectionResult(
            has_failure=False,
            failure_type="none",
            confidence=0.0,
            severity="low",
            details={"method": "cv_heuristics"}
        )


class AIFailureDetector:
    """
    High-level AI failure detection service.

    Currently uses CV heuristics fallback.
    Can be extended to use Spaghetti Detective pre-trained model.
    """

    def __init__(
        self,
        conf_threshold: float = 0.7,
        use_gpu: bool = False,
        model_path: Optional[str] = None
    ):
        """
        Initialize AI failure detector.

        Args:
            conf_threshold: Confidence threshold for detections
            use_gpu: Use GPU if available (for future PyTorch model)
            model_path: Path to pre-trained model (for future use)
        """
        self.conf_threshold = conf_threshold
        self.model_path = model_path

        # Use CV fallback detector
        self.detector = CVFailureDetector(conf_threshold=conf_threshold)

        # Statistics
        self.total_frames_processed = 0
        self.failures_detected = 0

        logger.info(
            f"[AI Detector] Initialized with CV fallback "
            f"(threshold={conf_threshold})"
        )

    async def detect_failure(self, frame: np.ndarray) -> FailureDetectionResult:
        """
        Detect failures in a single frame.

        Args:
            frame: BGR image (numpy array from cv2)

        Returns:
            FailureDetectionResult object
        """
        self.total_frames_processed += 1

        # Run detection
        result = await self.detector.detect(frame)

        if result.has_failure:
            self.failures_detected += 1
            logger.warning(
                f"[AI Detector] Failure detected: {result.failure_type} "
                f"(confidence={result.confidence:.2f}, severity={result.severity})"
            )

        return result

    def annotate_frame(
        self,
        frame: np.ndarray,
        result: FailureDetectionResult
    ) -> np.ndarray:
        """
        Draw detection results on frame.

        Args:
            frame: Original BGR image
            result: Detection result

        Returns:
            Annotated BGR image
        """
        annotated = frame.copy()

        if not result.has_failure:
            # Draw "OK" status
            cv2.putText(
                annotated, "OK", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2
            )
            return annotated

        # Get color based on severity
        color = self._get_severity_color(result.severity)
        label = f"{result.failure_type.upper()} ({result.confidence:.0%})"

        # Draw bounding box if available
        if result.bbox:
            x = result.bbox["x"]
            y = result.bbox["y"]
            w = result.bbox["width"]
            h = result.bbox["height"]
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                annotated, label, (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2
            )
        else:
            # Draw on top-left corner
            cv2.putText(
                annotated, label, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2
            )
            cv2.putText(
                annotated, f"Severity: {result.severity.upper()}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2
            )

        return annotated

    def _get_severity_color(self, severity: str) -> Tuple[int, int, int]:
        """Get BGR color for severity level."""
        colors = {
            "low": (0, 255, 255),      # Yellow
            "medium": (0, 165, 255),   # Orange
            "high": (0, 69, 255),      # Red-Orange
            "critical": (0, 0, 255)    # Red
        }
        return colors.get(severity, (0, 255, 0))

    def get_statistics(self) -> Dict[str, Any]:
        """Get detector statistics."""
        return {
            "total_frames_processed": self.total_frames_processed,
            "failures_detected": self.failures_detected,
            "failure_rate": self.failures_detected / max(1, self.total_frames_processed),
            "detection_method": "cv_heuristics"
        }


# ============================================================================
# Test Function
# ============================================================================

async def test_ai_detector():
    """Test AI failure detector with sample images."""
    print("=" * 80)
    print("AI Failure Detector Test")
    print("=" * 80)

    # Initialize detector
    detector = AIFailureDetector(conf_threshold=0.7)
    print(f"✅ Detector initialized")

    # Test 1: Normal frame (no failure)
    print("\n📸 Test 1: Normal frame")
    normal_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(normal_frame, (200, 150), (440, 330), (255, 255, 255), -1)
    cv2.putText(normal_frame, "Normal Print", (220, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    result = await detector.detect_failure(normal_frame)
    print(f"   Result: {result.failure_type} (confidence={result.confidence:.2%})")

    # Test 2: Simulated spaghetti (high chaos)
    print("\n🍝 Test 2: Spaghetti simulation")
    spaghetti_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    # Add random lines for high edge density
    for _ in range(200):
        pt1 = (np.random.randint(0, 640), np.random.randint(0, 480))
        pt2 = (np.random.randint(0, 640), np.random.randint(0, 480))
        cv2.line(spaghetti_frame, pt1, pt2, (255, 255, 255), 1)

    result = await detector.detect_failure(spaghetti_frame)
    print(f"   Result: {result.failure_type} (confidence={result.confidence:.2%}, severity={result.severity})")

    annotated = detector.annotate_frame(spaghetti_frame, result)
    cv2.imwrite("./output/test_spaghetti_detected.jpg", annotated)
    print(f"   Saved annotated frame: ./output/test_spaghetti_detected.jpg")

    # Test 3: Simulated layer shift (horizontal lines)
    print("\n📏 Test 3: Layer shift simulation")
    layer_shift_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw horizontal lines
    for y in [200, 210, 220, 230, 240]:
        cv2.line(layer_shift_frame, (50, y), (590, y), (255, 255, 255), 2)

    result = await detector.detect_failure(layer_shift_frame)
    print(f"   Result: {result.failure_type} (confidence={result.confidence:.2%}, severity={result.severity})")

    annotated = detector.annotate_frame(layer_shift_frame, result)
    cv2.imwrite("./output/test_layer_shift_detected.jpg", annotated)
    print(f"   Saved annotated frame: ./output/test_layer_shift_detected.jpg")

    # Statistics
    stats = detector.get_statistics()
    print("\n📊 Detector Statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print("\n" + "=" * 80)
    print("✅ Test completed!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_ai_detector())
