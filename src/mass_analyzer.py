#!/usr/bin/env python3
"""
Vocal characteristics batch-analysis pipeline.

Walks a directory tree, finds .wav and .mp3 audio files, and - for each one,
concurrently across a thread pool - analyzes it with AudioFeatureExtractor
and renders ONE combined PNG:

    +------------------------+------------------------------+
    | Pitch vs time          | Size vs Weight (density,      |
    |                        | viridis, square) - spans 3    |
    +------------------------+ rows                          |
    | Weight vs time         +------------------------------+
    |                        | Pitch density (viridis)       |
    +------------------------+------------------------------+
    | Size vs time            | Weight/Size/Pitch 3D scatter  |
    |                        | (density, viridis)             |
    +------------------------+------------------------------+

Then a single summary image is produced, aggregating the "Size vs Weight"
and "Pitch density" panels across every analyzed file.

No connecting lines are ever drawn - everything is scatter/heatmap only.
"""

import os
import re
import time
import threading
import argparse
from pathlib import Path
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import matplotlib
from scipy.interpolate import griddata

matplotlib.use("Agg")  # safe for headless / batch use
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (registers the '3d' projection)
import matplotlib.animation as animation
from scipy.stats import gaussian_kde

from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor
from signal_processing.AudioFeatures import AudioFeatures, SignalTimeSeries
import PlotsSpec


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

# Only .wav and .mp3 files are supported.
AUDIO_FILE_PATTERN = r"\.(wav|mp3)$"

# Number of worker threads used to run AudioFeatureExtractor.analyzeFile()
# concurrently across files.
ANALYSIS_THREADS = 12


def find_audio_files(root_dir: str, pattern: str) -> List[Path]:
    """Recursively find files under root_dir whose filename matches `pattern`."""
    regex = re.compile(pattern, re.IGNORECASE)
    matches = []
    for dirpath, _dirnames, filenames in os.walk(root_dir):
        for fname in filenames:
            if regex.search(fname):
                matches.append(Path(dirpath) / fname)
    return sorted(matches)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

SCATTER_KW = dict(s=8, alpha=0.6, edgecolors="none")  # points only, no lines


def _draw_timeseries(ax, ts: SignalTimeSeries, label: str, color: str) -> None:
    x = ts.get_x_without_NaN()
    y = ts.get_y_without_NaN()
    ax.scatter(x, y, color=color, **SCATTER_KW)
    ax.set_ylabel(label)
    ax.grid(True, alpha=0.3)


def _draw_size_weight_scatter(fig, ax, weight_vals: np.ndarray, size_vals: np.ndarray) -> None:
    n = min(weight_vals.size, size_vals.size)
    x, y = weight_vals[:n], size_vals[:n]

    if x.size >= 3:
        # Color each point by local point density (viridis), estimated with
        # a Gaussian KDE. Plot lowest-density points first so the densest
        # points end up drawn on top and stay visible.
        density = gaussian_kde(np.vstack([x, y]))(np.vstack([x, y]))
        order = np.argsort(density)
        x, y, density = x[order], y[order], density[order]
        sc = ax.scatter(x, y, c=density, cmap="viridis", s=8, alpha=0.8, edgecolors="none")
        fig.colorbar(sc, ax=ax, label="Density", fraction=0.046, pad=0.04)
    else:
        # Not enough points for a KDE - fall back to a plain scatter.
        ax.scatter(x, y, color="tab:purple", **SCATTER_KW)

    ax.set_xlabel("Weight")
    ax.set_ylabel("Size")
    ax.set_title("Size vs Weight (density)")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 4)
    ax.set_ylim(0, 40)


def _draw_pitch_heatmap(fig, ax, pitch_vals: np.ndarray, bins: int = 60) -> None:
    # Pitch on its own is a single axis of values. To turn that into a
    # heatmap (rather than a 1-D scatter/strip), we histogram it against a
    # dummy constant second axis and color by count with viridis - this
    # shows which pitch ranges are most common across the signal.
    if pitch_vals.size > 0:
        h = ax.hist2d(
            pitch_vals,
            np.zeros_like(pitch_vals),
            bins=[bins, 1],
            range=[[0, 450], [-0.5, 0.5]],
            cmap="viridis",
        )
        fig.colorbar(h[3], ax=ax, label="Count", fraction=0.046, pad=0.04)
    ax.set_xlabel("Pitch (Hz)")
    ax.set_xlim(0, 450)
    ax.set_yticks([])
    ax.set_title("Pitch (density)")


def _draw_weight_size_pitch_3d(
        fig, ax, weight_vals: np.ndarray, size_vals: np.ndarray, pitch_vals: np.ndarray
) -> None:
    """3D scatter: weight (X), size (Y), pitch (Z), colored by local point density (viridis)."""
    n = min(weight_vals.size, size_vals.size, pitch_vals.size)
    x, y, z = weight_vals[:n], size_vals[:n], pitch_vals[:n]

    if x.size >= 4:
        # Color each point by local point density (viridis), estimated with
        # a Gaussian KDE over all three dimensions.
        density = gaussian_kde(np.vstack([x, y, z]))(np.vstack([x, y, z]))
        order = np.argsort(density)
        x_s, y_s, z_s, density_s = x[order], y[order], z[order], density[order]

        sc = ax.scatter(x_s, y_s, z_s, c=density_s, cmap="viridis", s=8, alpha=0.8, edgecolors="none")
        fig.colorbar(sc, ax=ax, label="Density", fraction=0.046, pad=0.1, shrink=0.7)
    else:
        # Not enough points for a KDE - fall back to a plain scatter.
        ax.scatter(x, y, z, color="tab:purple", s=8, alpha=0.8, edgecolors="none")

    ax.set_xlabel("Weight")
    ax.set_ylabel("Size")
    ax.set_zlabel("Pitch")
    ax.set_xlim(0, 4)
    ax.set_ylim(0, 40)
    ax.set_zlim(50, 450)

    ax.set_title("Weight / Size / Pitch (density scatter)")

    # Rotate the plot Z-axis
    # Default elev is 30, default azim is -60.
    ax.view_init(elev=30, azim=142.5)


def create_combined_rotating_gif(features: AudioFeatures, out_path: Path, title: str) -> None:
    """
    Creates a combined figure (all plots) saved as a rotating GIF.
    The 3D plot rotates 36 degrees per frame (500ms per frame).
    """
    import matplotlib.animation as animation

    fig = Figure(figsize=(14, 13))
    FigureCanvasAgg(fig)

    # INCREASED hspace TO 0.5 to prevent titles and x-axis labels from overlapping
    # Lowered top to 0.90 to give the suptitle more breathing room
    fig.subplots_adjust(left=0.05, right=0.95, bottom=0.05, top=0.90, wspace=0.2, hspace=1)

    gs = fig.add_gridspec(8, 2, width_ratios=[1.3, 1])

    ax_pitch_t = fig.add_subplot(gs[0:3, 0])
    ax_weight_t = fig.add_subplot(gs[3:6, 0], sharex=ax_pitch_t)
    ax_size_t = fig.add_subplot(gs[6:8, 0], sharex=ax_pitch_t)

    _draw_timeseries(ax_pitch_t, features.pitch, "Pitch", PlotsSpec.pitch)
    _draw_timeseries(ax_weight_t, features.weight_instantaneous, "Weight", PlotsSpec.weight)
    _draw_timeseries(ax_size_t, features.size, "Size", PlotsSpec.size)
    ax_pitch_t.set_ylim(0, 450)
    ax_weight_t.set_ylim(0, 4)
    ax_size_t.set_ylim(0, 40)
    ax_size_t.set_xlabel("Time (s)")

    ax_size_weight = fig.add_subplot(gs[0:3, 1])
    ax_pitch_heat = fig.add_subplot(gs[3:5, 1])
    ax_3d = fig.add_subplot(gs[5:8, 1], projection="3d")

    weight_y = features.weight_instantaneous.get_y_without_NaN()
    size_y = features.size.get_y_without_NaN()
    pitch_y = features.pitch.get_y_without_NaN()

    _draw_size_weight_scatter(fig, ax_size_weight, weight_y, size_y)
    _draw_pitch_heatmap(fig, ax_pitch_heat, pitch_y)
    _draw_weight_size_pitch_3d(fig, ax_3d, weight_y, size_y, pitch_y)

    # Lock the 3D axis limits so the rotation doesn't cause auto-scaling
    if weight_y.size > 0:
        ax_3d.set_xlim(weight_y.min(), weight_y.max())
        ax_3d.set_ylim(size_y.min(), size_y.max())
    ax_3d.set_zlim(0, 450)

    fig.suptitle(f"{title} (Rotating)")

    # The update function called for each frame
    def update(frame):
        ax_3d.view_init(elev=30, azim=frame)
        return fig,

    # Generate frames from 0 to 360 degrees, stepping by 36 degrees
    frames = np.arange(0, 360, 36)

    # interval=500 means 500 milliseconds per frame
    ani = animation.FuncAnimation(fig, update, frames=frames, interval=500)

    # Save the animation using the Pillow writer
    ani.save(out_path, writer='pillow', dpi=100)
    print(f"  [Animation] Saved combined rotating GIF to {out_path.name}")


def create_summary_rotating_gif(
        all_weight: np.ndarray, all_size: np.ndarray, all_pitch: np.ndarray, out_path: Path, title: str
) -> None:
    """
    Creates a summary figure saved as a rotating GIF.
    The 3D plot rotates 36 degrees per frame (500ms per frame).
    """
    import matplotlib.animation as animation

    fig = Figure(figsize=(16, 5.5))
    FigureCanvasAgg(fig)

    # Disable constrained_layout and set manual margins to prevent shifting
    fig.subplots_adjust(left=0.05, right=0.95, bottom=0.15, top=0.85, wspace=0.3)

    ax_scatter = fig.add_subplot(1, 3, 1)
    ax_heat = fig.add_subplot(1, 3, 2)
    ax_3d = fig.add_subplot(1, 3, 3, projection="3d")

    _draw_size_weight_scatter(fig, ax_scatter, all_weight, all_size)
    _draw_pitch_heatmap(fig, ax_heat, all_pitch)
    _draw_weight_size_pitch_3d(fig, ax_3d, all_weight, all_size, all_pitch)

    # Lock the 3D axis limits so the rotation doesn't cause auto-scaling
    if all_weight.size > 0:
        ax_3d.set_xlim(all_weight.min(), all_weight.max())
        ax_3d.set_ylim(all_size.min(), all_size.max())
    ax_3d.set_zlim(0, 450)

    fig.suptitle(f"{title} (Rotating)")

    # The update function called for each frame
    def update(frame):
        ax_3d.view_init(elev=30, azim=frame)
        return fig,

    # Generate frames from 0 to 360 degrees, stepping by 36 degrees
    frames = np.arange(0, 360, 36)

    # interval=500 means 500 milliseconds per frame
    ani = animation.FuncAnimation(fig, update, frames=frames, interval=500)

    # Save the animation
    ani.save(out_path, writer='pillow', dpi=100)
    print(f"  [Animation] Saved summary rotating GIF to {out_path.name}")

def plot_combined_figure(features: AudioFeatures, out_path: Path, title: str) -> None:
    """
    Single combined figure per file:
      Left column (3 rows):  pitch vs time / weight vs time / size vs time
      Right column: size-vs-weight density scatter (spans 3 rows, square)
                    on top, pitch density heatmap (2 rows), then a 3D
                    weight/size/pitch density scatter (3 rows) below
    """
    fig = Figure(figsize=(14, 13), constrained_layout=True)
    FigureCanvasAgg(fig)  # attach an Agg canvas so fig.savefig() works
    gs = fig.add_gridspec(8, 2, width_ratios=[1.3, 1])

    ax_pitch_t = fig.add_subplot(gs[0:3, 0])
    ax_weight_t = fig.add_subplot(gs[3:6, 0], sharex=ax_pitch_t)
    ax_size_t = fig.add_subplot(gs[6:8, 0], sharex=ax_pitch_t)

    _draw_timeseries(ax_pitch_t, features.pitch, "Pitch", PlotsSpec.pitch)
    _draw_timeseries(ax_weight_t, features.weight_instantaneous, "Weight", PlotsSpec.weight)
    _draw_timeseries(ax_size_t, features.size, "Size", PlotsSpec.size)
    ax_pitch_t.set_ylim(0, 450)
    ax_weight_t.set_ylim(0, 4)
    ax_size_t.set_ylim(0, 40)
    ax_size_t.set_xlabel("Time (s)")

    ax_size_weight = fig.add_subplot(gs[0:3, 1])
    ax_pitch_heat = fig.add_subplot(gs[3:5, 1])
    ax_3d = fig.add_subplot(gs[5:8, 1], projection="3d")

    weight_y = features.weight_instantaneous.get_y_without_NaN()
    size_y = features.size.get_y_without_NaN()
    pitch_y = features.pitch.get_y_without_NaN()

    _draw_size_weight_scatter(fig, ax_size_weight, weight_y, size_y)
    _draw_pitch_heatmap(fig, ax_pitch_heat, pitch_y)
    _draw_weight_size_pitch_3d(fig, ax_3d, weight_y, size_y, pitch_y)

    fig.suptitle(title)
    fig.savefig(out_path, dpi=300)


def plot_summary_figure(
        all_weight: np.ndarray, all_size: np.ndarray, all_pitch: np.ndarray, out_path: Path, title: str
) -> None:
    """Summary: size-vs-weight density scatter, pitch density heatmap, and 3D scatter across all files."""
    # Widened figsize to comfortably fit 3 columns
    fig = Figure(figsize=(16, 5.5), constrained_layout=True)
    FigureCanvasAgg(fig)

    ax_scatter = fig.add_subplot(1, 3, 1)
    ax_heat = fig.add_subplot(1, 3, 2)
    ax_3d = fig.add_subplot(1, 3, 3, projection="3d")

    _draw_size_weight_scatter(fig, ax_scatter, all_weight, all_size)
    _draw_pitch_heatmap(fig, ax_heat, all_pitch)
    _draw_weight_size_pitch_3d(fig, ax_3d, all_weight, all_size, all_pitch)

    # Override the default view angle with your requested 142.5 degrees around Z
    ax_3d.view_init(elev=30, azim=142.5)

    fig.suptitle(title)
    fig.savefig(out_path, dpi=150)

# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Batch vocal characteristics analysis (.wav / .mp3 files)."
    )
    parser.add_argument("root_dir", help="Directory to search recursively for audio files.")
    parser.add_argument(
        "--pattern",
        default=AUDIO_FILE_PATTERN,
        help="Regex matched against each filename. Only .wav and .mp3 files "
             "are supported by the analyzer, so this should not be widened "
             "beyond those extensions (default: %(default)r).",
    )
    parser.add_argument(
        "--out-dir",
        default="analysis_output",
        help="Directory where PNGs are written (created if missing).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = find_audio_files(args.root_dir, args.pattern)
    if not files:
        print(f"No files under {args.root_dir!r} matched pattern {args.pattern!r}.")
        return

    extractor = AudioFeatureExtractor()

    all_weight, all_size, all_pitch = [], [], []

    def analyze_and_plot(path: Path):
        """Runs entirely inside a worker thread: analysis + PNG rendering."""
        # start = time.perf_counter()

        features = extractor.analyzeFile(str(path))
        # plot_combined_figure(
        #     features,
        #     out_dir / f"{path.stem}_analysis.png",
        #     title=path.stem,
        # )

        # Generate the combined rotating GIF
        create_combined_rotating_gif(
            features,
            out_dir / f"{path.stem}_combined_rotating.gif",
            title=path.stem,
        )

        features.weight_instantaneous = features.weight_instantaneous.get_y_without_NaN()
        features.size = features.size.get_y_without_NaN()
        features.pitch = features.pitch.get_y_without_NaN()

        # elapsed = time.perf_counter() - start
        # thread_name = threading.current_thread().name
        # print(f"  [{thread_name}] finished {path.name} in {elapsed:.2f}s")

        return features

    # Both analysis and plotting run concurrently here. Plotting is safe to
    # parallelize because plot_combined_figure() builds its own Figure via
    # the matplotlib object API (Figure + FigureCanvasAgg) rather than
    # pyplot - so no global figure-manager state is shared between threads.
    with ThreadPoolExecutor(max_workers=ANALYSIS_THREADS) as executor:
        future_to_path = {executor.submit(analyze_and_plot, path): path for path in files}
        total = len(future_to_path)
        completed = 0

        for future in as_completed(future_to_path):

            # start = time.perf_counter()

            path = future_to_path[future]
            completed += 1
            try:
                features = future.result()
            except Exception as exc:  # keep the batch going if one file fails
                print(f"  [{completed}/{total}] Skipping {path} due to error: {exc}")
                continue

            print(f"[{completed}/{total}] Analyzed {path}")

            all_weight.append(features.weight_instantaneous)
            all_size.append(features.size)
            all_pitch.append(features.pitch)

    if all_weight:
        start = time.perf_counter()

        summary_weight = np.concatenate(all_weight) if all_weight else np.array([])
        summary_size = np.concatenate(all_size) if all_size else np.array([])
        summary_pitch = np.concatenate(all_pitch) if all_pitch else np.array([])

        # plot_summary_figure(
        #     summary_weight,
        #     summary_size,
        #     summary_pitch,
        #     out_dir / "00_summary.png",
        #     title=f"Summary across {len(files)} files",
        # )

        create_summary_rotating_gif(
            summary_weight,
            summary_size,
            summary_pitch,
            out_dir / "summary_rotating.gif",
            title=f"Summary across {len(files)} files",
        )

        elapsed = time.perf_counter() - start
        print(f"Post processing time for the summary image: {elapsed:.2f}s")

    print(f"Output written to {out_dir.resolve()}")


if __name__ == "__main__":
    start = time.perf_counter()

    main()

    elapsed = time.perf_counter() - start
    print(f"Total processing time: {elapsed:.2f}s")