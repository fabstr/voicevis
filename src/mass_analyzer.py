#!/usr/bin/env python3
"""
Vocal characteristics batch-analysis pipeline.

Walks a directory tree, finds .wav and .mp3 audio files, and - for each one,
concurrently across a thread pool - analyzes it with AudioFeatureExtractor
and renders combined PNGs and rotating GIFs.

Then summary images and GIFs are produced, aggregating the data across every
analyzed file.
"""

import os
import re
import time
import argparse
from pathlib import Path
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import matplotlib

matplotlib.use("Agg")  # safe for headless / batch use
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (registers the '3d' projection)
import matplotlib.animation as animation
from scipy.stats import gaussian_kde

from signal_processing.AudioFeatureExtractor import AudioFeatureExtractor
from signal_processing.AudioFeatures import AudioFeatures, SignalTimeSeries
import PlotsSpec

SCATTER_POINT_SIZE = 1

SCATTER_KW = dict(s=SCATTER_POINT_SIZE, alpha=0.6, edgecolors="none")  # points only, no lines

# Only .wav and .mp3 files are supported.
AUDIO_FILE_PATTERN = r"\.(wav|mp3)$"

# Number of worker threads used to run AudioFeatureExtractor.analyzeFile()
# concurrently across files.
ANALYSIS_THREADS = 12



# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

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
# Plotting Helpers
# ---------------------------------------------------------------------------

SCATTER_KW = dict(s=8, alpha=0.6, edgecolors="none")  # points only, no lines


def _draw_timeseries(ax, ts: SignalTimeSeries, label: str, color: str) -> None:
    x = ts.get_x_without_NaN()
    y = ts.get_y_without_NaN()
    ax.scatter(x, y, color=color, **SCATTER_KW)
    ax.set_ylabel(label)
    ax.grid(True, alpha=0.3)


def _draw_size_weight_scatter(
        fig, ax, weight_vals: np.ndarray, size_vals: np.ndarray, loudness_vals: np.ndarray
) -> None:
    n = min(weight_vals.size, size_vals.size, loudness_vals.size)
    x, y, c = weight_vals[:n], size_vals[:n], loudness_vals[:n]

    if x.size > 0:
        # Sort by loudness so the loudest points are rendered on top
        order = np.argsort(c)
        x_s, y_s, c_s = x[order], y[order], c[order]
        sc = ax.scatter(x_s, y_s, c=c_s, cmap="viridis", s=SCATTER_POINT_SIZE, alpha=0.8, edgecolors="none")
        fig.colorbar(sc, ax=ax, label="Loudness", fraction=0.046, pad=0.04)

    ax.set_xlabel("Weight")
    ax.set_ylabel("Size")
    ax.set_title("Size vs Weight (Loudness)")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 4)
    ax.set_ylim(0, 40)


def _draw_pitch_loudness_scatter(fig, ax, pitch_vals: np.ndarray, loudness_vals: np.ndarray) -> None:
    n = min(pitch_vals.size, loudness_vals.size)
    x, c = pitch_vals[:n], loudness_vals[:n]

    if x.size > 0:
        # Sort by loudness so the loudest points are rendered on top
        order = np.argsort(c)
        x_s, c_s = x[order], c[order]

        # Apply random vertical jitter to create a thick, visible "strip" of points
        y_s = np.random.uniform(-0.5, 0.5, size=x_s.size)

        sc = ax.scatter(x_s, y_s, c=c_s, cmap="viridis", s=SCATTER_POINT_SIZE, alpha=0.8, edgecolors="none")
        fig.colorbar(sc, ax=ax, label="Loudness", fraction=0.046, pad=0.04)

    ax.set_xlabel("Pitch (Hz)")
    ax.set_xlim(0, 450)
    ax.set_ylim(-1, 1)
    ax.set_yticks([])  # Hide the dummy y-axis ticks
    ax.set_title("Pitch (Loudness)")


def _draw_weight_size_pitch_3d(
        fig, ax, weight_vals: np.ndarray, size_vals: np.ndarray, pitch_vals: np.ndarray, loudness_vals: np.ndarray
) -> None:
    """3D scatter: weight (X), size (Y), pitch (Z), colored by loudness."""
    n = min(weight_vals.size, size_vals.size, pitch_vals.size, loudness_vals.size)
    x, y, z, c = weight_vals[:n], size_vals[:n], pitch_vals[:n], loudness_vals[:n]

    if x.size > 0:
        # Sort by loudness so the loudest points are rendered on top
        order = np.argsort(c)
        x_s, y_s, z_s, c_s = x[order], y[order], z[order], c[order]

        sc = ax.scatter(x_s, y_s, z_s, c=c_s, cmap="viridis", s=SCATTER_POINT_SIZE, alpha=0.8, edgecolors="none")
        fig.colorbar(sc, ax=ax, label="Loudness", fraction=0.046, pad=0.1, shrink=0.7)

    ax.set_xlabel("Weight")
    ax.set_ylabel("Size")
    ax.set_zlabel("Pitch")
    ax.set_zlim(0, 450)

    ax.set_title("Weight / Size / Pitch (Loudness)")
    ax.view_init(elev=30, azim=30)


# ---------------------------------------------------------------------------
# Per-File Plotting
# ---------------------------------------------------------------------------

def plot_combined_figure(features: AudioFeatures, out_path: Path, title: str) -> None:
    """Single combined static figure per file."""
    fig = Figure(figsize=(14, 13), constrained_layout=True)
    FigureCanvasAgg(fig)
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
    loudness_y = features.loudness.get_y_without_NaN()

    _draw_size_weight_scatter(fig, ax_size_weight, weight_y, size_y, loudness_y)
    _draw_pitch_loudness_scatter(fig, ax_pitch_heat, pitch_y, loudness_y)
    _draw_weight_size_pitch_3d(fig, ax_3d, weight_y, size_y, pitch_y, loudness_y)

    fig.suptitle(title)
    fig.savefig(out_path, dpi=150)


def create_combined_rotating_gif(features: AudioFeatures, out_path: Path, title: str) -> None:
    """Combined figure saved as a rotating GIF (36 degrees per frame, 500ms)."""
    fig = Figure(figsize=(14, 13))
    FigureCanvasAgg(fig)

    # hspace set to 0.5 to prevent titles and x-axis labels from overlapping
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
    loudness_y = features.loudness.get_y_without_NaN()

    _draw_size_weight_scatter(fig, ax_size_weight, weight_y, size_y, loudness_y)
    _draw_pitch_loudness_scatter(fig, ax_pitch_heat, pitch_y, loudness_y)
    _draw_weight_size_pitch_3d(fig, ax_3d, weight_y, size_y, pitch_y, loudness_y)

    if weight_y.size > 0:
        ax_3d.set_xlim(weight_y.min(), weight_y.max())
        ax_3d.set_ylim(size_y.min(), size_y.max())
    ax_3d.set_zlim(0, 450)

    fig.suptitle(f"{title} (Rotating)")

    def update(frame):
        ax_3d.view_init(elev=30, azim=frame)
        return fig,

    frames = np.arange(0, 360, 36)
    ani = animation.FuncAnimation(fig, update, frames=frames, interval=500)
    ani.save(out_path, writer='pillow', dpi=100)
    print(f"  [Animation] Saved combined rotating GIF to {out_path.name}")


# ---------------------------------------------------------------------------
# Summary Plotting
# ---------------------------------------------------------------------------

def plot_summary_figure(
        all_weight: np.ndarray, all_size: np.ndarray, all_pitch: np.ndarray, all_loudness: np.ndarray, out_path: Path,
        title: str
) -> None:
    """Summary static PNG across all files (1x3 grid)."""
    fig = Figure(figsize=(16, 5.5), constrained_layout=True)
    FigureCanvasAgg(fig)

    ax_scatter = fig.add_subplot(1, 3, 1)
    ax_heat = fig.add_subplot(1, 3, 2)
    ax_3d = fig.add_subplot(1, 3, 3, projection="3d")

    _draw_size_weight_scatter(fig, ax_scatter, all_weight, all_size, all_loudness)
    _draw_pitch_loudness_scatter(fig, ax_heat, all_pitch, all_loudness)
    _draw_weight_size_pitch_3d(fig, ax_3d, all_weight, all_size, all_pitch, all_loudness)

    ax_3d.view_init(elev=30, azim=142.5)

    fig.suptitle(title)
    fig.savefig(out_path, dpi=150)


def create_summary_rotating_gif(
        all_weight: np.ndarray, all_size: np.ndarray, all_pitch: np.ndarray, all_loudness: np.ndarray, out_path: Path,
        title: str
) -> None:
    """Summary figure saved as a rotating GIF (36 degrees per frame, 500ms)."""
    fig = Figure(figsize=(16, 5.5))
    FigureCanvasAgg(fig)

    fig.subplots_adjust(left=0.05, right=0.95, bottom=0.15, top=0.85, wspace=0.3)

    ax_scatter = fig.add_subplot(1, 3, 1)
    ax_heat = fig.add_subplot(1, 3, 2)
    ax_3d = fig.add_subplot(1, 3, 3, projection="3d")

    _draw_size_weight_scatter(fig, ax_scatter, all_weight, all_size, all_loudness)
    _draw_pitch_loudness_scatter(fig, ax_heat, all_pitch, all_loudness)
    _draw_weight_size_pitch_3d(fig, ax_3d, all_weight, all_size, all_pitch, all_loudness)

    if all_weight.size > 0:
        ax_3d.set_xlim(all_weight.min(), all_weight.max())
        ax_3d.set_ylim(all_size.min(), all_size.max())
    ax_3d.set_zlim(0, 450)

    fig.suptitle(f"{title} (Rotating)")

    def update(frame):
        ax_3d.view_init(elev=30, azim=frame)
        return fig,

    frames = np.arange(0, 360, 36)
    ani = animation.FuncAnimation(fig, update, frames=frames, interval=500)
    ani.save(out_path, writer='pillow', dpi=100)
    print(f"  [Animation] Saved summary rotating GIF to {out_path.name}")


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
        help="Directory where PNGs/GIFs are written (created if missing).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = find_audio_files(args.root_dir, args.pattern)
    if not files:
        print(f"No files under {args.root_dir!r} matched pattern {args.pattern!r}.")
        return

    extractor = AudioFeatureExtractor()

    all_weight, all_size, all_pitch, all_loudness = [], [], [], []

    def analyze_and_plot(path: Path):
        """Runs entirely inside a worker thread: analysis + rendering."""
        features = extractor.analyzeFile(str(path))

        plot_combined_figure(
            features,
            out_dir / f"{path.stem}_analysis.png",
            title=path.stem,
        )

        create_combined_rotating_gif(
            features,
            out_dir / f"{path.stem}_combined_rotating.gif",
            title=path.stem,
        )

        features.weight_instantaneous = features.weight_instantaneous.get_y_without_NaN()
        features.size = features.size.get_y_without_NaN()
        features.pitch = features.pitch.get_y_without_NaN()
        features.loudness = features.loudness.get_y_without_NaN()

        return features

    # Both analysis and plotting run concurrently here.
    with ThreadPoolExecutor(max_workers=ANALYSIS_THREADS) as executor:
        future_to_path = {executor.submit(analyze_and_plot, path): path for path in files}
        total = len(future_to_path)
        completed = 0

        for future in as_completed(future_to_path):
            path = future_to_path[future]
            completed += 1
            try:
                features = future.result()
            except Exception as exc:
                print(f"  [{completed}/{total}] Skipping {path} due to error: {exc}")
                continue

            print(f"[{completed}/{total}] Analyzed {path}")

            all_weight.append(features.weight_instantaneous)
            all_size.append(features.size)
            all_pitch.append(features.pitch)
            all_loudness.append(features.loudness)

    if all_weight:
        start = time.perf_counter()

        summary_weight = np.concatenate(all_weight) if all_weight else np.array([])
        summary_size = np.concatenate(all_size) if all_size else np.array([])
        summary_pitch = np.concatenate(all_pitch) if all_pitch else np.array([])
        summary_loudness = np.concatenate(all_loudness) if all_loudness else np.array([])

        summary_title = f"Summary across {len(files)} files"

        plot_summary_figure(
            summary_weight,
            summary_size,
            summary_pitch,
            summary_loudness,
            out_dir / "summary_size_weight_pitch.png",
            title=summary_title,
        )

        create_summary_rotating_gif(
            summary_weight,
            summary_size,
            summary_pitch,
            summary_loudness,
            out_dir / "summary_rotating.gif",
            title=summary_title,
        )

        elapsed = time.perf_counter() - start
        print(f"Summary processing time: {elapsed:.2f}s")

    print(f"Done. Output written to {out_dir.resolve()}")


if __name__ == "__main__":
    start = time.perf_counter()
    main()
    elapsed = time.perf_counter() - start
    print(f"Processing time: {elapsed:.2f}s")