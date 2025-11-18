-- ============================================================================
-- AI Print Monitoring - Failure Scenes Database Schema
-- ============================================================================
-- This table stores automatically collected failure scenes for:
-- 1. Real-time failure detection alerts
-- 2. Historical failure analysis
-- 3. Building training dataset for future custom models
-- ============================================================================

-- Drop existing table and related objects if they exist
DROP TRIGGER IF EXISTS trigger_update_failure_scenes_updated_at ON failure_scenes;
DROP FUNCTION IF EXISTS update_failure_scenes_updated_at();
DROP TABLE IF EXISTS failure_scenes CASCADE;

-- Create the table
CREATE TABLE failure_scenes (
    -- Primary identification
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    device_uuid UUID NOT NULL,

    -- Detection information
    failure_type VARCHAR(50) NOT NULL, -- 'spaghetti', 'layer_shift', 'warping', 'stringing', etc.
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    severity VARCHAR(20) NOT NULL DEFAULT 'medium', -- 'low', 'medium', 'high', 'critical'
    detection_model VARCHAR(50) DEFAULT 'spaghetti_detective', -- Model used for detection

    -- Media URLs (Supabase Storage)
    original_frame_url TEXT NOT NULL, -- Original captured frame
    annotated_frame_url TEXT, -- Frame with detection bounding boxes/masks
    before_frames_url TEXT, -- Video clip: 5 seconds before failure
    after_frames_url TEXT, -- Video clip: 5 seconds after failure (if available)

    -- Print context (captured at time of detection)
    gcode_filename VARCHAR(255),
    layer_number INTEGER,
    print_progress FLOAT CHECK (print_progress >= 0 AND print_progress <= 100),
    nozzle_temp FLOAT,
    bed_temp FLOAT,
    print_speed FLOAT,
    fan_speed INTEGER,
    z_height FLOAT,
    estimated_time_remaining INTEGER, -- seconds

    -- Detection details (raw AI output)
    detection_bbox JSONB, -- Bounding box coordinates if applicable: {x, y, width, height}
    detection_mask_url TEXT, -- Segmentation mask URL if applicable
    raw_prediction_data JSONB, -- Full model output for debugging

    -- GPT Vision Analysis (실시간 불량 분석)
    gpt_description TEXT, -- 상황 설명 (30-50+ 글자)
    gpt_root_cause TEXT, -- 원인 분석 (20-40 글자)
    gpt_suggested_action TEXT, -- 즉시 조치 (15-30 글자)
    gpt_prevention_tips TEXT, -- 예방 방법 (30-50+ 글자)
    gpt_raw_response TEXT, -- GPT의 전체 응답 원문

    -- Verification and dataset curation
    is_verified BOOLEAN DEFAULT FALSE, -- Has human reviewed this?
    is_false_positive BOOLEAN DEFAULT FALSE, -- User marked as incorrect detection
    verified_by UUID REFERENCES auth.users(id), -- Who verified it
    verified_at TIMESTAMPTZ,
    verification_notes TEXT,

    -- Dataset management
    include_in_dataset BOOLEAN DEFAULT TRUE, -- Include in training dataset export
    dataset_split VARCHAR(20), -- 'train', 'val', 'test' for ML splits
    dataset_exported_at TIMESTAMPTZ,

    -- Action taken
    action_taken VARCHAR(50), -- 'paused', 'stopped', 'notified', 'none'
    user_notified BOOLEAN DEFAULT FALSE,
    notification_sent_at TIMESTAMPTZ,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- Indexes for performance
-- ============================================================================

-- Query by user for dashboard
CREATE INDEX idx_failure_scenes_user_id ON failure_scenes(user_id, created_at DESC);

-- Query by device for device-specific analysis
CREATE INDEX idx_failure_scenes_device ON failure_scenes(device_uuid, created_at DESC);

-- Query by failure type for analytics
CREATE INDEX idx_failure_scenes_type ON failure_scenes(failure_type, created_at DESC);

-- Query unverified scenes for review queue
CREATE INDEX idx_failure_scenes_unverified ON failure_scenes(is_verified, created_at DESC)
    WHERE is_verified = FALSE;

-- Query verified true positives for dataset export
CREATE INDEX idx_failure_scenes_dataset ON failure_scenes(include_in_dataset, dataset_split, created_at DESC)
    WHERE is_verified = TRUE AND is_false_positive = FALSE;

-- ============================================================================
-- Row Level Security (RLS) Policies
-- ============================================================================

ALTER TABLE failure_scenes ENABLE ROW LEVEL SECURITY;

-- Users can view their own failure scenes
CREATE POLICY "Users can view own failure scenes"
    ON failure_scenes FOR SELECT
    USING (auth.uid() = user_id);

-- Service role can insert failure scenes (from AI detection service)
CREATE POLICY "Service can insert failure scenes"
    ON failure_scenes FOR INSERT
    WITH CHECK (true); -- Service role bypasses RLS, but this is explicit

-- Users can update verification status of their own scenes
CREATE POLICY "Users can verify own failure scenes"
    ON failure_scenes FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Users can delete their own failure scenes
CREATE POLICY "Users can delete own failure scenes"
    ON failure_scenes FOR DELETE
    USING (auth.uid() = user_id);

-- ============================================================================
-- Automatic updated_at trigger
-- ============================================================================

CREATE OR REPLACE FUNCTION update_failure_scenes_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_failure_scenes_updated_at
    BEFORE UPDATE ON failure_scenes
    FOR EACH ROW
    EXECUTE FUNCTION update_failure_scenes_updated_at();

-- ============================================================================
-- Storage Buckets Setup
-- ============================================================================

-- Create storage buckets for failure scene media
INSERT INTO storage.buckets (id, name, public)
VALUES
    ('failure-frames', 'failure-frames', false),
    ('failure-videos', 'failure-videos', false),
    ('failure-masks', 'failure-masks', false)
ON CONFLICT (id) DO NOTHING;

-- Storage policies for failure frames
CREATE POLICY "Users can view own failure frames"
    ON storage.objects FOR SELECT
    USING (bucket_id = 'failure-frames' AND (storage.foldername(name))[1] = auth.uid()::text);

CREATE POLICY "Service can upload failure frames"
    ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'failure-frames');

CREATE POLICY "Users can delete own failure frames"
    ON storage.objects FOR DELETE
    USING (bucket_id = 'failure-frames' AND (storage.foldername(name))[1] = auth.uid()::text);

-- Storage policies for failure videos
CREATE POLICY "Users can view own failure videos"
    ON storage.objects FOR SELECT
    USING (bucket_id = 'failure-videos' AND (storage.foldername(name))[1] = auth.uid()::text);

CREATE POLICY "Service can upload failure videos"
    ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'failure-videos');

CREATE POLICY "Users can delete own failure videos"
    ON storage.objects FOR DELETE
    USING (bucket_id = 'failure-videos' AND (storage.foldername(name))[1] = auth.uid()::text);

-- Storage policies for failure masks
CREATE POLICY "Users can view own failure masks"
    ON storage.objects FOR SELECT
    USING (bucket_id = 'failure-masks' AND (storage.foldername(name))[1] = auth.uid()::text);

CREATE POLICY "Service can upload failure masks"
    ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'failure-masks');

CREATE POLICY "Users can delete own failure masks"
    ON storage.objects FOR DELETE
    USING (bucket_id = 'failure-masks' AND (storage.foldername(name))[1] = auth.uid()::text);

-- ============================================================================
-- Sample Query Examples
-- ============================================================================

/*
-- Get all unverified failures for review
SELECT * FROM failure_scenes_review_queue LIMIT 20;

-- Get failure statistics by type
SELECT
    failure_type,
    COUNT(*) as total_detections,
    AVG(confidence) as avg_confidence,
    COUNT(*) FILTER (WHERE is_verified = TRUE AND is_false_positive = FALSE) as true_positives,
    COUNT(*) FILTER (WHERE is_verified = TRUE AND is_false_positive = TRUE) as false_positives
FROM failure_scenes
GROUP BY failure_type
ORDER BY total_detections DESC;

-- Get failure rate over time (daily)
SELECT
    DATE(created_at) as date,
    COUNT(*) as failure_count,
    COUNT(DISTINCT device_uuid) as affected_devices
FROM failure_scenes
WHERE is_verified = TRUE AND is_false_positive = FALSE
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- Export dataset statistics
SELECT
    dataset_split,
    failure_type,
    COUNT(*) as count
FROM failure_scenes_dataset_ready
GROUP BY dataset_split, failure_type
ORDER BY dataset_split, count DESC;
*/
