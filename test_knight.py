"""Debug knight detection with color-based segmentation."""
import cv2
import numpy as np
from PIL import Image

# Load the debug image
img = Image.open(r"C:\Users\kizsl\Desktop\chess_debug.png")
img_array = np.array(img)

h, w = img_array.shape[:2]
square_size = w // 8

print(f"Image: {w}x{h}, Square size: {square_size}")

# The knight is at row 2, col 2 (f3 from Black's view)
row, col = 2, 2
y1, y2 = row * square_size, (row + 1) * square_size
x1, x2 = col * square_size, (col + 1) * square_size

square = img_array[y1:y2, x1:x2]
print(f"Square coords: ({x1},{y1}) to ({x2},{y2})")

# Convert to HSV
hsv = cv2.cvtColor(square, cv2.COLOR_RGB2HSV)

margin = square_size // 4
center_rgb = square[margin:square_size-margin, margin:square_size-margin]
center_hsv = hsv[margin:square_size-margin, margin:square_size-margin]

# For white piece: low saturation, high value
sat = center_hsv[:, :, 1]
val = center_hsv[:, :, 2]

print(f"\nCenter saturation range: {np.min(sat)} - {np.max(sat)}, mean: {np.mean(sat):.1f}")
print(f"Center value range: {np.min(val)} - {np.max(val)}, mean: {np.mean(val):.1f}")

# Create binary mask: white pieces have low sat (<60) and high val (>180)
binary = ((sat < 60) & (val > 180)).astype(np.uint8) * 255

# Save images for inspection
Image.fromarray(center_rgb).save(r"C:\Users\kizsl\Desktop\knight_center.png")
Image.fromarray(binary).save(r"C:\Users\kizsl\Desktop\knight_binary_hsv.png")
print("\nSaved knight_center.png and knight_binary_hsv.png")

# Analyze shape
h, w = binary.shape
left_half = binary[:, :w//2]
right_half = binary[:, w//2:]
left_sum = float(np.sum(left_half))
right_sum = float(np.sum(right_half))
binary_sum = left_sum + right_sum

if binary_sum > 0:
    h_asymmetry = abs(left_sum - right_sum) / binary_sum
else:
    h_asymmetry = 0

top_half = binary[:h//2, :]
bottom_half = binary[h//2:, :]
top_sum = float(np.sum(top_half))

if binary_sum > 0:
    top_weight = top_sum / binary_sum
else:
    top_weight = 0.5

print(f"\nShape analysis:")
print(f"  Binary sum: {binary_sum:.0f}")
print(f"  H asymmetry: {h_asymmetry:.3f} (knight threshold: 0.1)")
print(f"  Top weight: {top_weight:.3f}")

# Total density
total_density = np.sum(binary) / (binary.size + 1)
print(f"  Total density: {total_density:.1f}")
