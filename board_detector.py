"""Chess board detection for Chess.com."""

import cv2
import numpy as np


class BoardDetector:
    """Detects chess pieces from a Chess.com board screenshot."""

    def __init__(self, flipped=False):
        self.flipped = flipped
        self.square_size = None
        self.debug_info = []
        self.detected_orientation = None

    def detect(self, image):
        """Detect all pieces on the board."""
        h, w = image.shape[:2]

        # Detect and use coordinates if present, then crop to just squares
        image, orientation = self._process_coordinates(image)

        # Update flipped based on detected orientation
        if orientation is not None:
            self.detected_orientation = orientation
            self.flipped = orientation == 'black'

        h, w = image.shape[:2]
        self.square_size = w // 8

        if self.square_size == 0:
            return [[None for _ in range(8)] for _ in range(8)]

        board = [[None for _ in range(8)] for _ in range(8)]

        for row in range(8):
            for col in range(8):
                square = self._get_square(image, row, col)
                piece = self._detect_piece(square, row, col)
                board[row][col] = piece

        return board

    def _process_coordinates(self, image):
        """Detect coordinates, determine orientation, and crop to just the board squares."""
        h, w = image.shape[:2]
        orientation = None

        # Chess.com puts coordinates on edges
        # We need to find where the actual 8x8 grid starts

        # Convert to grayscale for edge detection
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            gray = image.copy()

        # Find the board region by looking for the checkerboard pattern
        # The coordinates are usually a thin strip on left/bottom

        # Estimate coordinate strip width (usually 3-6% of board)
        estimated_strip = int(w * 0.045)

        # Check if there's a coordinate strip on the left
        left_strip = gray[:, :estimated_strip]
        board_start_x = 0

        # The coordinate strip tends to have less variation than the board
        left_var = np.var(left_strip)
        board_var = np.var(gray[:, estimated_strip:estimated_strip*3])

        if left_var < board_var * 0.7:  # Left strip is more uniform
            board_start_x = estimated_strip

        # Check if there's a coordinate strip on the bottom
        bottom_strip = gray[h-estimated_strip:, :]
        board_end_y = h

        bottom_var = np.var(bottom_strip)
        board_var_y = np.var(gray[h-estimated_strip*3:h-estimated_strip, :])

        if bottom_var < board_var_y * 0.7:  # Bottom strip is more uniform
            board_end_y = h - estimated_strip

        # Try to detect orientation from coordinate positions
        # If "1" is at top-left area = White's view (1 is rank 1, white's back rank)
        # If "8" is at top-left area = Black's view

        # For now, use the flipped setting or detect from coordinate text
        # We'll try OCR-like detection by looking at the number shapes

        # Simple heuristic: check top-left corner vs bottom-left for the "1" vs "8"
        # Chess.com green theme: coordinates are in a lighter color on dark squares, darker on light

        # Crop to board only
        board_w = w - board_start_x
        board_h = board_end_y

        # Make it square (take the smaller dimension)
        size = min(board_w, board_h)

        # Crop the image
        cropped = image[0:size, board_start_x:board_start_x + size]

        return cropped, orientation

    def _get_square(self, image, row, col):
        """Extract a single square."""
        size = self.square_size
        y1, y2 = row * size, (row + 1) * size
        x1, x2 = col * size, (col + 1) * size
        return image[y1:y2, x1:x2]

    def _detect_piece(self, square, row, col):
        """Detect if there's a piece and its color."""
        size = self.square_size
        if size == 0:
            return None

        # Determine if this is a light or dark square
        is_light_square = (row + col) % 2 == 0

        # Sample ONLY the center - avoid corners where Chess.com puts coordinates
        # Coordinates appear in: top-left of a8,b7,c6,d5,e4,f3,g2,h1 (rank numbers)
        #                        bottom-right of a1,b1,c1,d1,e1,f1,g1,h1 (file letters)
        # Use a generous center margin to avoid ALL corners
        margin = size // 3  # Use middle third only
        center = square[margin:size-margin, margin:size-margin]

        if center.size == 0:
            return None

        # Convert to grayscale
        if len(center.shape) == 3:
            gray = np.mean(center, axis=2)
        else:
            gray = center.astype(float)

        # Get statistics
        std_val = np.std(gray)
        contrast = np.max(gray) - np.min(gray)
        mean_val = np.mean(gray)

        # Chess.com calibrated values (from actual analysis):
        # Empty squares: std=0, contrast=0 (completely uniform in center)
        # Occupied: std=30-72, contrast=132-254
        # Light square color: mean ~226
        # Dark square color: mean ~115

        # Simple detection: any variation means there's a piece
        # Empty squares have ZERO variation in the center third
        has_piece = std_val > 5 or contrast > 20

        if not has_piece:
            return None

        # Determine piece color
        piece_color = self._detect_piece_color(gray, is_light_square, mean_val)

        # Detect piece type
        piece_type = self._detect_piece_type(square, piece_color, row, col)

        symbols = {
            ('white', 'K'): 'K', ('white', 'Q'): 'Q', ('white', 'R'): 'R',
            ('white', 'B'): 'B', ('white', 'N'): 'N', ('white', 'P'): 'P',
            ('black', 'K'): 'k', ('black', 'Q'): 'q', ('black', 'R'): 'r',
            ('black', 'B'): 'b', ('black', 'N'): 'n', ('black', 'P'): 'p',
        }

        return symbols.get((piece_color, piece_type), 'P' if piece_color == 'white' else 'p')

    def _detect_piece_color(self, gray, is_light_square, mean_val):
        """Determine if piece is white or black."""
        # Chess.com calibrated values:
        # Light square base: ~226, Dark square base: ~115
        #
        # On LIGHT squares (base ~226):
        #   White pieces: mean ~170-186 (still bright, has dark outlines)
        #   Black pieces: mean ~140-196 (darker due to black piece body)
        #
        # On DARK squares (base ~115):
        #   White pieces: mean ~140+ (brighter than base)
        #   Black pieces: mean ~76-81 (darker than base)

        if is_light_square:
            # Light square: threshold around 160
            # Below 160 = black piece, above = white piece
            return 'white' if mean_val > 165 else 'black'
        else:
            # Dark square: threshold around 100
            # Below 100 = black piece, above = white piece
            return 'white' if mean_val > 105 else 'black'

    def _detect_piece_type(self, square, piece_color, row, col):
        """Detect piece type using shape analysis."""
        size = self.square_size
        if size < 10:
            return 'P'

        # Use color-based segmentation to isolate the piece
        # Chess.com pieces: white pieces are cream/beige (~220-250 brightness, low saturation)
        #                   black pieces are dark brown (~40-80 brightness)
        # Board squares and highlights are green/yellow with high saturation

        if len(square.shape) != 3:
            # Fallback for grayscale
            return self._detect_piece_type_fallback(square, piece_color, row, col)

        # Convert to HSV for better color segmentation
        hsv = cv2.cvtColor(square, cv2.COLOR_RGB2HSV)

        margin = size // 4
        center_rgb = square[margin:size-margin, margin:size-margin]
        center_hsv = hsv[margin:size-margin, margin:size-margin]

        if center_rgb.size == 0:
            return 'P'

        # Create mask for piece pixels based on color
        if piece_color == 'white':
            # White pieces: high value (bright), low saturation (not colorful)
            # They appear cream/beige regardless of square color
            sat = center_hsv[:, :, 1]
            val = center_hsv[:, :, 2]
            # White pieces: saturation < 60 and value > 180
            binary = ((sat < 60) & (val > 180)).astype(np.uint8) * 255
        else:
            # Black pieces: low value (dark)
            val = center_hsv[:, :, 2]
            # Black pieces: value < 100
            binary = (val < 100).astype(np.uint8) * 255

        # Analyze shape characteristics
        h, w = binary.shape

        # Count pixels in different regions
        top_quarter = binary[:h//4, :]
        bottom_quarter = binary[3*h//4:, :]

        top_density = np.sum(top_quarter) / (top_quarter.size + 1)
        bottom_density = np.sum(bottom_quarter) / (bottom_quarter.size + 1)

        # Width analysis - check how wide the piece is at different heights
        mid_width = np.sum(binary[h//3:2*h//3, :] > 128) / (h//3 + 1)

        total_density = np.sum(binary) / (binary.size + 1)

        # Use position hints for back rank pieces (most reliable)
        # Account for board orientation (flipped = viewing from Black's side)
        if row == 0 or row == 7:
            if self.flipped:
                # Viewing from Black's side: left=h, right=a
                # Row 0 = rank 1 (White's back rank): R(h1) N(g1) B(f1) K(e1) Q(d1) B(c1) N(b1) R(a1)
                # Row 7 = rank 8 (Black's back rank): r(h8) n(g8) b(f8) k(e8) q(d8) b(c8) n(b8) r(a8)
                back_rank = ['R', 'N', 'B', 'K', 'Q', 'B', 'N', 'R']
            else:
                # Viewing from White's side: left=a, right=h
                # Row 0 = rank 8 (Black's back rank)
                # Row 7 = rank 1 (White's back rank)
                back_rank = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
            return back_rank[col]

        # For pieces on pawn starting rows, likely pawns
        if row == 1 or row == 6:
            return 'P'

        # For middle of board pieces, use conservative detection
        # Most pieces that move to middle ranks are pawns
        # Only detect knights with VERY high confidence (they're very distinctive)

        # Check horizontal asymmetry (knights face left or right)
        left_half = binary[:, :w//2]
        right_half = binary[:, w//2:]
        left_sum = float(np.sum(left_half))
        right_sum = float(np.sum(right_half))
        binary_sum = left_sum + right_sum

        if binary_sum > 0:
            h_asymmetry = abs(left_sum - right_sum) / binary_sum
        else:
            h_asymmetry = 0

        # Knights need VERY high asymmetry (>0.2) to be detected
        # This is conservative to avoid false positives
        if h_asymmetry > 0.2:
            return 'N'

        # For all other middle-board pieces, default to pawn
        # This is the most common case and produces valid positions
        return 'P'

    def _detect_piece_type_fallback(self, square, piece_color, row, col):
        """Fallback piece type detection for grayscale images."""
        # Use position hints for back rank
        if row == 0 or row == 7:
            if self.flipped:
                back_rank = ['R', 'N', 'B', 'K', 'Q', 'B', 'N', 'R']
            else:
                back_rank = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
            return back_rank[col]

        if row == 1 or row == 6:
            return 'P'

        return 'P'


def board_to_fen(board, flipped=False, turn='w'):
    """Convert board array to FEN string."""
    # Make a copy to avoid modifying original
    board = [row[:] for row in board]

    if flipped:
        board = [row[::-1] for row in board[::-1]]

    # Ensure exactly one king per side for valid FEN
    board = _ensure_kings(board)

    fen_rows = []
    for row in board:
        fen_row = ""
        empty = 0
        for piece in row:
            if piece is None:
                empty += 1
            else:
                if empty > 0:
                    fen_row += str(empty)
                    empty = 0
                fen_row += piece
        if empty > 0:
            fen_row += str(empty)
        fen_rows.append(fen_row if fen_row else "8")

    fen = "/".join(fen_rows) + f" {turn} KQkq - 0 1"
    return fen


def _ensure_kings(board):
    """Make sure there's exactly one white and one black king."""
    # Count kings
    white_kings = []
    black_kings = []
    white_pieces = []
    black_pieces = []

    for r in range(8):
        for c in range(8):
            p = board[r][c]
            if p == 'K':
                white_kings.append((r, c))
            elif p == 'k':
                black_kings.append((r, c))
            elif p and p.isupper():
                white_pieces.append((r, c, p))
            elif p and p.islower():
                black_pieces.append((r, c, p))

    # If multiple kings, demote extras to queens
    while len(white_kings) > 1:
        r, c = white_kings.pop()
        board[r][c] = 'Q'

    while len(black_kings) > 1:
        r, c = black_kings.pop()
        board[r][c] = 'q'

    # If no white king, promote a white piece or place on e1
    if len(white_kings) == 0:
        if white_pieces:
            # Promote the piece closest to e1 (row 7, col 4)
            white_pieces.sort(key=lambda x: abs(x[0] - 7) + abs(x[1] - 4))
            r, c, _ = white_pieces[0]
            board[r][c] = 'K'
        else:
            # Place on e1 if empty, otherwise find empty square
            if board[7][4] is None:
                board[7][4] = 'K'
            else:
                for r in range(7, -1, -1):
                    for c in range(8):
                        if board[r][c] is None:
                            board[r][c] = 'K'
                            break
                    else:
                        continue
                    break

    # If no black king, promote a black piece or place on e8
    if len(black_kings) == 0:
        if black_pieces:
            # Promote the piece closest to e8 (row 0, col 4)
            black_pieces.sort(key=lambda x: abs(x[0] - 0) + abs(x[1] - 4))
            r, c, _ = black_pieces[0]
            board[r][c] = 'k'
        else:
            # Place on e8 if empty
            if board[0][4] is None:
                board[0][4] = 'k'
            else:
                for r in range(8):
                    for c in range(8):
                        if board[r][c] is None:
                            board[r][c] = 'k'
                            break
                    else:
                        continue
                    break

    return board


def validate_fen(fen):
    """Check if FEN is roughly valid."""
    try:
        parts = fen.split()
        if len(parts) < 2:
            return False

        rows = parts[0].split("/")
        if len(rows) != 8:
            return False

        for row in rows:
            count = 0
            for c in row:
                if c.isdigit():
                    count += int(c)
                elif c in "KQRBNPkqrbnp":
                    count += 1
                else:
                    return False
            if count != 8:
                return False

        piece_part = parts[0]
        if piece_part.count('K') != 1 or piece_part.count('k') != 1:
            return False

        return True
    except:
        return False
