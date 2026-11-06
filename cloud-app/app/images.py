from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD = 10 * 1024 * 1024
MAX_PIXELS = 24_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class InvalidImage(ValueError):
    pass


def decode_image(data: bytes, *, photo=False):
    limit = MAX_UPLOAD if photo else 24 * 1024 * 1024
    if not data or len(data) > limit:
        raise InvalidImage("图片为空或超出大小限制；照片最大 10 MB。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as im:
                if im.format not in {"PNG", "JPEG", "WEBP"}:
                    raise InvalidImage("只支持 JPG、PNG 和 WebP 图片。")
                if im.width * im.height > MAX_PIXELS or max(im.size) > 12000:
                    raise InvalidImage("图片像素过大，请先缩小到 2400 万像素以内。")
                if photo and min(im.size) < 128:
                    raise InvalidImage("照片太小，请使用宽和高至少 128 像素的清晰照片。")
                im.seek(0)
                im.load()
                return ImageOps.exif_transpose(im).convert("RGBA")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImage("无法读取这张图片，请重新选择有效的 JPG、PNG 或 WebP。") from exc


def normalize_photo(data: bytes):
    im = decode_image(data, photo=True)
    im.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
    # Re-encode only pixels, stripping EXIF, GPS, ICC and other metadata.
    clean = Image.new("RGBA", im.size)
    clean.paste(im)
    buffer = BytesIO()
    clean.save(buffer, "PNG")
    return buffer.getvalue()
