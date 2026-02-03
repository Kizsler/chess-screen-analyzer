"""Screen region selector for choosing the chess board area."""

import tkinter as tk
from tkinter import simpledialog
import json
import subprocess
import sys
from pathlib import Path

# Path to store selected region temporarily
TEMP_REGION_FILE = Path.home() / ".chess_watcher" / "temp_region.json"


def run_selector_gui():
    """Run the actual GUI selector - called as subprocess."""
    from PIL import Image, ImageTk, ImageGrab

    class RegionSelector:
        def __init__(self):
            self.start_x = None
            self.start_y = None
            self.rect = None
            self.region = None
            self.phase = 1  # 1 = select board, 2 = click a1 square
            self.board_region = None
            self.grid_rects = []
            self.a1_corner = None  # Will be 'bottom-left' or 'top-right' etc.

        def select(self):
            # Capture screen
            self.img = ImageGrab.grab()

            # Create fullscreen window
            self.root = tk.Tk()
            self.root.attributes("-fullscreen", True)
            self.root.attributes("-topmost", True)
            self.root.configure(cursor="cross", bg="black")

            # Canvas
            self.canvas = tk.Canvas(self.root, width=self.img.width, height=self.img.height,
                                   highlightthickness=0, bg="black")
            self.canvas.pack()

            # Show screenshot
            self.photo = ImageTk.PhotoImage(self.img)
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

            # Instructions (will be updated per phase)
            self.instruction_shadow = self.canvas.create_text(
                self.img.width//2+2, 32,
                text="Step 1: Drag to select the chess board squares",
                fill="black", font=("Arial", 18, "bold"))
            self.instruction_text = self.canvas.create_text(
                self.img.width//2, 30,
                text="Step 1: Drag to select the chess board squares",
                fill="yellow", font=("Arial", 18, "bold"))

            self.sub_instruction = self.canvas.create_text(
                self.img.width//2, 60,
                text="(Select just the 8x8 grid, not the coordinates)",
                fill="cyan", font=("Arial", 14))

            # Bindings
            self.canvas.bind("<ButtonPress-1>", self._press)
            self.canvas.bind("<B1-Motion>", self._drag)
            self.canvas.bind("<ButtonRelease-1>", self._release)
            self.root.bind("<Escape>", lambda e: self.root.destroy())

            self.root.mainloop()
            return self.region

        def _update_instructions(self, text, subtext=""):
            self.canvas.itemconfig(self.instruction_shadow, text=text)
            self.canvas.itemconfig(self.instruction_text, text=text)
            self.canvas.itemconfig(self.sub_instruction, text=subtext)

        def _press(self, e):
            if self.phase == 1:
                # Phase 1: Selecting board region
                self.start_x, self.start_y = e.x, e.y
                if self.rect:
                    self.canvas.delete(self.rect)
                self.rect = self.canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                          outline="lime", width=3)
            elif self.phase == 2:
                # Phase 2: Clicking on a1 square
                self._handle_a1_click(e.x, e.y)

        def _drag(self, e):
            if self.phase == 1 and self.rect:
                self.canvas.coords(self.rect, self.start_x, self.start_y, e.x, e.y)

        def _release(self, e):
            if self.phase == 1:
                if self.start_x is None:
                    return
                x = min(self.start_x, e.x)
                y = min(self.start_y, e.y)
                w = abs(e.x - self.start_x)
                h = abs(e.y - self.start_y)
                if w < 50 or h < 50:
                    return
                # Make it square
                size = max(w, h)
                self.board_region = {"x": int(x), "y": int(y), "width": int(size), "height": int(size)}

                # Move to phase 2
                self._start_phase_2()

        def _start_phase_2(self):
            """Start phase 2: clicking on a1 square."""
            self.phase = 2
            self._update_instructions(
                "Step 2: Click on the A1 square (bottom-left for white)",
                "(This tells us the board orientation)"
            )

            # Draw grid overlay on selected region
            x, y = self.board_region["x"], self.board_region["y"]
            size = self.board_region["width"]
            sq_size = size / 8

            # Draw grid lines
            for i in range(9):
                # Vertical lines
                lx = x + i * sq_size
                self.canvas.create_line(lx, y, lx, y + size, fill="yellow", width=1)
                # Horizontal lines
                ly = y + i * sq_size
                self.canvas.create_line(x, ly, x + size, ly, fill="yellow", width=1)

            # Highlight corners with labels
            corners = [
                (0, 7, "bottom-left"),   # Bottom-left
                (7, 7, "bottom-right"),  # Bottom-right
                (0, 0, "top-left"),      # Top-left
                (7, 0, "top-right"),     # Top-right
            ]

            self.corner_rects = {}
            for col, row, name in corners:
                cx = x + col * sq_size
                cy = y + row * sq_size
                rect = self.canvas.create_rectangle(
                    cx, cy, cx + sq_size, cy + sq_size,
                    outline="cyan", width=3, fill=""
                )
                # Add label
                label = self.canvas.create_text(
                    cx + sq_size/2, cy + sq_size/2,
                    text="a1?", fill="cyan", font=("Arial", 12, "bold")
                )
                self.corner_rects[name] = {
                    "rect": rect,
                    "label": label,
                    "col": col,
                    "row": row,
                    "x": cx,
                    "y": cy,
                    "size": sq_size
                }

        def _handle_a1_click(self, click_x, click_y):
            """Determine which corner was clicked."""
            for name, corner in self.corner_rects.items():
                cx, cy = corner["x"], corner["y"]
                sq_size = corner["size"]
                if cx <= click_x <= cx + sq_size and cy <= click_y <= cy + sq_size:
                    self.a1_corner = name
                    self._finish_selection()
                    return

            # Check if click is within board at all
            x, y = self.board_region["x"], self.board_region["y"]
            size = self.board_region["width"]
            sq_size = size / 8

            if x <= click_x <= x + size and y <= click_y <= y + size:
                # Determine which square was clicked
                col = int((click_x - x) / sq_size)
                row = int((click_y - y) / sq_size)

                # Determine corner based on click position
                if col < 4 and row >= 4:
                    self.a1_corner = "bottom-left"
                elif col >= 4 and row >= 4:
                    self.a1_corner = "bottom-right"
                elif col < 4 and row < 4:
                    self.a1_corner = "top-left"
                else:
                    self.a1_corner = "top-right"

                self._finish_selection()

        def _finish_selection(self):
            """Finalize selection with orientation."""
            # Determine if board is flipped based on a1 location
            # Standard: a1 is bottom-left (white's perspective)
            # Flipped: a1 is top-right (black's perspective)

            flipped = self.a1_corner in ["top-right", "top-left"]

            # For bottom-right or top-left, the board is rotated 90 degrees
            # which is unusual - we'll treat it as flipped for simplicity
            if self.a1_corner in ["bottom-right", "top-left"]:
                flipped = True

            self.region = {
                "x": self.board_region["x"],
                "y": self.board_region["y"],
                "width": self.board_region["width"],
                "height": self.board_region["height"],
                "a1_corner": self.a1_corner,
                "flipped": flipped
            }
            self.root.destroy()

    selector = RegionSelector()
    region = selector.select()

    # Save result
    TEMP_REGION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TEMP_REGION_FILE, "w") as f:
        json.dump(region, f)

    return region


def select_board_region(parent=None):
    """Launch selector as subprocess to avoid tkinter conflicts."""
    # Run this script as a subprocess
    result = subprocess.run(
        [sys.executable, __file__, "--gui"],
        capture_output=True,
        text=True
    )

    # Read result from temp file
    if TEMP_REGION_FILE.exists():
        with open(TEMP_REGION_FILE, "r") as f:
            region = json.load(f)
        TEMP_REGION_FILE.unlink()  # Clean up
        return region
    return None


if __name__ == "__main__":
    if "--gui" in sys.argv:
        # Running as subprocess - do the actual GUI
        run_selector_gui()
    else:
        # Test mode
        region = select_board_region()
        print(f"Selected: {region}")
