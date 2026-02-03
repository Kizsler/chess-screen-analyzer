"""Stockfish chess engine integration."""

import os
import sys
import zipfile
import requests
from pathlib import Path
import chess
import chess.engine
from config import find_stockfish, STOCKFISH_DIR, load_config, save_config


STOCKFISH_DOWNLOAD_URL = "https://github.com/official-stockfish/Stockfish/releases/download/sf_17/stockfish-windows-x86-64-avx2.zip"


def download_stockfish(progress_callback=None):
    """
    Download Stockfish if not present.

    Args:
        progress_callback: Optional function(downloaded, total) for progress updates

    Returns:
        Path to stockfish executable or None if failed
    """
    STOCKFISH_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = STOCKFISH_DIR / "stockfish.zip"
    exe_name = "stockfish-windows-x86-64-avx2.exe"
    exe_path = STOCKFISH_DIR / exe_name

    if exe_path.exists():
        return str(exe_path)

    try:
        print("Downloading Stockfish...")
        response = requests.get(STOCKFISH_DOWNLOAD_URL, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total_size)

        print("Extracting Stockfish...")
        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Find the exe in the zip
            for name in zf.namelist():
                if name.endswith('.exe'):
                    # Extract to stockfish dir
                    zf.extract(name, STOCKFISH_DIR)
                    extracted = STOCKFISH_DIR / name
                    # Move to expected location
                    if extracted != exe_path:
                        extracted.rename(exe_path)
                    break

        # Clean up zip
        zip_path.unlink()

        # Save path to config
        config = load_config()
        config["stockfish_path"] = str(exe_path)
        save_config(config)

        print(f"Stockfish installed to: {exe_path}")
        return str(exe_path)

    except Exception as e:
        print(f"Error downloading Stockfish: {e}")
        return None


class ChessAnalyzer:
    """Analyzes chess positions using Stockfish."""

    def __init__(self, stockfish_path=None, depth=15):
        """
        Initialize the analyzer.

        Args:
            stockfish_path: Path to Stockfish executable
            depth: Analysis depth (higher = stronger but slower)
        """
        self.depth = depth
        self.engine = None
        self.stockfish_path = stockfish_path or find_stockfish()

    def start(self):
        """Start the engine."""
        if not self.stockfish_path:
            raise RuntimeError("Stockfish not found. Please install it first.")

        self.engine = chess.engine.SimpleEngine.popen_uci(self.stockfish_path)

    def stop(self):
        """Stop the engine."""
        if self.engine:
            self.engine.quit()
            self.engine = None

    def analyze(self, fen, depth=None):
        """
        Analyze a position.

        Args:
            fen: FEN string of the position
            depth: Override default depth

        Returns:
            dict with keys: best_move, evaluation, pv (principal variation)
        """
        if not self.engine:
            self.start()

        depth = depth or self.depth

        try:
            board = chess.Board(fen)
        except ValueError as e:
            return {"error": f"Invalid FEN: {e}"}

        if not board.is_valid():
            return {"error": f"Invalid position", "fen": fen, "legal_moves": []}

        try:
            result = self.engine.analyse(board, chess.engine.Limit(depth=depth))

            # Get best move
            best_move = result.get("pv", [None])[0]
            best_move_san = board.san(best_move) if best_move else None
            best_move_uci = best_move.uci() if best_move else None

            # Get evaluation
            score = result.get("score")
            if score:
                if score.is_mate():
                    mate_in = score.relative.moves
                    eval_str = f"Mate in {mate_in}" if mate_in > 0 else f"Getting mated in {-mate_in}"
                    eval_cp = 10000 if mate_in > 0 else -10000
                else:
                    eval_cp = score.relative.score()
                    eval_str = f"{eval_cp/100:+.2f}"
            else:
                eval_cp = 0
                eval_str = "0.00"

            # Get principal variation
            pv = result.get("pv", [])
            pv_san = []
            temp_board = board.copy()
            for move in pv[:5]:  # First 5 moves
                pv_san.append(temp_board.san(move))
                temp_board.push(move)

            # Get all legal moves
            legal_moves = [board.san(m) for m in board.legal_moves]

            return {
                "best_move": best_move_san,
                "best_move_uci": best_move_uci,
                "evaluation": eval_str,
                "eval_cp": eval_cp,
                "pv": " ".join(pv_san),
                "turn": "White" if board.turn else "Black",
                "fen": fen,
                "legal_moves": legal_moves
            }

        except Exception as e:
            return {"error": str(e)}

    def get_best_move(self, fen, time_limit=1.0):
        """
        Get best move with a time limit instead of depth.

        Args:
            fen: FEN string
            time_limit: Time in seconds

        Returns:
            Best move in SAN notation
        """
        if not self.engine:
            self.start()

        try:
            board = chess.Board(fen)
            result = self.engine.play(board, chess.engine.Limit(time=time_limit))
            return board.san(result.move)
        except Exception as e:
            return None


def ensure_stockfish():
    """Ensure Stockfish is available, downloading if needed."""
    path = find_stockfish()
    if path:
        return path
    return download_stockfish()


if __name__ == "__main__":
    # Test analyzer
    print("Ensuring Stockfish is available...")
    path = ensure_stockfish()

    if path:
        print(f"Using Stockfish at: {path}")
        analyzer = ChessAnalyzer(path)
        analyzer.start()

        # Test position (starting position)
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        print(f"\nAnalyzing: {fen}")
        result = analyzer.analyze(fen)
        print(f"Best move: {result.get('best_move')}")
        print(f"Evaluation: {result.get('evaluation')}")
        print(f"Line: {result.get('pv')}")

        analyzer.stop()
    else:
        print("Could not find or download Stockfish")
