import urllib.request
from vision.models import download_models, REVISION, verified
from central.staff import MODEL, SHA256

if __name__ == '__main__':
    download_models()
    if not verified(MODEL, SHA256):
        temporary = MODEL.with_suffix('.part')
        try:
            url = f'https://media.githubusercontent.com/media/opencv/opencv_zoo/{REVISION}/models/face_recognition_sface/{MODEL.name}'
            with urllib.request.urlopen(url, timeout=60) as source, temporary.open('wb') as target:
                while chunk := source.read(1024*1024):
                    target.write(chunk)
            if not verified(temporary, SHA256):
                raise RuntimeError('Staff model checksum mismatch.')
            temporary.replace(MODEL)
        finally:
            temporary.unlink(missing_ok=True)
    print('All central models verified.')
