"""Chess Watcher - Web UI Backend."""

import json
import threading
import time
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import webbrowser

from config import load_config, save_config, find_stockfish
from region_selector import select_board_region
from screen_capture import ScreenCapture
from board_detector import BoardDetector, board_to_fen, validate_fen
from analyzer import ChessAnalyzer, download_stockfish

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Global state
state = {
    "running": False,
    "config": load_config(),
    "current_fen": None,
    "last_result": None,
    "capture": None,
    "detector": None,
    "analyzer": None,
    "watch_thread": None,
    "stockfish_ready": False
}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status')
def get_status():
    stockfish_path = find_stockfish()
    return jsonify({
        "running": state["running"],
        "board_selected": state["config"].get("board_region") is not None,
        "stockfish_ready": stockfish_path is not None,
        "playing_as": "black" if state["config"].get("board_flipped") else "white",
        "depth": state["config"].get("analysis_depth", 15)
    })


@app.route('/api/analysis')
def get_analysis():
    result = state["last_result"]
    if result:
        return jsonify(result)
    return jsonify({
        "best_move": None,
        "evaluation": "0.00",
        "eval_cp": 0,
        "pv": "",
        "turn": "White",
        "fen": None,
        "legal_moves": []
    })


@app.route('/api/select-board', methods=['POST'])
def select_board():
    """Trigger board region selection."""
    def do_select():
        time.sleep(0.5)  # Give browser time to minimize
        region = select_board_region()
        if region:
            state["config"]["board_region"] = region
            # Use the flipped value from region selection
            if "flipped" in region:
                state["config"]["board_flipped"] = region["flipped"]
            save_config(state["config"])

    threading.Thread(target=do_select, daemon=True).start()
    return jsonify({"status": "selecting"})


@app.route('/api/start', methods=['POST'])
def start_watching():
    if state["running"]:
        return jsonify({"error": "Already running"})

    region = state["config"].get("board_region")
    if not region:
        return jsonify({"error": "No board region selected"})

    stockfish_path = find_stockfish()
    if not stockfish_path:
        return jsonify({"error": "Stockfish not found"})

    state["running"] = True
    state["capture"] = ScreenCapture(region)
    state["detector"] = BoardDetector(flipped=state["config"].get("board_flipped", False))
    state["analyzer"] = ChessAnalyzer(stockfish_path, depth=state["config"].get("analysis_depth", 15))
    state["analyzer"].start()

    state["watch_thread"] = threading.Thread(target=watch_loop, daemon=True)
    state["watch_thread"].start()

    return jsonify({"status": "started"})


@app.route('/api/stop', methods=['POST'])
def stop_watching():
    state["running"] = False

    if state["analyzer"]:
        state["analyzer"].stop()
        state["analyzer"] = None

    if state["capture"]:
        state["capture"].close()
        state["capture"] = None

    return jsonify({"status": "stopped"})


@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json

    if "playing_as" in data:
        state["config"]["board_flipped"] = data["playing_as"] == "black"
        if state["detector"]:
            state["detector"].flipped = state["config"]["board_flipped"]

    if "depth" in data:
        state["config"]["analysis_depth"] = int(data["depth"])

    save_config(state["config"])
    return jsonify({"status": "updated"})


@app.route('/api/analyze-fen', methods=['POST'])
def analyze_fen():
    data = request.json
    fen = data.get("fen", "").strip()

    if not fen:
        return jsonify({"error": "No FEN provided"})

    if ' ' not in fen:
        fen += " w KQkq - 0 1"

    if not validate_fen(fen):
        return jsonify({"error": "Invalid FEN"})

    stockfish_path = find_stockfish()
    if not stockfish_path:
        return jsonify({"error": "Stockfish not found"})

    if not state["analyzer"]:
        state["analyzer"] = ChessAnalyzer(stockfish_path, depth=state["config"].get("analysis_depth", 15))
        state["analyzer"].start()

    result = state["analyzer"].analyze(fen, depth=state["config"].get("analysis_depth", 15))
    state["last_result"] = result
    return jsonify(result)


@app.route('/api/debug', methods=['POST'])
def save_debug():
    """Save debug screenshot and detection info."""
    import os
    from PIL import ImageGrab
    import numpy as np

    region = state["config"].get("board_region")
    if not region:
        return jsonify({"error": "No board region selected"})

    try:
        # Capture the region
        bbox = (region["x"], region["y"],
                region["x"] + region["width"],
                region["y"] + region["height"])
        img = ImageGrab.grab(bbox=bbox)

        # Save screenshot
        debug_path = os.path.join(os.path.expanduser("~"), "Desktop", "chess_debug.png")
        img.save(debug_path)

        # Run detection
        img_array = np.array(img)
        detector = BoardDetector(flipped=state["config"].get("board_flipped", False))
        board = detector.detect(img_array)
        fen = board_to_fen(board, flipped=state["config"].get("board_flipped", False))

        return jsonify({
            "path": debug_path,
            "fen": fen,
            "region": region,
            "flipped": state["config"].get("board_flipped", False)
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route('/api/download-stockfish', methods=['POST'])
def download_stockfish_route():
    def do_download():
        path = download_stockfish()
        state["stockfish_ready"] = path is not None

    threading.Thread(target=do_download, daemon=True).start()
    return jsonify({"status": "downloading"})


def watch_loop():
    """Main watching loop."""
    interval = state["config"].get("capture_interval_ms", 500) / 1000.0

    while state["running"]:
        try:
            img, changed = state["capture"].capture_if_changed()

            if changed:
                board = state["detector"].detect(img)

                # Determine whose turn - start with user's color
                user_is_black = state["config"].get("board_flipped", False)

                if state["current_fen"]:
                    # Position changed - toggle turn from previous
                    prev_turn = state["current_fen"].split()[1] if len(state["current_fen"].split()) > 1 else 'w'
                    turn = 'b' if prev_turn == 'w' else 'w'
                else:
                    # First detection - assume it's user's turn
                    turn = 'b' if user_is_black else 'w'

                fen = board_to_fen(board, flipped=state["config"].get("board_flipped", False), turn=turn)

                if not validate_fen(fen):
                    continue

                if fen != state["current_fen"]:
                    state["current_fen"] = fen
                    result = state["analyzer"].analyze(fen, depth=state["config"].get("analysis_depth", 15))
                    # Always include the detected FEN for debugging
                    result["detected_fen"] = fen

                    # Check if it's the user's turn
                    user_is_black = state["config"].get("board_flipped", False)
                    fen_turn = fen.split()[1] if len(fen.split()) > 1 else 'w'
                    is_user_turn = (fen_turn == 'b' and user_is_black) or (fen_turn == 'w' and not user_is_black)

                    result["is_user_turn"] = is_user_turn
                    result["user_color"] = "Black" if user_is_black else "White"

                    state["last_result"] = result

        except Exception as e:
            state["last_result"] = {"error": str(e)}

        time.sleep(interval)


def main():
    # Check stockfish
    state["stockfish_ready"] = find_stockfish() is not None

    # Open browser
    threading.Timer(1.0, lambda: webbrowser.open('http://localhost:5000')).start()

    # Run server
    app.run(host='localhost', port=5000, debug=False, threaded=True)


if __name__ == '__main__':
    main()
