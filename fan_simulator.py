"""
fan_simulator.py — VoxEdge: Tkinter GUI that simulates a fan.

This module provides a FanSimulator class with three visual states:
  • FAN: OFF  — grey background (default)
  • FAN: ON   — green background with a spinning fan blade animation
  • ACCESS DENIED — red background

No real hardware is used; this is purely a GUI demonstration.
"""

import math       # for sin/cos used to draw the fan blades
import tkinter as tk
from tkinter import font as tkfont


class FanSimulator:
    """A Tkinter window that acts as the simulated fan output device."""

    # How fast the fan blades spin (degrees per animation frame)
    _SPIN_STEP   = 6      # degrees added per tick
    _SPIN_DELAY  = 30     # milliseconds between frames (~33 fps)
    _BLADE_COUNT = 4      # number of fan blades
    _RADIUS      = 80     # blade tip distance from centre (pixels)

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("VoxEdge — Fan Simulator")
        self.root.geometry("480x360")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")  # dark background for aesthetics

        # ── Title banner ─────────────────────────────────────────────────────
        title_label = tk.Label(
            self.root,
            text="⚙  VoxEdge Fan Simulator",
            bg="#1e1e2e",
            fg="#cdd6f4",
            font=("Helvetica", 14, "bold"),
            pady=8,
        )
        title_label.pack(fill="x")

        # ── Fan canvas (where the blades are drawn) ───────────────────────────
        self._canvas = tk.Canvas(
            self.root,
            width=200,
            height=200,
            bg="#313244",      # slightly lighter dark panel
            highlightthickness=0,
        )
        self._canvas.pack(pady=(0, 8))
        self._cx = 100   # canvas centre x
        self._cy = 100   # canvas centre y
        self._angle = 0  # current rotation angle (degrees)
        self._spinning = False
        self._after_id = None  # handle for the scheduled animation callback

        # Draw the fan in its initial stopped state
        self._draw_fan(color="#6c7086")  # grey blades = off

        # ── Status label (large text showing state) ───────────────────────────
        self._status_label = tk.Label(
            self.root,
            text="FAN: OFF",
            bg="#45475a",       # muted grey
            fg="#ffffff",
            font=("Helvetica", 28, "bold"),
            pady=12,
        )
        self._status_label.pack(fill="x", padx=20, pady=(0, 16))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _draw_fan(self, color: str = "#89b4fa") -> None:
        """Redraw all fan blades at the current self._angle."""
        self._canvas.delete("blade")  # remove the previous frame's blades

        for i in range(self._BLADE_COUNT):
            # Evenly space blades around the circle
            angle_rad = math.radians(self._angle + i * (360 / self._BLADE_COUNT))

            # Tip point of this blade
            tip_x = self._cx + self._RADIUS * math.cos(angle_rad)
            tip_y = self._cy + self._RADIUS * math.sin(angle_rad)

            # Two base points to give each blade a triangular shape
            base_angle_a = math.radians(self._angle + i * (360 / self._BLADE_COUNT) + 25)
            base_angle_b = math.radians(self._angle + i * (360 / self._BLADE_COUNT) - 25)
            base_r = 20  # how wide the blade root is

            bax = self._cx + base_r * math.cos(base_angle_a)
            bay = self._cy + base_r * math.sin(base_angle_a)
            bbx = self._cx + base_r * math.cos(base_angle_b)
            bby = self._cy + base_r * math.sin(base_angle_b)

            self._canvas.create_polygon(
                tip_x, tip_y, bax, bay, bbx, bby,
                fill=color, outline="#1e1e2e", width=2,
                tags="blade",
            )

        # Draw the hub (centre circle) on top
        hub_r = 12
        self._canvas.create_oval(
            self._cx - hub_r, self._cy - hub_r,
            self._cx + hub_r, self._cy + hub_r,
            fill="#1e1e2e", outline="#cdd6f4", width=2,
        )

    def _animate(self) -> None:
        """One frame of the spin animation — called repeatedly while ON."""
        if not self._spinning:
            return
        self._angle = (self._angle + self._SPIN_STEP) % 360
        self._draw_fan(color="#a6e3a1")   # green blades while spinning
        self._after_id = self.root.after(self._SPIN_DELAY, self._animate)

    def _stop_animation(self) -> None:
        """Cancel any running animation callback."""
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self._spinning = False

    # ── Public state methods (called from main.py via root.after) ─────────────

    def turn_on(self) -> None:
        """Switch to the ON state: green label + spinning blades."""
        self._canvas.configure(bg="#1e3a2e")   # dark green canvas background
        self._status_label.config(text="FAN: ON", bg="#40a02b", fg="#ffffff")
        if not self._spinning:
            self._spinning = True
            self._animate()  # kick off the animation loop

    def turn_off(self) -> None:
        """Switch to the OFF state: grey label + still blades."""
        self._stop_animation()
        self._canvas.configure(bg="#313244")
        self._draw_fan(color="#6c7086")        # grey, static blades
        self._status_label.config(text="FAN: OFF", bg="#45475a", fg="#ffffff")

    def access_denied(self) -> None:
        """Switch to the ACCESS DENIED state: red label + still blades."""
        self._stop_animation()
        self._canvas.configure(bg="#3a1e1e")   # dark red canvas background
        self._draw_fan(color="#f38ba8")        # red-tinted blades
        self._status_label.config(text="ACCESS DENIED", bg="#d20f39", fg="#ffffff")

    def run(self) -> None:
        """Start the Tkinter event loop (blocks until the window is closed)."""
        self.root.mainloop()