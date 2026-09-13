import os
import requests

def download():
    model_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "open-nsfw.onnx")
    if not os.path.exists(model_path) or os.path.getsize(model_path) < 10000000:
        print("[SETUP] Downloading Yahoo Open-NSFW ONNX model...")
        url = "https://huggingface.co/bluefoxcreation/open-nsfw/resolve/main/open-nsfw.onnx"
        r = requests.get(url, stream=True, timeout=60)
        with open(model_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        print(f"[SETUP] Successfully downloaded model: {os.path.getsize(model_path)} bytes")
    else:
        print(f"[SETUP] Model already exists: {os.path.getsize(model_path)} bytes")

if __name__ == "__main__":
    download()
