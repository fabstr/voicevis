import sys
import os
import argparse
from PyQt6 import QtWidgets, QtCore
import pyqtgraph.exporters

# Import your existing UI widget class
from ui.LiveMultiPlotWidget import LiveMultiPlotWidget


class HeadlessPlotExporter(QtCore.QObject):
    def __init__(self, input_dir, output_dir, targets_file=None):
        super().__init__()
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.targets_file = targets_file

        # 1. Gather all target audio files (.wav, .mp3)
        extensions = ('.wav', '.mp3')
        self.files_to_process = [
            os.path.join(input_dir, f) for f in os.listdir(input_dir)
            if f.lower().endswith(extensions)
        ]
        self.current_index = 0

        # 2. Instantiate your widget (DO NOT call widget.show())
        self.widget = LiveMultiPlotWidget()

        # 3. If a targets file was provided, programmatically load it now
        if self.targets_file:
            self.load_target_bands()

    def load_target_bands(self):
        """Reuses your existing JSON target parsing logic cleanly."""
        if not os.path.exists(self.targets_file):
            print(f"Warning: Targets file not found at {self.targets_file}. Skipping targets.")
            return

        print(f"Loading target bands from: {self.targets_file}")
        try:
            import json
            with open(self.targets_file, 'r') as f:
                loaded_data = json.load(f)

            for plot_name, targets in loaded_data.items():
                if plot_name in self.widget.target_bands:
                    for target_name, target_data in targets.items():
                        if target_name in self.widget.target_bands[plot_name]:
                            t_obj = self.widget.target_bands[plot_name][target_name]
                            t_obj['enabled'] = target_data.get('enabled', False)
                            t_obj['min'] = target_data.get('min', 0.0)
                            t_obj['max'] = target_data.get('max', 1.0)

                            if t_obj['enabled']:
                                t_obj['item'].setRegion((t_obj['min'], t_obj['max']))
                                t_obj['item'].setVisible(True)
                            else:
                                t_obj['item'].setVisible(False)
            print("Target bands successfully loaded and applied.")
        except Exception as e:
            print(f"Error importing targets programmatically: {str(e)}")

    def start_batch(self):
        if not self.files_to_process:
            print("No audio files found to process.")
            QtWidgets.QApplication.quit()
            return

        print(f"Starting batch process for {len(self.files_to_process)} files...")
        self.process_next()

    def process_next(self):
        if self.current_index >= len(self.files_to_process):
            print("\nBatch processing completely finished!")
            QtWidgets.QApplication.quit()
            return

        file_path = self.files_to_process[self.current_index]
        self.current_base_name = os.path.splitext(os.path.basename(file_path))[0]

        print(f"\n[{self.current_index + 1}/{len(self.files_to_process)}] Analyzing: {self.current_base_name}")

        # Reset size constraints before layout updates happen
        splitter = self.widget.plot_splitter
        splitter.setMinimumSize(0, 0)
        splitter.setMaximumSize(16777215, 16777215)

        # Make sure ALL standard plots are toggled VISIBLE on the layout canvas
        ALLOWED_PLOTS = ["Pitch (Hz)", "F3 / Pitch", "F2 / Pitch", "F1 / Pitch", "Size", "Weight"]
        for plot_name in list(self.widget.plots.keys()):
            plot_spec_title = self.widget.plots[plot_name]['plot'].plotItem.titleLabel.text
            if plot_name in ALLOWED_PLOTS or plot_spec_title in ALLOWED_PLOTS:
                self.widget.handle_toggle_plot(plot_name, True)
            else:
                self.widget.handle_toggle_plot(plot_name, False)

        # Process layouts with unconstrained size
        QtWidgets.QApplication.processEvents()

        # Trigger your background processing pipeline
        self.widget.selectAnalysisFile(file_path)

        # Connect the worker's completion signal straight to our image exporter
        self.widget.worker.result_ready.connect(self.export_current_plots, QtCore.Qt.ConnectionType.UniqueConnection)

    def export_current_plots(self):
        splitter = self.widget.plot_splitter

        # HARD LOCK the geometry to exactly 1000x1000
        splitter.setFixedSize(1000, 1000)

        # Flush layout changes to ensure internal plot sizes are updated
        QtWidgets.QApplication.processEvents()
        QtWidgets.QApplication.sendPostedEvents()

        # Define consistent min/max coordinate bounds based on your data spreads
        Y_RANGES = {
            "Pitch (Hz)": (0, 350),  # Formants usually range from 0 to 4000 Hz
            "F3 / Pitch": (0, 50),  # Uniform scale covering up to your max observed pitch ratios
            "F2 / Pitch": (0, 40),
            "F1 / Pitch": (0, 15),
            "Size": (-500, 1000),
            "Weight": (0, 5e-7)  # Covers scientific notation limits cleanly
        }

        # Iterate through every plot to hide data lines, fix margins, and hard lock ranges
        for plot_name, plot_config in self.widget.plots.items():
            plot_item = plot_config['plot'].plotItem
            current_title = plot_item.titleLabel.text

            # 1. Force the left axis margin to stay identical
            left_axis = plot_item.getAxis('left')
            left_axis.setWidth(80)

            # Disable auto-ranging completely so it stops overriding our constraints
            plot_item.disableAutoRange()

            # 2. Match the plot to its strict coordinate limits
            matched_range = None
            for key, bounds in Y_RANGES.items():
                if key in plot_name or key in current_title:
                    matched_range = bounds
                    break

            if matched_range:
                # Force the exact coordinate zoom limits
                plot_item.setYRange(matched_range[0], matched_range[1], padding=0)

            # 3. Handle data visibility (skip hiding elements for the Weight plot)
            if "Weight" in plot_name or "Weight" in current_title:
                plot_item.getViewBox().update()
                continue

            if "Size" in plot_name or "Size" in current_title:
                plot_item.getViewBox().update()
                continue

            # Hide standard data curves so only the target region highlights remain
            # import pyqtgraph as pg
            # for item in plot_item.items:
            #     if isinstance(item, pg.PlotDataItem):
            #         item.setVisible(False)

            plot_item.getViewBox().update()

        # Final layout pass to bake the hardcoded zoom positions into the buffer
        QtWidgets.QApplication.processEvents()

        output_file = os.path.join(self.output_dir, f"{self.current_base_name}_plots.png")

        try:
            # Take snapshot
            pixmap = splitter.grab()
            success = pixmap.save(output_file, "PNG")

            if success:
                print(f" Saved filtered {pixmap.width()}x{pixmap.height()} plot image to: {output_file}")
            else:
                print(f" Failed to save image (Qt file write error) for {self.current_base_name}")

        except Exception as e:
            print(f" Failed to export image for {self.current_base_name}: {str(e)}")

        # Step increment and pass to the next file execution block
        self.current_index += 1
        QtCore.QTimer.singleShot(100, self.process_next)


if __name__ == '__main__':
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QtWidgets.QApplication(sys.argv)

    parser = argparse.ArgumentParser(description="PyQtGraph Headless Batch Exporter CLI")
    parser.add_argument("-i", "--input", required=True, help="Directory path containing input .wav/.mp3 files")
    parser.add_argument("-o", "--output", required=True, help="Directory path where output PNGs will save")
    parser.add_argument("-t", "--targets", required=False, default=None,
                        help="Optional path to a exported targets JSON text file")

    args, _ = parser.parse_known_args()

    if not os.path.exists(args.output):
        os.makedirs(args.output)

    exporter = HeadlessPlotExporter(args.input, args.output, args.targets)
    QtCore.QTimer.singleShot(0, exporter.start_batch)

    sys.exit(app.exec())