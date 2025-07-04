# FastSymApi Configuration

This document describes the environment variables that can be used to configure FastSymApi behavior.

## Performance Configuration

### FASTSYM_CHUNK_SIZE
- **Description**: Size of chunks used for file downloads and streaming (in bytes)
- **Default**: 2097152 (2MB)
- **Example**: `FASTSYM_CHUNK_SIZE=1048576` (1MB)

### FASTSYM_MAX_MEMORY_MB
- **Description**: Maximum memory usage limit for streaming operations (in MB)
- **Default**: 100
- **Example**: `FASTSYM_MAX_MEMORY_MB=200`

## Network Reliability Configuration

### FASTSYM_MAX_RETRIES
- **Description**: Maximum number of retry attempts for failed network requests
- **Default**: 3
- **Example**: `FASTSYM_MAX_RETRIES=5`

### FASTSYM_RETRY_BACKOFF
- **Description**: Backoff factor for exponential retry delays
- **Default**: 0.3
- **Example**: `FASTSYM_RETRY_BACKOFF=0.5`

## Usage Examples

### Development Environment
```bash
export FASTSYM_CHUNK_SIZE=1048576       # 1MB chunks for faster testing
export FASTSYM_MAX_RETRIES=1            # Fewer retries for faster feedback
export FASTSYM_MAX_MEMORY_MB=50         # Lower memory limit
```

### Production Environment
```bash
export FASTSYM_CHUNK_SIZE=4194304       # 4MB chunks for efficiency
export FASTSYM_MAX_RETRIES=5            # More retries for reliability
export FASTSYM_MAX_MEMORY_MB=500        # Higher memory limit
export FASTSYM_RETRY_BACKOFF=1.0        # Longer backoff to avoid overwhelming servers
```

### High-Performance Environment
```bash
export FASTSYM_CHUNK_SIZE=8388608       # 8MB chunks
export FASTSYM_MAX_MEMORY_MB=1000       # 1GB memory limit
```