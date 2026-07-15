from PIL import Image
import sys
import os

png_path = r"C:/Users/Dell 14/.gemini/antigravity/brain/19c60c07-108a-4664-b882-cc6ddc138c8c/app_icon_1768476338276.png"
ico_path = r"c:/Users/Dell 14/Desktop/wp_local_installer_pro/app.ico"

if os.path.exists(png_path):
    img = Image.open(png_path)
    img.save(ico_path, format="ICO")
    print(f"Converted {png_path} to {ico_path}")
else:
    print("PNG not found")
