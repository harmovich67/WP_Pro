"""Convert PNG logo to ICO format for Windows executable"""
from PIL import Image

# Load the generated logo
logo = Image.open(r"C:/Users/Dell 14/.gemini/antigravity/brain/4c15b2ed-1c60-4d9e-ad76-e90dd5a982f8/harmulizer_logo_1768819781213.png")

# Resize to multiple sizes for better quality at different resolutions
sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
icons = []

for size in sizes:
    resized = logo.resize(size, Image.Resampling.LANCZOS)
    icons.append(resized)

# Save as ICO with multiple sizes
icons[0].save('app.ico', format='ICO', sizes=[(img.width, img.height) for img in icons], append_images=icons[1:])

print("✓ Icon created: app.ico")
print(f"✓ Sizes included: {', '.join([f'{s[0]}x{s[1]}' for s in sizes])}")
