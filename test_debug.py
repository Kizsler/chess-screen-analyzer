"""Test detector on debug image."""
import cv2
import numpy as np
from PIL import Image
from board_detector import BoardDetector, board_to_fen, validate_fen

# Load the debug image
img = Image.open(r"C:\Users\kizsl\Desktop\chess_debug.png")
img_array = np.array(img)

print(f"Image size: {img_array.shape}")

# Test with flipped=True (Black's perspective)
detector = BoardDetector(flipped=True)
board = detector.detect(img_array)

print("\nDetected board (visual layout):")
for row_idx, row in enumerate(board):
    row_str = ""
    for piece in row:
        row_str += piece if piece else "."
    print(f"  Row {row_idx}: {row_str}")

fen = board_to_fen(board, flipped=True, turn='w')
print(f"\nGenerated FEN: {fen}")
print(f"Valid: {validate_fen(fen)}")

# Also show what the expected FEN should look like
# After 1. Nf3, the position should be:
expected = "rnbqkbnr/pppppppp/8/8/8/5N2/PPPPPPPP/RNBQKB1R b KQkq - 1 1"
print(f"\nExpected FEN: {expected}")
print(f"Expected valid: {validate_fen(expected)}")
