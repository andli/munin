"""Standalone settings editor process for Munin.
Launch via: python -m munin_client.settings_editor
Runs Tk on main thread; edits face labels & colors and saves config atomically.
"""
import sys
import tkinter as tk
from tkinter import colorchooser, messagebox
from typing import Dict

from munin_client.config import MuninConfig
from munin_client.logger import MuninLogger

logger = MuninLogger()


class SettingsEditor:
    def __init__(self):
        self.config = MuninConfig()
        self.root = tk.Tk()
        self.root.title("Munin Settings")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.color_vars: Dict[int, tk.StringVar] = {}
        self.label_vars: Dict[int, tk.StringVar] = {}
        self.swatches: Dict[int, tk.Label] = {}
        self.entries = {}
        self.MAX_LABEL_LENGTH = 24

        tk.Label(self.root, text="Face Settings", font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=6, pady=(8, 4))
        tk.Label(self.root, text="Face").grid(row=1, column=0, sticky="w")
        tk.Label(self.root, text="Label").grid(row=1, column=1, sticky="w")
        tk.Label(self.root, text="Color (#RRGGBB)").grid(row=1, column=2, sticky="w")
        tk.Label(self.root, text="Preview").grid(row=1, column=3, sticky="w")

        faces = range(1, 7)
        row = 2
        for face in faces:
            label = self.config.get_face_label(face)
            color = self.config.get_face_color(face)
            tk.Label(self.root, text=str(face)).grid(row=row, column=0, sticky="w", padx=4)

            label_var = tk.StringVar(value=label)
            self.label_vars[face] = label_var
            label_entry = tk.Entry(self.root, textvariable=label_var, width=14)
            label_entry.grid(row=row, column=1, padx=4, pady=2, sticky="w")

            color_hex = f"#{color['r']:02X}{color['g']:02X}{color['b']:02X}"
            var = tk.StringVar(value=color_hex)
            self.color_vars[face] = var
            entry = tk.Entry(self.root, textvariable=var, width=10)
            entry.grid(row=row, column=2, padx=4, pady=2, sticky="w")
            self.entries[face] = entry

            swatch = tk.Label(self.root, text="", width=4, relief="groove")
            swatch.grid(row=row, column=3, padx=4, pady=2, sticky="w")
            self.swatches[face] = swatch
            self._update_swatch(face)
            var.trace_add('write', lambda *_args, f=face: self._update_swatch(f))

            btn = tk.Button(self.root, text="Pick", command=lambda f=face: self._pick_color(f))
            btn.grid(row=row, column=4, padx=4)
            row += 1

        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=row, column=0, columnspan=6, pady=8)
        tk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Set all to color…", command=self._set_all_to_color).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="All Red", command=self._set_all_red).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Reset to defaults", command=self._reset_to_defaults).pack(side=tk.LEFT, padx=12)
        tk.Button(btn_frame, text="Cancel", command=self._on_close).pack(side=tk.LEFT, padx=4)

    def _reset_to_defaults(self):
        """Reset all face labels and colors to defaults and save immediately (no prompts)."""

        defaults_labels = self.config.default_config.get("face_labels", {})
        defaults_colors = self.config.default_config.get("face_colors", {})
        for face in range(1, 7):
            # Labels
            default_label = defaults_labels.get(str(face), f"Face {face}")
            if face in self.label_vars:
                self.label_vars[face].set(default_label)

            # Colors
            dc = defaults_colors.get(str(face), {"r": 128, "g": 128, "b": 128})
            hex_color = f"#{dc['r']:02X}{dc['g']:02X}{dc['b']:02X}"
            if face in self.color_vars:
                self.color_vars[face].set(hex_color)

        # Auto-save without closing
        self._save_impl(close_window=False, quiet=True)

    def _set_all_to_color(self):
        """Pick a color once, apply to all faces, and save immediately (no prompts)."""
        try:
            _rgb_tuple, hex_color = colorchooser.askcolor(color="#FF0000", title="Pick color for all faces")
            if not hex_color:
                return
            hex_color = hex_color.upper()
            # Basic validation
            if not (hex_color.startswith('#') and len(hex_color) == 7):
                messagebox.showerror("Invalid Color", f"'{hex_color}' is not #RRGGBB")
                return
            for face in range(1, 7):
                self.color_vars[face].set(hex_color)
            # Auto-save without closing
            self._save_impl(close_window=False, quiet=True)
        except Exception as e:
            logger.log_event(f"All-to-color picker error: {e}")

    def _set_all_red(self):
        """Quick action: set all faces to pure red and save immediately (no prompts)."""
        try:
            for face in range(1, 7):
                self.color_vars[face].set("#FF0000")
            # Auto-save without closing
            self._save_impl(close_window=False, quiet=True)
        except Exception as e:
            logger.log_event(f"All-red apply error: {e}")

    def _pick_color(self, face: int):
        try:
            initial = self.color_vars[face].get()
            _rgb_tuple, hex_color = colorchooser.askcolor(color=initial, title=f"Pick color for Face {face}")
            if hex_color:
                self.color_vars[face].set(hex_color.upper())
        except Exception as e:
            logger.log_event(f"Color picker error: {e}")

    def _update_swatch(self, face: int):
        """Update the color preview swatch for a face."""
        val = self.color_vars[face].get().strip()
        if val.startswith('#') and len(val) == 7:
            try:
                int(val[1:], 16)
                r = int(val[1:3], 16)
                g = int(val[3:5], 16)
                b = int(val[5:7], 16)
                hex_color = f"#{r:02X}{g:02X}{b:02X}"
                self.swatches[face].configure(bg=hex_color)
                luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
                fg = '#000000' if luminance > 140 else '#FFFFFF'
                self.swatches[face].configure(fg=fg, text='')
            except ValueError:
                self.swatches[face].configure(bg=self.root.cget('bg'), text='')
        else:
            self.swatches[face].configure(bg=self.root.cget('bg'), text='')

    def _save(self):
        self._save_impl(close_window=True, quiet=False)

    def _save_impl(self, close_window: bool = True, quiet: bool = False):
        color_updates = 0
        label_updates = 0

        # Validate labels first
        for face, label_var in self.label_vars.items():
            label_val = label_var.get().strip()
            if not label_val:
                messagebox.showerror("Invalid Label", f"Face {face}: label cannot be empty")
                return
            if len(label_val) > self.MAX_LABEL_LENGTH:
                messagebox.showerror(
                    "Invalid Label", f"Face {face}: label too long (max {self.MAX_LABEL_LENGTH} chars)"
                )
                return

        # Prepare a single config update to minimize file writes
        cfg = self.config.load_config().copy()
        if "face_labels" not in cfg:
            cfg["face_labels"] = {}
        if "face_colors" not in cfg:
            cfg["face_colors"] = {}

        for face, var in self.color_vars.items():
            # Labels
            label_val = self.label_vars[face].get().strip()
            current_label = cfg.get("face_labels", {}).get(str(face), self.config.get_face_label(face))
            if label_val != current_label:
                cfg["face_labels"][str(face)] = label_val
                label_updates += 1

            # Colors
            val = var.get().strip()
            if not val.startswith('#') or len(val) != 7:
                messagebox.showerror("Invalid Color", f"Face {face}: '{val}' is not #RRGGBB")
                return
            try:
                r = int(val[1:3], 16)
                g = int(val[3:5], 16)
                b = int(val[5:7], 16)
            except ValueError:
                messagebox.showerror("Invalid Color", f"Face {face}: '{val}' parse error")
                return
            current = cfg.get("face_colors", {}).get(str(face), self.config.get_face_color(face))
            if current['r'] != r or current['g'] != g or current['b'] != b:
                cfg["face_colors"][str(face)] = {"r": r, "g": g, "b": b}
                color_updates += 1

        # Save once if there were any updates
        if color_updates or label_updates:
            self.config.save_config(cfg)

        if not quiet:
            if color_updates or label_updates:
                if color_updates and label_updates:
                    logger.log_event(f"Updated {label_updates} label(s), {color_updates} color(s)")
                elif label_updates:
                    logger.log_event(f"Updated {label_updates} label(s)")
                else:
                    logger.log_event(f"Updated {color_updates} color(s)")
            else:
                logger.log_event("No changes detected")
        if close_window:
            self._on_close()

    def _on_close(self):
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    try:
        SettingsEditor().run()
    except Exception as e:
        logger.log_event(f"Settings editor crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
