"""Chess Screen Watcher - Main Application."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import sys
from pathlib import Path

from config import load_config, save_config, find_stockfish
from region_selector import select_board_region
from screen_capture import ScreenCapture
from board_detector import BoardDetector, board_to_fen, validate_fen
from analyzer import ChessAnalyzer, ensure_stockfish, download_stockfish


class ChessWatcherApp:
    """Main application window."""

    def __init__(self):
        self.config = load_config()
        self.running = False
        self.capture = None
        self.detector = BoardDetector()
        self.analyzer = None
        self.current_fen = None
        self.watch_thread = None

        self._setup_ui()
        self._check_stockfish()

    def _setup_ui(self):
        """Setup the main window."""
        self.root = tk.Tk()
        self.root.title("Chess Watcher")
        self.root.geometry("350x650")
        self.root.resizable(True, True)
        self.root.attributes("-topmost", True)

        # Main frame
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Status section
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding=5)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_label = ttk.Label(status_frame, text="Not watching", foreground="gray")
        self.status_label.pack()

        # Best move section
        move_frame = ttk.LabelFrame(main_frame, text="Best Move", padding=10)
        move_frame.pack(fill=tk.X, pady=(0, 10))

        self.move_label = ttk.Label(
            move_frame,
            text="--",
            font=("Arial", 28, "bold"),
            foreground="#2e7d32"
        )
        self.move_label.pack()

        self.turn_label = ttk.Label(move_frame, text="", font=("Arial", 10))
        self.turn_label.pack()

        # Evaluation section
        eval_frame = ttk.LabelFrame(main_frame, text="Evaluation", padding=5)
        eval_frame.pack(fill=tk.X, pady=(0, 10))

        self.eval_label = ttk.Label(eval_frame, text="0.00", font=("Arial", 16))
        self.eval_label.pack()

        # Eval bar
        self.eval_canvas = tk.Canvas(eval_frame, height=20, bg="white", highlightthickness=1)
        self.eval_canvas.pack(fill=tk.X, pady=5)
        self._draw_eval_bar(0)

        # Line (principal variation)
        self.pv_label = ttk.Label(eval_frame, text="", font=("Arial", 9), wraplength=280)
        self.pv_label.pack()

        # Detected Position section
        pos_frame = ttk.LabelFrame(main_frame, text="Detected Position", padding=5)
        pos_frame.pack(fill=tk.X, pady=(0, 10))

        self.fen_display = ttk.Label(pos_frame, text="No position detected", font=("Consolas", 8), wraplength=280)
        self.fen_display.pack(fill=tk.X)

        # Legal moves section
        moves_frame = ttk.LabelFrame(main_frame, text="Legal Moves", padding=5)
        moves_frame.pack(fill=tk.X, pady=(0, 10))

        self.moves_label = ttk.Label(moves_frame, text="--", font=("Consolas", 9), wraplength=280)
        self.moves_label.pack(fill=tk.X)

        # Control buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        self.select_btn = ttk.Button(btn_frame, text="Select Board", command=self._select_board)
        self.select_btn.pack(side=tk.LEFT, padx=2)

        self.watch_btn = ttk.Button(btn_frame, text="Start Watching", command=self._toggle_watch)
        self.watch_btn.pack(side=tk.LEFT, padx=2)

        self.debug_btn = ttk.Button(btn_frame, text="Debug", command=self._save_debug)
        self.debug_btn.pack(side=tk.LEFT, padx=2)

        # Manual FEN input
        fen_frame = ttk.LabelFrame(main_frame, text="Manual FEN (paste here)", padding=5)
        fen_frame.pack(fill=tk.X, pady=(0, 10))

        self.fen_entry = ttk.Entry(fen_frame, width=40)
        self.fen_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.analyze_btn = ttk.Button(fen_frame, text="Analyze", command=self._analyze_manual_fen)
        self.analyze_btn.pack(side=tk.LEFT, padx=5)

        # Settings
        settings_frame = ttk.LabelFrame(main_frame, text="Settings", padding=5)
        settings_frame.pack(fill=tk.X, pady=(0, 10))

        # Board orientation
        orient_frame = ttk.Frame(settings_frame)
        orient_frame.pack(fill=tk.X)

        ttk.Label(orient_frame, text="Playing as:").pack(side=tk.LEFT)
        self.color_var = tk.StringVar(value="white")
        ttk.Radiobutton(orient_frame, text="White", variable=self.color_var, value="white",
                        command=self._on_color_change).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(orient_frame, text="Black", variable=self.color_var, value="black",
                        command=self._on_color_change).pack(side=tk.LEFT)

        # Depth slider
        depth_frame = ttk.Frame(settings_frame)
        depth_frame.pack(fill=tk.X, pady=5)

        ttk.Label(depth_frame, text="Analysis depth:").pack(side=tk.LEFT)
        self.depth_var = tk.IntVar(value=self.config.get("analysis_depth", 15))
        depth_spin = ttk.Spinbox(depth_frame, from_=5, to=25, width=5, textvariable=self.depth_var)
        depth_spin.pack(side=tk.LEFT, padx=5)

        # Board region indicator
        region = self.config.get("board_region")
        if region:
            self.status_label.config(text="Board selected. Click Start Watching.", foreground="blue")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _check_stockfish(self):
        """Check if Stockfish is available."""
        path = find_stockfish()
        if not path:
            result = messagebox.askyesno(
                "Stockfish Not Found",
                "Stockfish chess engine is required.\n\nDownload it now? (~30MB)"
            )
            if result:
                self._download_stockfish()
            else:
                messagebox.showinfo(
                    "Manual Installation",
                    "Please download Stockfish from:\nhttps://stockfishchess.org/download/\n\n"
                    "Then place the .exe file in:\nC:\\stockfish\\stockfish.exe"
                )

    def _download_stockfish(self):
        """Download Stockfish with progress dialog."""
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Downloading Stockfish")
        progress_win.geometry("300x100")
        progress_win.transient(self.root)
        progress_win.grab_set()

        ttk.Label(progress_win, text="Downloading Stockfish...").pack(pady=10)
        progress = ttk.Progressbar(progress_win, length=250, mode='determinate')
        progress.pack(pady=10)
        status = ttk.Label(progress_win, text="")
        status.pack()

        def update_progress(downloaded, total):
            if total > 0:
                pct = (downloaded / total) * 100
                progress['value'] = pct
                status.config(text=f"{downloaded // 1024} / {total // 1024} KB")
                progress_win.update()

        def do_download():
            path = download_stockfish(update_progress)
            progress_win.destroy()
            if path:
                messagebox.showinfo("Success", "Stockfish downloaded successfully!")
            else:
                messagebox.showerror("Error", "Failed to download Stockfish.")

        threading.Thread(target=do_download, daemon=True).start()

    def _draw_eval_bar(self, eval_cp):
        """Draw the evaluation bar."""
        self.eval_canvas.delete("all")
        width = self.eval_canvas.winfo_width() or 280
        height = 20

        # Convert centipawns to percentage (clamp at +/- 10 pawns)
        clamped = max(-1000, min(1000, eval_cp))
        white_pct = (clamped + 1000) / 2000  # 0 to 1

        white_width = int(width * white_pct)

        # Draw black side
        self.eval_canvas.create_rectangle(0, 0, width, height, fill="#333333", outline="")
        # Draw white side
        self.eval_canvas.create_rectangle(0, 0, white_width, height, fill="#f5f5f5", outline="")
        # Center line
        self.eval_canvas.create_line(width // 2, 0, width // 2, height, fill="gray")

    def _select_board(self):
        """Open region selector."""
        self.root.withdraw()
        time.sleep(0.3)  # Let window hide

        region = select_board_region()

        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        if region:
            self.config["board_region"] = region
            save_config(self.config)
            self.status_label.config(text="Board selected! Click Start Watching.", foreground="blue")
            messagebox.showinfo("Success", f"Board region saved!\n\nPosition: ({region['x']}, {region['y']})\nSize: {region['width']}x{region['height']}")
        else:
            messagebox.showwarning("Cancelled", "Board selection cancelled.")

    def _on_color_change(self):
        """Handle color selection change."""
        is_black = self.color_var.get() == "black"
        self.config["board_flipped"] = is_black
        save_config(self.config)
        self.detector.flipped = is_black

    def _toggle_watch(self):
        """Start or stop watching."""
        if self.running:
            self._stop_watching()
        else:
            self._start_watching()

    def _start_watching(self):
        """Start the screen watching loop."""
        region = self.config.get("board_region")
        if not region:
            messagebox.showwarning("No Board Selected", "Please select the board region first.")
            return

        stockfish_path = find_stockfish()
        if not stockfish_path:
            messagebox.showerror("No Engine", "Stockfish not found. Please install it first.")
            return

        self.running = True
        self.watch_btn.config(text="Stop Watching")
        self.select_btn.config(state=tk.DISABLED)
        self.status_label.config(text="Watching...", foreground="green")

        # Initialize components
        self.capture = ScreenCapture(region)
        self.detector = BoardDetector(flipped=self.config.get("board_flipped", False))
        self.analyzer = ChessAnalyzer(stockfish_path, depth=self.depth_var.get())
        self.analyzer.start()

        # Start watch thread
        self.watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.watch_thread.start()

    def _stop_watching(self):
        """Stop the watching loop."""
        self.running = False
        self.watch_btn.config(text="Start Watching")
        self.select_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Stopped", foreground="gray")

        if self.analyzer:
            self.analyzer.stop()
            self.analyzer = None

        if self.capture:
            self.capture.close()
            self.capture = None

    def _watch_loop(self):
        """Main watching loop (runs in thread)."""
        interval = self.config.get("capture_interval_ms", 500) / 1000.0

        while self.running:
            try:
                # Capture screen
                img, changed = self.capture.capture_if_changed()

                if changed:
                    # Detect board
                    board = self.detector.detect(img)

                    # Determine turn (alternate based on previous, or default to white)
                    turn = 'w'
                    if self.current_fen:
                        # Simple heuristic: if position changed, it's the other side's turn
                        prev_turn = self.current_fen.split()[1]
                        turn = 'b' if prev_turn == 'w' else 'w'

                    fen = board_to_fen(board, flipped=self.config.get("board_flipped", False), turn=turn)

                    # Validate FEN before analyzing
                    if not validate_fen(fen):
                        self._update_status("Detection error - adjust selection")
                        continue

                    # Only analyze if position changed significantly
                    if fen != self.current_fen:
                        self.current_fen = fen
                        self._update_status("Analyzing...")

                        # Analyze position
                        result = self.analyzer.analyze(fen, depth=self.depth_var.get())

                        # Update UI
                        self._update_ui(result)

            except Exception as e:
                self._update_status(f"Error: {str(e)[:30]}")

            time.sleep(interval)

    def _update_ui(self, result):
        """Update UI with analysis result (thread-safe)."""
        def update():
            if "error" in result:
                self.move_label.config(text="Error", foreground="red")
                self.status_label.config(text=result["error"][:40], foreground="red")
                return

            # Best move
            move = result.get("best_move", "--")
            self.move_label.config(text=move, foreground="#2e7d32")

            # Turn
            turn = result.get("turn", "")
            self.turn_label.config(text=f"{turn} to move")

            # Evaluation
            eval_str = result.get("evaluation", "0.00")
            eval_cp = result.get("eval_cp", 0)
            self.eval_label.config(text=eval_str)
            self._draw_eval_bar(eval_cp)

            # Principal variation
            pv = result.get("pv", "")
            self.pv_label.config(text=pv)

            # Detected FEN
            fen = result.get("fen", "")
            self.fen_display.config(text=fen if fen else "No position detected")

            # Legal moves
            legal_moves = result.get("legal_moves", [])
            if legal_moves:
                moves_text = ", ".join(legal_moves[:20])  # Show first 20
                if len(legal_moves) > 20:
                    moves_text += f"... (+{len(legal_moves) - 20} more)"
                self.moves_label.config(text=f"{len(legal_moves)} moves: {moves_text}")
            else:
                self.moves_label.config(text="No legal moves")

            # Status
            self.status_label.config(text="Watching...", foreground="green")

        self.root.after(0, update)

    def _update_status(self, text):
        """Update status label (thread-safe)."""
        self.root.after(0, lambda: self.status_label.config(text=text))

    def _analyze_manual_fen(self):
        """Analyze a manually entered FEN."""
        fen = self.fen_entry.get().strip()
        if not fen:
            messagebox.showwarning("No FEN", "Please paste a FEN string first.")
            return

        # Add default parts if missing
        if ' ' not in fen:
            fen += " w KQkq - 0 1"

        if not validate_fen(fen):
            messagebox.showerror("Invalid FEN", "The FEN string is invalid.")
            return

        # Make sure analyzer is ready
        stockfish_path = find_stockfish()
        if not stockfish_path:
            messagebox.showerror("No Engine", "Stockfish not found.")
            return

        if not self.analyzer:
            self.analyzer = ChessAnalyzer(stockfish_path, depth=self.depth_var.get())
            self.analyzer.start()

        self.status_label.config(text="Analyzing...", foreground="blue")
        self.root.update()

        result = self.analyzer.analyze(fen, depth=self.depth_var.get())
        self._update_ui_direct(result)

    def _update_ui_direct(self, result):
        """Update UI directly (not from thread)."""
        if "error" in result:
            self.move_label.config(text="Error", foreground="red")
            self.status_label.config(text=result["error"][:40], foreground="red")
            return

        move = result.get("best_move", "--")
        self.move_label.config(text=move, foreground="#2e7d32")

        turn = result.get("turn", "")
        self.turn_label.config(text=f"{turn} to move")

        eval_str = result.get("evaluation", "0.00")
        eval_cp = result.get("eval_cp", 0)
        self.eval_label.config(text=eval_str)
        self._draw_eval_bar(eval_cp)

        pv = result.get("pv", "")
        self.pv_label.config(text=pv)

        # Detected FEN
        fen = result.get("fen", "")
        self.fen_display.config(text=fen if fen else "No position detected")

        # Legal moves
        legal_moves = result.get("legal_moves", [])
        if legal_moves:
            moves_text = ", ".join(legal_moves[:20])
            if len(legal_moves) > 20:
                moves_text += f"... (+{len(legal_moves) - 20} more)"
            self.moves_label.config(text=f"{len(legal_moves)} moves: {moves_text}")
        else:
            self.moves_label.config(text="No legal moves")

        self.status_label.config(text="Analysis complete", foreground="green")

    def _save_debug(self):
        """Save current board capture for debugging."""
        region = self.config.get("board_region")
        if not region:
            messagebox.showwarning("No Board", "Select a board region first.")
            return

        from PIL import Image, ImageGrab
        import os

        # Capture the region
        bbox = (region["x"], region["y"],
                region["x"] + region["width"],
                region["y"] + region["height"])
        img = ImageGrab.grab(bbox=bbox)

        # Save to desktop
        debug_path = os.path.join(os.path.expanduser("~"), "Desktop", "chess_debug.png")
        img.save(debug_path)

        # Also try to detect and show FEN
        import numpy as np
        img_array = np.array(img)
        detector = BoardDetector(flipped=self.config.get("board_flipped", False))
        board = detector.detect(img_array)
        fen = board_to_fen(board, flipped=self.config.get("board_flipped", False))

        messagebox.showinfo("Debug Saved",
            f"Screenshot saved to:\n{debug_path}\n\nDetected FEN:\n{fen}\n\nPlease share the chess_debug.png file.")

    def _on_close(self):
        """Handle window close."""
        self._stop_watching()
        self.root.destroy()

    def run(self):
        """Run the application."""
        self.root.mainloop()


def main():
    """Entry point."""
    app = ChessWatcherApp()
    app.run()


if __name__ == "__main__":
    main()
