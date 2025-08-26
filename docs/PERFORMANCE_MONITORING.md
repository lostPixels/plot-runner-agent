# Performance Monitoring and Optimization Guide

## Overview

This guide helps you identify and resolve performance bottlenecks when processing large SVG files with the NextDraw plotter system. The application now includes comprehensive timing instrumentation to track each stage of the plotting pipeline.

## Performance Monitoring Features

### 1. Automatic Timing Logs

The application automatically logs detailed timing information for every plot operation. These logs help identify where delays occur in the plotting pipeline.

#### Key Timing Stages Tracked:

1. **Request Processing** - Time from API request receipt to response
2. **NextDraw Initialization** - Creating the NextDraw instance
3. **SVG Setup** - Loading and parsing the SVG file
4. **Layer Processing** - Extracting specific layers (if applicable)
5. **Configuration Application** - Applying plot settings
6. **Update Phase** - NextDraw internal update processing
7. **Plot Execution** - Actual plotting operation

#### Example Log Output:

```
2025-08-26 14:00:01,100 INFO: SVG file 'design.svg' size: 15.34 MB (16,089,234 bytes)
2025-08-26 14:00:01,101 INFO: Pre-plot preparation time: 0.002s | SVG size: 15.34MB
2025-08-26 14:00:01,102 INFO: Plot thread started - Time from request: 0.003s
2025-08-26 14:00:01,103 INFO: NextDraw instance created in 0.125s
2025-08-26 14:00:01,450 INFO: Main plot_setup completed in 0.347s
2025-08-26 14:00:01,523 INFO: Final update() completed in 0.073s
2025-08-26 14:00:01,524 INFO: Total SVG setup time: 0.421s
2025-08-26 14:00:01,525 INFO: Starting plot_run() - Time from request to plot_run start: 0.425s
2025-08-26 14:00:01,525 INFO: TIMING SUMMARY | Size: 15.34MB | Setup: 0.425s | Plot: 45.2s | Total: 45.625s
```

### 2. SVG File Size Tracking

Every plot operation logs the SVG file size to help correlate performance with file complexity:

```
INFO: SVG file size: 15.34 MB (16,089,234 bytes)
```

### 3. Performance Summary

At the end of each plot operation, a summary line provides key metrics:

```
TIMING SUMMARY | Size: 15.34MB | Setup: 0.425s | Plot: 45.2s | Total: 45.625s
```

## Using the Performance Profiler

The included `profile_nextdraw.py` utility provides detailed performance analysis without actually running plots.

### Basic Usage

```bash
# Profile a specific SVG file
python profile_nextdraw.py your_design.svg

# Profile with verbose output
python profile_nextdraw.py your_design.svg --verbose

# Profile a specific layer
python profile_nextdraw.py your_design.svg --layer 2 --mode layers

# Profile layer extraction performance
python profile_nextdraw.py your_design.svg --profile-layers
```

### Profiler Output

```
============================================================
Profiling NextDraw with SVG: design.svg
SVG Size: 15.34 MB (16,089,234 bytes)
Mode: plot, Layer: all
============================================================

PERFORMANCE RESULTS
============================================================
SVG Size:           15.34 MB
Total Time:         0.548s
MB/sec throughput:  28.01

Detailed Timing Breakdown:
----------------------------------------
NextDraw init:      0.125s
Plot setup total:   0.347s
  - File read:      0.042s
  - Setup call:     0.305s
Configure options:  0.001s
Update call:        0.073s
Plot run prepare:   0.002s

Memory Usage:
----------------------------------------
Peak memory:        89.45 MB
Memory/SVG ratio:   5.8x
```

## Common Performance Bottlenecks

### 1. Large SVG Files (>10MB)

**Symptoms:**
- Long delays before plotting starts
- High memory usage
- Slow `plot_setup()` times

**Solutions:**
- Optimize SVG files using tools like SVGO
- Remove unnecessary metadata and comments
- Simplify complex paths
- Split into multiple layers and plot separately

### 2. Complex Path Data

**Symptoms:**
- Slow `update()` calls
- High CPU usage during processing
- Long delays in `plot_run()`

**Solutions:**
- Reduce path precision (fewer decimal places)
- Combine similar paths
- Remove duplicate or overlapping paths
- Use straight lines instead of curves where possible

### 3. Serial Communication Delays

**Symptoms:**
- "Slow request detected" warnings
- Delays before plot starts moving
- Connection timeout messages

**Solutions:**
- Already fixed with asynchronous serial communication
- Ensure serial display is optional
- Check USB cable quality
- Reduce retry attempts if display not needed

### 4. Layer Processing Overhead

**Symptoms:**
- Extra delays when plotting specific layers
- Multiple PLOB creation logs
- Slow layer extraction

**Solutions:**
- Pre-process SVGs to separate layers
- Cache layer information
- Plot "all" layers when possible

## Optimization Strategies

### 1. SVG File Optimization

```bash
# Using SVGO (install with npm install -g svgo)
svgo input.svg -o optimized.svg

# Remove metadata and comments
svgo input.svg -o clean.svg --disable=removeMetadata

# Reduce precision
svgo input.svg -o reduced.svg --precision=2
```

### 2. Pre-Processing Large Files

For consistently large files, consider pre-processing:

```python
# Split large SVG into chunks
# Process layers separately
# Cache processed results
```

### 3. Configuration Tuning

Adjust NextDraw configuration for better performance:

```json
{
  "digest": 2,
  "speed_pendown": 50,
  "speed_penup": 75,
  "acceleration": 10
}
```

### 4. Hardware Considerations

- Use fast storage (SSD) for SVG files
- Ensure adequate RAM (>4GB recommended for large files)
- Use USB 3.0 connections where possible
- Keep firmware updated

## Interpreting Timing Metrics

### Healthy Performance Indicators

| Metric | Good | Acceptable | Needs Attention |
|--------|------|------------|-----------------|
| Setup time (per MB) | <50ms | 50-100ms | >100ms |
| Update() call | <100ms | 100-500ms | >500ms |
| Request to plot_run | <1s | 1-3s | >3s |
| Memory ratio | <3x | 3-6x | >6x |

### Warning Signs

1. **Setup time > 1 second for files under 5MB**
   - Check file complexity
   - Look for corrupted data

2. **Memory usage > 10x file size**
   - Memory leak possible
   - SVG may have recursive structures

3. **Update() taking > 2 seconds**
   - SVG too complex
   - Consider simplification

4. **Plot_run() delay > 5 seconds**
   - Check plotter connection
   - Verify configuration

## Monitoring in Production

### Enable Detailed Logging

Set logging level in your environment:

```bash
export PLOTTER_LOG_LEVEL=INFO
```

### Log Analysis

Monitor key metrics over time:

```bash
# Extract timing summaries
grep "TIMING SUMMARY" app.log | tail -20

# Find slow requests
grep "Slow request detected" app.log

# Track file sizes
grep "SVG file size" app.log | awk '{print $5, $6}'
```

### Performance Dashboards

Consider integrating with monitoring tools:
- Prometheus for metrics collection
- Grafana for visualization
- ELK stack for log analysis

## Troubleshooting Guide

### Problem: Plot takes minutes to start

**Check:**
1. SVG file size in logs
2. Setup and update timing
3. Memory usage
4. Serial communication logs

**Fix:**
- Optimize SVG file
- Disable serial display if not needed
- Check system resources

### Problem: Intermittent hanging

**Check:**
1. Serial display connection logs
2. "Slow request detected" warnings
3. Thread status

**Fix:**
- Update to latest version (includes async serial fix)
- Reduce serial retry attempts
- Check USB connections

### Problem: Out of memory errors

**Check:**
1. SVG file size
2. Memory ratio in profiler
3. System available RAM

**Fix:**
- Process in smaller chunks
- Increase system RAM
- Optimize SVG complexity

## Best Practices

1. **Always monitor file sizes** - Log and track SVG sizes
2. **Set performance budgets** - Define acceptable delays
3. **Profile before optimization** - Measure, don't guess
4. **Test with real files** - Use production SVGs for testing
5. **Document bottlenecks** - Keep notes on specific file issues
6. **Regular maintenance** - Clean up temporary files
7. **Monitor trends** - Watch for degradation over time

## Advanced Profiling

For deeper analysis, use Python profiling tools:

```python
import cProfile
import pstats

# Profile the plot operation
cProfile.run('plotter_controller.plot_file(svg_path)', 'profile_stats')

# Analyze results
stats = pstats.Stats('profile_stats')
stats.sort_stats('cumulative')
stats.print_stats(20)
```

## Reporting Performance Issues

When reporting performance problems, include:

1. **SVG file size and complexity**
2. **Timing summary from logs**
3. **System specifications**
4. **Profiler output**
5. **Sample SVG file (if possible)**

## Future Improvements

Planned performance enhancements:
- [ ] SVG caching system
- [ ] Parallel layer processing
- [ ] Progressive rendering
- [ ] Compression support
- [ ] Background pre-processing
- [ ] Performance regression tests
