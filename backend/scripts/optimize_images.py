import os
from PIL import Image

def optimize_images(assets_dir):
    for filename in os.listdir(assets_dir):
        if filename.endswith(".png") or filename.endswith(".jpg") or filename.endswith(".jpeg"):
            filepath = os.path.join(assets_dir, filename)
            webp_filepath = os.path.join(assets_dir, filename.rsplit('.', 1)[0] + '.webp')
            
            # Skip if webp version already exists
            if os.path.exists(webp_filepath):
                print(f"Skipping {filename} (webp already exists)")
                continue
                
            try:
                with Image.open(filepath) as img:
                    img.save(webp_filepath, 'WEBP', quality=85)
                    original_size = os.path.getsize(filepath)
                    new_size = os.path.getsize(webp_filepath)
                    print(f"Optimized {filename}: {original_size // 1024}KB -> {new_size // 1024}KB")
            except Exception as e:
                print(f"Failed to optimize {filename}: {e}")

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(current_dir, "..", "..", "assets")
    optimize_images(assets_dir)
