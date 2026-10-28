import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

PROFILE_PICS_DIR = Path(__file__).resolve().parent / "media" / "profile_pics" # anchored to Backend/, same folder main.py serves at /media


# CPU bound (decode, resize, encode), so these are plain sync functions
# async routes call process_profile_image through run_in_threadpool so it doesn't block the event loop
def process_profile_image(content: bytes) -> str:
    """Square crop to 300x300, save as a jpg under a random name, and return that name."""
    with Image.open(BytesIO(content)) as original: # raises UnidentifiedImageError if the bytes aren't an image
        img = ImageOps.exif_transpose(original) # phone photos store rotation in exif, apply it so the picture isn't sideways

        img = ImageOps.fit(img, (300, 300), method=Image.Resampling.LANCZOS) # crop to square from the center, then resize

        # jpeg only supports RGB, transparency (RGBA/LA) and palette (P) images have to be converted
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        filename = f"{uuid.uuid4().hex}.jpg" # never use the uploaded filename, it's user controlled and may collide
        filepath = PROFILE_PICS_DIR / filename

        PROFILE_PICS_DIR.mkdir(parents=True, exist_ok=True)

        img.save(filepath, "JPEG", quality=85, optimize=True)

    return filename


def delete_profile_image(filename: str | None) -> None:
    if filename is None:
        return

    filepath = PROFILE_PICS_DIR / filename
    if filepath.exists():
        filepath.unlink()
