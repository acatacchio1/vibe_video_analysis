# Video Analyzer Web - Architecture Decision Records

## ADR-002: Two-Step Video Analysis System

### Status
**IMPLEMENTED** (v0.5.0) - Date: 2026-04-23  
**Note**: Current implementation has sequential synthesis limitation - needs proper queue for full parallelism

### Context
Video analysis involves both visual understanding (what's shown) and contextual understanding (what's being said). Traditional single-pass analysis either:
1. Analyzed visuals only, missing audio context
2. Combined visuals and audio in single prompt, requiring complex prompt engineering
3. Used sequential processing, slowing down analysis

Goal: Create a system that can:
- Use different LLM providers/models for vision vs. synthesis tasks
- Process frames in parallel across multiple GPU instances
- Provide real-time feedback for both analysis stages
- Allow users to compare vision-only vs. combined analysis

### Decision
Implemented a **two-step concurrent analysis system**:

**Architecture:**
- **Phase 1 (Vision Analysis)**: Frame-by-frame visual analysis using primary LLM
- **Phase 2 (Synthesis)**: Combines Phase 1 results with transcript using secondary LLM
- **Concurrent Execution**: Phase 2 starts as soon as Phase 1 completes for each frame
- **Separate Configuration**: Users select different providers/models/temperature for each phase
- **Dual View Interface**: Separate tabs for Vision Analysis vs. Combined Analysis results

**Implementation Details:**
1. **Worker Process Flow** (`worker.py`):
   - Modified main analysis loop to call `synthesize_frame()` after each frame analysis
   - Added Phase 2 configuration extraction from job params
   - Writes Phase 2 results to `synthesis.jsonl` alongside `frames.jsonl`

2. **Frontend Interface**:
   - Added Phase 2 provider/model/temperature selection controls
   - Created dual-tab display (Vision Analysis / Combined Analysis)
   - Added `appendCombinedLog()` function for Phase 2 results display
   - SocketIO `frame_synthesis` event for real-time Phase 2 updates

3. **Configuration Management**:
   - Phase 2 settings passed via `params.phase2_*` in job config
   - WebSocket handler (`handlers.py`) merges Phase 2 config into job params
   - Default Phase 2 model: `qwen3.5:9b-q8-128k` (available model)
   - Default Phase 2 URL: `192.168.1.237:11434` (not localhost for Docker)

4. **Data Flow**:
   ```
   Frame → Phase 1 (Vision LLM) → frames.jsonl → [Vision Tab]
                     ↓
            Phase 2 (Text LLM) → synthesis.jsonl → [Combined Tab]
   ```

**Current Limitation (To Be Fixed):**
Phase 2 synthesis runs **sequentially within the same loop** as Phase 1, causing vision analysis to wait for synthesis completion. This prevents full parallel GPU utilization across Ollama instances. A proper synthesis queue is needed for true parallelism.

### Consequences

#### Positive
- **Flexible Resource Allocation**: Different Ollama instances can handle vision vs. synthesis (e.g., .237 for vision, .241 for synthesis)
- **Specialized Models**: Can use vision-optimized models for Phase 1, text-optimized for Phase 2
- **Real-time Comparison**: Users can switch between vision-only and combined analysis views
- **Resource Efficiency**: Secondary Ollama instance can process synthesis while primary focuses on vision

#### Negative (Current Implementation)
- **Sequential Bottleneck**: Phase 1 waits for Phase 2 completion before next frame
- **Suboptimal GPU Utilization**: GPUs idle while waiting for sequential processing
- **Complex Configuration**: Users need to understand two different provider setups

#### Risks
- **Configuration Errors**: Users might select incompatible Phase 2 models
- **Network Latency**: Multiple Ollama instances increase network dependencies
- **Synchronization Issues**: Phase 2 depends on Phase 1 completion; failures could cascade

### Future Improvements
1. **Implement Proper Synthesis Queue**: Allow Phase 2 to lag behind Phase 1 with configurable queue depth
2. **Batch Processing**: Process multiple frames in parallel for Phase 2 when using same provider
3. **Fallback Strategies**: Automatic fallback if Phase 2 provider is unavailable
4. **Progress Tracking**: Separate progress bars for Phase 1 vs. Phase 2
5. **Resource Monitoring**: Track GPU utilization across both phases

## ADR-001: Transcript Injection Architecture (Legacy/Abandoned)