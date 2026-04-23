# Test Videos for Parallel Deduplication Testing

## Directory Structure

```
test_videos/
├── small/           # 10-100 frames
│   ├── source/      # Original video files
│   └── processed/   # Extracted frames for testing
├── medium/          # 100-1000 frames  
│   ├── source/
│   └── processed/
├── large/           # 1000-5000 frames
│   ├── source/
│   └── processed/
└── very_large/      # 5000+ frames
    ├── source/
    └── processed/
```

## Usage for Testing

1. **Add test videos**: Place videos in appropriate `source/` directory
2. **Run frame extraction**: Use the test framework to extract frames
3. **Run deduplication tests**: Test parallel vs sequential performance

## Video Guidelines

- **Small**: 10-100 frames (e.g., 3-10 second clips)
- **Medium**: 100-1000 frames (e.g., 30 second to 1 minute clips)
- **Large**: 1000-5000 frames (e.g., 1-5 minute clips)
- **Very Large**: 5000+ frames (e.g., 5+ minute clips)

## Expected Test Coverage

Each category tests different aspects:
- **Small**: Parallel overhead vs sequential
- **Medium**: Scaling behavior
- **Large**: Performance optimization
- **Very Large**: Memory management and stress testing