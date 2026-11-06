from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-image-1.5"
    data_dir: Path = ROOT / ".runtime"
    ttl_seconds: int = 3600
    secure_cookie: bool = False
    max_active_jobs: int = 3
    max_stored_jobs: int = 40
    font_path: Path = ROOT / "web/assets/NotoSansCJKsc-Regular.otf"

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env", override=False)
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        url = urlsplit(base)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("OPENAI_BASE_URL 必须是无账号、查询参数的 HTTPS API 地址。")
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            api_base=base,
            model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1.5"),
            data_dir=Path(os.getenv("STICKER_DATA_DIR", str(ROOT / ".runtime"))),
            ttl_seconds=max(60, int(os.getenv("STICKER_TTL_SECONDS", "3600"))),
            secure_cookie=os.getenv("STICKER_SECURE_COOKIE", "false").lower() == "true",
            font_path=Path(os.getenv("STICKER_FONT_PATH", str(ROOT / "web/assets/NotoSansCJKsc-Regular.otf"))),
        )

    @property
    def provider_host(self):
        return urlsplit(self.api_base).hostname
