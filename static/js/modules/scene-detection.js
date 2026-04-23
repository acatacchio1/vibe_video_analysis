// Scene Detection Module
// Handles PySceneDetect integration for scene detection and scene-aware deduplication

const sceneDetection = (function() {
    // Module state
    let currentVideo = null;
    let detectedScenes = [];
    let sceneAwareDeduplicationEnabled = false;
    let appliedSceneThreshold = null;

    // DOM elements
    let sceneDetectBtn, sceneThresholdInput, sceneAwareCheckbox;
    let sceneResultsDiv, sceneCountSpan, sceneAvgLengthSpan, sceneListDiv;
    let sceneApplyBtn, sceneClearBtn;

    // Initialize module
    function init() {
        // Cache DOM elements
        sceneDetectBtn = document.getElementById('scene-detect-btn');
        sceneThresholdInput = document.getElementById('scene-threshold-input');
        sceneAwareCheckbox = document.getElementById('scene-aware-dedup-checkbox');
        sceneResultsDiv = document.getElementById('scene-results');
        sceneCountSpan = document.getElementById('scene-count');
        sceneAvgLengthSpan = document.getElementById('scene-avg-length');
        sceneListDiv = document.getElementById('scene-list');
        sceneApplyBtn = document.getElementById('scene-apply-btn');
        sceneClearBtn = document.getElementById('scene-clear-btn');

        // Event listeners
        sceneDetectBtn.addEventListener('click', handleSceneDetection);
        sceneApplyBtn.addEventListener('click', applyScenesToAnalysis);
        sceneClearBtn.addEventListener('click', clearScenes);
        sceneAwareCheckbox.addEventListener('change', toggleSceneAwareDeduplication);

        // Update when video selection changes
        const videoSelect = document.getElementById('video-select');
        if (videoSelect) {
            videoSelect.addEventListener('change', handleVideoSelectionChange);
        }

        console.log('Scene detection module initialized');
    }

    // Handle video selection change
    function handleVideoSelectionChange() {
        const videoSelect = document.getElementById('video-select');
        currentVideo = videoSelect.value;
        
        // Clear scene detection results when video changes
        if (currentVideo) {
            clearScenes();
        }
    }

    // Handle scene detection button click
    async function handleSceneDetection() {
        if (!currentVideo) {
            showToast('Please select a video first', 'error');
            return;
        }

        const threshold = parseInt(sceneThresholdInput.value) || 30;
        
        // Show loading state
        sceneDetectBtn.disabled = true;
        sceneDetectBtn.textContent = 'Detecting...';
        
        try {
            // Call scene detection API
            const response = await fetch(`/api/videos/${encodeURIComponent(currentVideo)}/scenes`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    threshold: threshold,
                    method: 'content' // Default to content-based detection
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const scenes = await response.json();
            
            // Store scenes and update UI
            detectedScenes = scenes;
            appliedSceneThreshold = threshold;
            updateSceneUI();
            
            // Show results section
            sceneResultsDiv.classList.remove('hidden');
            
            // Update frame browser visualization
            if (typeof window.updateSceneVisualization === 'function') {
                window.updateSceneVisualization(scenes);
            }
            
            showToast(`Detected ${scenes.length} scenes`, 'success');
            
        } catch (error) {
            console.error('Scene detection failed:', error);
            showToast(`Scene detection failed: ${error.message}`, 'error');
        } finally {
            // Reset button state
            sceneDetectBtn.disabled = false;
            sceneDetectBtn.textContent = 'Detect Scenes';
        }
    }

    // Update scene detection UI with results
    function updateSceneUI() {
        if (detectedScenes.length === 0) {
            sceneCountSpan.textContent = '--';
            sceneAvgLengthSpan.textContent = '--';
            sceneListDiv.innerHTML = '<div class="scene-empty">No scenes detected</div>';
            return;
        }

        // Calculate average frames per scene
        const avgFrames = Math.round(detectedScenes.reduce((sum, scene) => sum + (scene.end - scene.start + 1), 0) / detectedScenes.length);
        
        // Update summary
        sceneCountSpan.textContent = detectedScenes.length;
        sceneAvgLengthSpan.textContent = `${avgFrames} frames`;

        // Build scene list
        let sceneListHTML = '';
        detectedScenes.forEach((scene, index) => {
            const sceneNumber = index + 1;
            const frameCount = scene.end - scene.start + 1;
            const timeRange = formatTimeRange(scene.start_time, scene.end_time);
            
            sceneListHTML += `
                <div class="scene-item" data-scene-index="${index}">
                    <span class="scene-number">Scene ${sceneNumber}</span>
                    <span class="scene-frame-count">${frameCount} frames</span>
                    <span class="scene-time-range">${timeRange}</span>
                    <button class="scene-preview-btn" onclick="sceneDetection.previewScene(${index})" title="Preview scene">👁️</button>
                </div>
            `;
        });

        sceneListDiv.innerHTML = sceneListHTML;
    }

    // Format time range for display
    function formatTimeRange(startTime, endTime) {
        const format = (seconds) => {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = Math.floor(seconds % 60);
            const ms = Math.floor((seconds % 1) * 1000);
            
            if (hours > 0) {
                return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
            }
            return `${minutes}:${secs.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
        };
        
        return `${format(startTime)} - ${format(endTime)}`;
    }

    // Preview a specific scene in the frame browser
    function previewScene(sceneIndex) {
        if (!detectedScenes[sceneIndex]) return;
        
        const scene = detectedScenes[sceneIndex];
        
        // Check if frame-browser module is available
        if (typeof window.initFrameBrowser !== 'undefined' && typeof window.loadFrameRange !== 'undefined') {
            // Set frame range to scene boundaries
            document.getElementById('start-frame-input').value = scene.start;
            document.getElementById('end-frame-input').value = scene.end;
            
            // Update sliders
            const startSlider = document.getElementById('start-frame-slider');
            const endSlider = document.getElementById('end-frame-slider');
            
            if (startSlider && endSlider) {
                startSlider.value = scene.start;
                endSlider.value = scene.end;
                
                // Trigger change events
                startSlider.dispatchEvent(new Event('input'));
                endSlider.dispatchEvent(new Event('input'));
            }
            
            showToast(`Previewing Scene ${sceneIndex + 1} (frames ${scene.start}-${scene.end})`, 'info');
        } else {
            showToast('Frame browser not available for preview', 'warning');
        }
    }

    // Apply scene detection to current analysis
    async function applyScenesToAnalysis() {
        if (!currentVideo || detectedScenes.length === 0) {
            showToast('No scenes detected to apply', 'warning');
            return;
        }

        // If scene-aware deduplication is enabled, we need to handle it specially
        if (sceneAwareCheckbox.checked) {
            try {
                // Show loading
                sceneApplyBtn.disabled = true;
                sceneApplyBtn.textContent = 'Applying...';
                
                // Call scene-aware deduplication API
                const response = await fetch(`/api/videos/${encodeURIComponent(currentVideo)}/scene-aware-dedup`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        scene_threshold: appliedSceneThreshold || 30,
                        dedup_threshold: 15, // Default dedup threshold within scenes
                        preserve_scene_structure: true,
                        parallel_processing: true
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const result = await response.json();
                
                // Update dedup results display
                updateDedupResultsAfterSceneAwareProcessing(result);
                
                showToast(`Scene-aware deduplication completed. Kept ${result.frames_kept} frames across ${result.scene_count} scenes.`, 'success');
                
            } catch (error) {
                console.error('Scene-aware deduplication failed:', error);
                showToast(`Scene-aware deduplication failed: ${error.message}`, 'error');
            } finally {
                sceneApplyBtn.disabled = false;
                sceneApplyBtn.textContent = 'Apply to Analysis';
            }
        } else {
            // Just use scene boundaries for analysis scope
            // This could limit analysis to specific scenes in future enhancement
            showToast('Scenes available for analysis (scene-aware deduplication not enabled)', 'info');
        }
    }

    // Update dedup results display after scene-aware processing
    function updateDedupResultsAfterSceneAwareProcessing(result) {
        // Find dedup results table and update it
        const dedupTbody = document.getElementById('dedup-multi-tbody');
        if (!dedupTbody) return;
        
        // Clear existing rows
        dedupTbody.innerHTML = '';
        
        // Add new row for scene-aware dedup result
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong>Scene-aware (${result.scene_count} scenes)</strong></td>
            <td>${result.frames_kept}</td>
            <td>${result.frames_dropped}</td>
            <td>${result.drop_percentage.toFixed(1)}%</td>
            <td><button class="btn secondary small" onclick="sceneDetection.reapplySceneAwareDedup()">Use</button></td>
        `;
        dedupTbody.appendChild(row);
        
        // Update original frame count if available
        const originalCountSpan = document.getElementById('dedup-original-count');
        if (originalCountSpan && result.original_frames) {
            originalCountSpan.textContent = result.original_frames;
        }
    }

    // Re-apply scene-aware deduplication with current settings
    function reapplySceneAwareDedup() {
        if (!currentVideo || detectedScenes.length === 0) {
            showToast('No scene detection results to re-apply', 'warning');
            return;
        }
        
        // This would trigger a new scene-aware deduplication with stored parameters
        showToast('Scene-aware deduplication would be re-applied with current settings', 'info');
        // In a full implementation, this would re-call applyScenesToAnalysis()
    }

    // Clear scene detection results
    function clearScenes() {
        detectedScenes = [];
        appliedSceneThreshold = null;
        
        // Hide results section
        sceneResultsDiv.classList.add('hidden');
        
        // Reset UI
        sceneCountSpan.textContent = '--';
        sceneAvgLengthSpan.textContent = '--';
        sceneListDiv.innerHTML = '<div class="scene-empty">No scenes detected yet</div>';
        
        // Uncheck scene-aware checkbox
        sceneAwareCheckbox.checked = false;
        sceneAwareDeduplicationEnabled = false;
        
        showToast('Scene detection results cleared', 'info');
    }

    // Toggle scene-aware deduplication
    function toggleSceneAwareDeduplication() {
        sceneAwareDeduplicationEnabled = sceneAwareCheckbox.checked;
        
        if (sceneAwareDeduplicationEnabled && detectedScenes.length === 0) {
            showToast('First detect scenes to enable scene-aware deduplication', 'warning');
            sceneAwareCheckbox.checked = false;
            sceneAwareDeduplicationEnabled = false;
        }
    }

    // Get current scene detection state for analysis submission
    function getAnalysisParameters() {
        if (!sceneAwareDeduplicationEnabled || detectedScenes.length === 0) {
            return null;
        }
        
        return {
            scene_aware: true,
            scene_count: detectedScenes.length,
            scene_threshold: appliedSceneThreshold,
            scenes: detectedScenes.map(scene => ({
                start: scene.start,
                end: scene.end,
                start_time: scene.start_time,
                end_time: scene.end_time
            }))
        };
    }

    // Show toast notification (using existing UI module)
    function showToast(message, type = 'info') {
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    }

    // Public API
    return {
        init: init,
        previewScene: previewScene,
        reapplySceneAwareDedup: reapplySceneAwareDedup,
        getAnalysisParameters: getAnalysisParameters
    };
})();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', sceneDetection.init);
} else {
    sceneDetection.init();
}

// Export for other modules
if (typeof window !== 'undefined') {
    window.sceneDetection = sceneDetection;
}