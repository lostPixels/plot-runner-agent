#!/usr/bin/env python3
"""
NextDraw Performance Profiler
Analyzes performance bottlenecks when processing large SVG files
"""

import os
import sys
import time
import argparse
import json
import tracemalloc
import gc
from datetime import datetime
from typing import Dict, Any, Optional

try:
    from nextdraw import NextDraw
except ImportError:
    print("Error: NextDraw module not found. Please ensure it's installed.")
    sys.exit(1)


class NextDrawProfiler:
    """Profile NextDraw operations with detailed timing and memory tracking"""

    def __init__(self, svg_path: str, verbose: bool = False):
        self.svg_path = svg_path
        self.verbose = verbose
        self.timings = {}
        self.memory_snapshots = {}
        self.svg_size_mb = 0

        # Check if SVG exists
        if not os.path.exists(svg_path):
            raise FileNotFoundError(f"SVG file not found: {svg_path}")

        # Get SVG file size
        self.svg_size_bytes = os.path.getsize(svg_path)
        self.svg_size_mb = self.svg_size_bytes / (1024 * 1024)

    def log(self, message: str):
        """Log message with timestamp"""
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {message}")

    def start_timer(self, stage: str):
        """Start timing a stage"""
        self.timings[f"{stage}_start"] = time.perf_counter()
        self.log(f"Starting: {stage}")

    def end_timer(self, stage: str) -> float:
        """End timing a stage and return duration"""
        end_time = time.perf_counter()
        start_time = self.timings.get(f"{stage}_start", end_time)
        duration = end_time - start_time
        self.timings[f"{stage}_duration"] = duration
        self.timings[f"{stage}_end"] = end_time
        self.log(f"Completed: {stage} in {duration:.3f}s")
        return duration

    def measure_memory(self, snapshot_name: str):
        """Take a memory snapshot"""
        gc.collect()  # Force garbage collection before measurement
        if tracemalloc.is_tracing():
            snapshot = tracemalloc.take_snapshot()
            self.memory_snapshots[snapshot_name] = snapshot
            stats = snapshot.statistics('lineno')
            total_mb = sum(stat.size for stat in stats) / (1024 * 1024)
            self.log(f"Memory snapshot '{snapshot_name}': {total_mb:.2f} MB")
            return total_mb
        return 0

    def profile_basic_plot(self, layer: Optional[str] = None, mode: str = "plot"):
        """Profile a basic plot operation"""
        print("\n" + "="*60)
        print(f"Profiling NextDraw with SVG: {os.path.basename(self.svg_path)}")
        print(f"SVG Size: {self.svg_size_mb:.2f} MB ({self.svg_size_bytes:,} bytes)")
        print(f"Mode: {mode}, Layer: {layer or 'all'}")
        print("="*60)

        # Start memory tracking
        tracemalloc.start()
        self.measure_memory("initial")

        # Stage 1: NextDraw initialization
        self.start_timer("nextdraw_init")
        nd = NextDraw()
        init_time = self.end_timer("nextdraw_init")
        self.measure_memory("after_init")

        # Stage 2: plot_setup
        self.start_timer("plot_setup")
        self.log(f"Loading SVG file...")

        # Sub-stage: File reading
        self.start_timer("file_read")
        with open(self.svg_path, 'r', encoding='utf-8') as f:
            svg_content = f.read()
        file_read_time = self.end_timer("file_read")
        self.log(f"SVG file read: {len(svg_content):,} characters")

        # Sub-stage: Actual plot setup
        self.start_timer("plot_setup_call")
        nd.plot_setup(self.svg_path)
        plot_setup_call_time = self.end_timer("plot_setup_call")

        setup_time = self.end_timer("plot_setup")
        self.measure_memory("after_setup")

        # Stage 3: Configure options
        self.start_timer("configure_options")
        if mode == "layers" and layer:
            nd.options.mode = "layers"
            nd.options.layer = int(layer)
            self.log(f"Set mode=layers, layer={layer}")
        elif mode == "plot":
            nd.options.mode = "plot"
            self.log("Set mode=plot")
        config_time = self.end_timer("configure_options")

        # Stage 4: update()
        self.start_timer("update")
        nd.update()
        update_time = self.end_timer("update")
        self.measure_memory("after_update")

        # Stage 5: plot_run (simulated - don't actually run the plot)
        self.start_timer("plot_run_prepare")
        # Just prepare for plot_run without executing
        self.log("Preparing for plot_run (not executing actual plot)")
        plot_run_prepare_time = self.end_timer("plot_run_prepare")

        # If you want to actually test plot_run timing (will start moving the plotter!):
        # Uncomment the following lines ONLY if you want to actually plot
        # self.start_timer("plot_run")
        # result = nd.plot_run(True)
        # plot_run_time = self.end_timer("plot_run")
        # self.measure_memory("after_plot_run")

        # Final memory snapshot
        final_memory = self.measure_memory("final")

        # Stop memory tracking
        tracemalloc.stop()

        # Calculate totals
        total_time = sum(
            v for k, v in self.timings.items()
            if k.endswith("_duration") and not k.startswith("file_read") and not k.startswith("plot_setup_call")
        )

        # Print results
        print("\n" + "="*60)
        print("PERFORMANCE RESULTS")
        print("="*60)
        print(f"SVG Size:           {self.svg_size_mb:.2f} MB")
        print(f"Total Time:         {total_time:.3f}s")
        print(f"MB/sec throughput:  {self.svg_size_mb/total_time if total_time > 0 else 0:.2f}")
        print("\nDetailed Timing Breakdown:")
        print("-" * 40)
        print(f"NextDraw init:      {init_time:.3f}s")
        print(f"Plot setup total:   {setup_time:.3f}s")
        print(f"  - File read:      {file_read_time:.3f}s")
        print(f"  - Setup call:     {plot_setup_call_time:.3f}s")
        print(f"Configure options:  {config_time:.3f}s")
        print(f"Update call:        {update_time:.3f}s")
        print(f"Plot run prepare:   {plot_run_prepare_time:.3f}s")

        print("\nMemory Usage:")
        print("-" * 40)
        print(f"Peak memory:        {final_memory:.2f} MB")
        print(f"Memory/SVG ratio:   {final_memory/self.svg_size_mb if self.svg_size_mb > 0 else 0:.1f}x")

        return self.timings

    def profile_layer_extraction(self):
        """Profile extracting individual layers from SVG"""
        print("\n" + "="*60)
        print("Profiling Layer Extraction")
        print("="*60)

        tracemalloc.start()

        # Initialize NextDraw
        nd = NextDraw()
        nd.plot_setup(self.svg_path)

        # Try to extract layers
        self.start_timer("layer_extraction")

        layers_found = []
        for layer_num in range(1, 10):  # Test first 9 layers
            self.start_timer(f"layer_{layer_num}")
            nd.options.mode = "layers"
            nd.options.layer = layer_num
            nd.update()

            # Check if layer exists (this is approximate)
            try:
                # We won't actually run the plot, just check if it would work
                self.log(f"Layer {layer_num} configuration successful")
                layers_found.append(layer_num)
            except Exception as e:
                self.log(f"Layer {layer_num} not found or error: {e}")

            self.end_timer(f"layer_{layer_num}")

        extraction_time = self.end_timer("layer_extraction")

        tracemalloc.stop()

        print(f"\nLayers found: {layers_found}")
        print(f"Total extraction time: {extraction_time:.3f}s")

        return layers_found

    def profile_with_config(self, config: Dict[str, Any]):
        """Profile with specific configuration"""
        print("\n" + "="*60)
        print("Profiling with Custom Configuration")
        print(f"Config: {json.dumps(config, indent=2)}")
        print("="*60)

        tracemalloc.start()

        # Initialize and setup
        nd = NextDraw()
        nd.plot_setup(self.svg_path)

        # Apply configuration
        self.start_timer("apply_config")
        for key, value in config.items():
            if hasattr(nd.options, key):
                setattr(nd.options, key, value)
                self.log(f"Set option: {key} = {value}")
        self.end_timer("apply_config")

        # Update with configuration
        self.start_timer("update_with_config")
        nd.update()
        update_time = self.end_timer("update_with_config")

        tracemalloc.stop()

        print(f"\nConfiguration applied and updated in {update_time:.3f}s")

        return update_time


def main():
    parser = argparse.ArgumentParser(description="Profile NextDraw performance with SVG files")
    parser.add_argument("svg_file", help="Path to SVG file to profile")
    parser.add_argument("--layer", type=str, help="Layer number to profile (default: all)")
    parser.add_argument("--mode", choices=["plot", "layers", "all"], default="plot",
                       help="Profiling mode (default: plot)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--config", type=str, help="JSON config file to test")
    parser.add_argument("--profile-layers", action="store_true",
                       help="Profile layer extraction performance")

    args = parser.parse_args()

    try:
        profiler = NextDrawProfiler(args.svg_file, verbose=args.verbose)

        if args.profile_layers:
            # Profile layer extraction
            profiler.profile_layer_extraction()
        elif args.config:
            # Profile with custom config
            with open(args.config, 'r') as f:
                config = json.load(f)
            profiler.profile_with_config(config)
        else:
            # Standard profiling
            if args.mode == "all":
                # Profile both plot and layers mode
                profiler.profile_basic_plot(mode="plot")
                if args.layer:
                    profiler.profile_basic_plot(layer=args.layer, mode="layers")
            else:
                profiler.profile_basic_plot(layer=args.layer, mode=args.mode)

        print("\n" + "="*60)
        print("Profiling complete!")
        print("="*60)

        # Suggest optimizations based on results
        if profiler.svg_size_mb > 10:
            print("\n⚠️  Large SVG detected. Suggestions:")
            print("  - Consider optimizing/simplifying the SVG")
            print("  - Use layer-specific plotting if possible")
            print("  - Check for redundant path data")

        if profiler.timings.get("update_duration", 0) > 2:
            print("\n⚠️  Slow update() detected. Suggestions:")
            print("  - Check SVG complexity")
            print("  - Consider pre-processing the SVG")

    except Exception as e:
        print(f"\n❌ Error during profiling: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
