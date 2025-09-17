import threading
import tkinter as tk
from tkinter import colorchooser, messagebox
from typing import Dict

from munin_client.config import MuninConfig
from munin_client.logger import MuninLogger
from munin_client.ble_manager import BLEDeviceManager

logger = MuninLogger()

class SettingsWindow:
    """Simple Tkinter window for editing face colors."""

    _instance = None  # Singleton (avoid multiple windows)

    @classmethod
    def open(cls, ble_manager: BLEDeviceManager):
        # Run in separate thread so pystray event loop (main thread) is not blocked
        if cls._instance and cls._instance.root and tk.Toplevel.winfo_exists(cls._instance.root):
            try:
                cls._instance.root.lift()
                return
            except Exception:
                pass
        def _run():
            try:
                SettingsWindow(ble_manager)
            except Exception as e:
                logger.log_event(f"Error launching settings window: {e}")
        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def __init__(self, ble_manager: BLEDeviceManager):
        self.ble_manager = ble_manager
        self.config = MuninConfig()
        self.root = tk.Tk()
        self.root.title("Munin Settings")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.color_vars: Dict[int, tk.StringVar] = {}

        tk.Label(self.root, text="Face Colors", font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=4, pady=(8,4))
        tk.Label(self.root, text="Face").grid(row=1, column=0, sticky="w")
        tk.Label(self.root, text="Label").grid(row=1, column=1, sticky="w")
        tk.Label(self.root, text="Color (RGB)").grid(row=1, column=2, sticky="w")

        faces = range(1,7)
        row = 2
        self.entries = {}
        for face in faces:
            label = self.config.get_face_label(face)
            color = self.config.get_face_color(face)
            tk.Label(self.root, text=str(face)).grid(row=row, column=0, sticky="w", padx=4)
            tk.Label(self.root, text=label).grid(row=row, column=1, sticky="w")
            color_hex = f"#{color['r']:02X}{color['g']:02X}{color['b']:02X}"
            var = tk.StringVar(value=color_hex)
            self.color_vars[face] = var
            entry = tk.Entry(self.root, textvariable=var, width=10)
            entry.grid(row=row, column=2, padx=4, pady=2)
            self.entries[face] = entry
            btn = tk.Button(self.root, text="Pick", command=lambda f=face: self._pick_color(f))
            btn.grid(row=row, column=3, padx=4)
            row += 1

        btn_frame = tk.Frame(self.root)
        btn_frame.grid(row=row, column=0, columnspan=4, pady=8)
        tk.Button(btn_frame, text="Save", command=self._save).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="Cancel", command=self._on_close).pack(side=tk.LEFT, padx=4)

        # Non-blocking mainloop (periodic check to keep window responsive in thread)
        self._tick()
        self.root.mainloop()

    def _tick(self):
        if self.root.winfo_exists():
            self.root.after(250, self._tick)

    def _pick_color(self, face: int):
        try:
            initial = self.color_vars[face].get()
            rgb_tuple, hex_color = colorchooser.askcolor(color=initial, title=f"Pick color for Face {face}")
            if hex_color:
                self.color_vars[face].set(hex_color.upper())
        except Exception as e:
            logger.log_event(f"Color picker error: {e}")

    def _save(self):
        # Validate and persist colors
        updated = 0
        for face, var in self.color_vars.items():
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
            # Only write if changed
            current = self.config.get_face_color(face)
            if current['r'] != r or current['g'] != g or current['b'] != b:
                self.config.set_face_color(str(face), r, g, b)
                updated += 1
        if updated:
            logger.log_event(f"Updated {updated} face color(s)")
            # Push new colors to device if connected
            try:
                if self.ble_manager and self.ble_manager.is_connected():
                    self.ble_manager.send_face_colors_to_device()
                    logger.log_event("Sent face color configuration to device (settings window)")
            except Exception as e:
                logger.log_event(f"Failed to push colors to device: {e}")
        else:
            logger.log_event("No color changes detected")
        self._on_close()

    def _on_close(self):
        try:
            if self.root and self.root.winfo_exists():
                self.root.destroy()
        except Exception:
            pass
        SettingsWindow._instance = None

__all__ = ["SettingsWindow"]
