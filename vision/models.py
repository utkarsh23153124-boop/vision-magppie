"""Pinned OpenCV Zoo models. No downloads occur during camera processing."""
from pathlib import Path
import hashlib
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REVISION = "47534e27c9851bb1128ccc0102f1145e27f23f98"
MODELS = {
    "person": (
        "object_detection_nanodet/object_detection_nanodet_2022nov.onnx",
        "4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186",
    ),
    "face": (
        "face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
}


def model_path(kind):
    return ROOT / "models" / Path(MODELS[kind][0]).name


def verified(path, expected):
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected


def require_models():
    for kind, (_, digest) in MODELS.items():
        if not verified(model_path(kind), digest):
            raise RuntimeError("Models missing or checksum mismatch. Run setup.bat first.")


def download_models():
    for kind, (relative, digest) in MODELS.items():
        path = model_path(kind)
        if verified(path, digest):
            print(f"Verified: {path.name}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{REVISION}/models/{relative}"
        temporary = path.with_suffix(".part")
        try:
            print(f"Downloading: {path.name}", flush=True)
            with urllib.request.urlopen(url, timeout=60) as source, temporary.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            if not verified(temporary, digest):
                raise RuntimeError(f"Checksum mismatch for {path.name}; download rejected.")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    download_models()
