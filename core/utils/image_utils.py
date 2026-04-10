"""Image / base64 helpers."""
import base64
from pathlib import Path

def encode_image_to_base64(image_path: str) -> str:
    """Read an image file and return base64 text."""
    try:
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image: {e}")
        return ""

def decode_base64_to_image(base64_str: str, output_path: str):
    """Write base64 payload to a file."""
    try:
        image_data = base64.b64decode(base64_str)
        with open(output_path, 'wb') as f:
            f.write(image_data)
        return True
    except Exception as e:
        print(f"Error decoding image: {e}")
        return False

def create_data_url(base64_data: str, media_type: str = "image/png") -> str:
    """Build a data: URL."""
    return f"data:{media_type};base64,{base64_data}"
