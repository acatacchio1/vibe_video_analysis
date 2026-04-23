# Video Analyzer Web - Architecture Decision Records

## ADR-001: Transcript Injection Architecture (Legacy/Abandoned)

### Status
**ABANDONED** - Date: 2026-04-23

### Context
Video Analyzer Web processes videos through multiple stages: frame extraction, transcription, frame analysis (using LLMs), and video reconstruction. A key feature is injecting transcript context into frame analysis prompts to provide the LLM with audio context for each video frame.

The original implementation attempted to inject transcript segments into frame analysis prompts by:
1. Loading transcript segments with timestamps
2. For each frame, finding relevant transcript segments based on frame timestamp
3. Injecting transcript context into the LLM prompt template

### Decision
The original transcript injection approach used runtime prompt modification within the worker process loop, with the following characteristics:

**Architecture:**
- **Prompt Token System**: Used placeholder tokens in prompt templates (`{TRANSCRIPT_CONTEXT}`, `{TRANSCRIPT_RECENT}`, `{TRANSCRIPT_PRIOR}`)
- **Runtime Injection**: Modified `analyzer.frame_prompt` property during frame iteration
- **Timestamp Matching**: Mapped frame numbers to video timestamps using `frames_index.json`
- **Context Selection**: Selected "recent" (current timeframe) and "prior" (previous context) transcript segments

**Implementation Details:**
1. **Worker Process Flow** (`worker.py`):
   - Loaded transcript segments with validated end times
   - For each frame, calculated `current_ts` from dedup mapping
   - Found transcript segments near frame timestamp (15-second buffer)
   - Built `recent_transcript` (current segment) and `prior_transcript` (up to 2 prior segments)
   - Injected via token replacement or fallback appending

2. **Prompt Templates**:
   - `frame_with_transcript.txt`: Used single `{TRANSCRIPT_CONTEXT}` token with formatted section
   - `frame_analysis.txt`: Used separate `{TRANSCRIPT_RECENT}` and `{TRANSCRIPT_PRIOR}` tokens
   - Fallback: Appended transcript context if no tokens found

3. **Data Flow**:
   ```
   Frame → Timestamp → Transcript Segments → Context Building → Prompt Injection → LLM Analysis
   ```

### Consequences

#### Positive (Intended)
- **Contextual Analysis**: Provided audio context for visual analysis
- **Timestamp Accuracy**: Used frame-to-timestamp mapping for precise alignment
- **Flexible Prompts**: Supported multiple prompt template formats

#### Negative (Observed Issues)
1. **Complex State Management**:
   - Modified shared `analyzer.frame_prompt` property in loop
   - State corruption across frames (duplicate transcript injections)
   - Required restoring original prompt each iteration

2. **External Dependency Issues**:
   - Relied on `video-analyzer` package's internal `VideoAnalyzer` API
   - No clear interface for transcript injection
   - Monkey-patching required for per-frame context

3. **Error-Prone Implementation**:
   - Multiple token formats created confusion
   - `context_section` variable referenced but not always defined
   - `corrected_ts` variable bug (referenced but never defined)
   - Path-dependent prompt loading with hardcoded paths

4. **Maintenance Challenges**:
   - Difficult to debug transcript injection failures
   - Silent failures when tokens not found in prompts
   - Complex logic with multiple fallback paths

5. **Performance Issues**:
   - Repeated string operations on prompt templates
   - No caching of transcript segment lookups
   - O(n) search through transcript segments for each frame

### Abandonment Rationale
The approach is being abandoned due to:

1. **Architectural Flaws**: Tight coupling with external package internals
2. **Maintenance Burden**: Complex, bug-prone implementation
3. **Poor Observability**: Difficult to verify transcript injection worked
4. **Limited Flexibility**: Hard to extend or modify injection logic
5. **Implementation Bugs**: Critical issues like `corrected_ts` undefined variable

**Evidence of Failure**: Frame analysis outputs showed no transcript context despite the injection logic appearing to run successfully in logs.

### Future Direction
A new approach will be developed with these principles:
1. **Clean Separation**: Decouple transcript injection from frame analysis
2. **Explicit Interfaces**: Well-defined APIs between components
3. **Testability**: Unit-testable injection logic
4. **Observability**: Clear logging and validation of injection results
5. **Simplicity**: Reduce complexity and edge cases

### Lessons Learned
1. **Avoid modifying shared state** in iteration loops
2. **Prefer composition over monkey-patching** of external APIs
3. **Validate assumptions** about prompt template formats
4. **Design for testability** from the beginning
5. **Implement proper error handling** for edge cases

---
*This decision record documents the legacy approach to inform future architectural decisions and prevent recurrence of similar issues.*