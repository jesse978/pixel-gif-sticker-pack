import base64
import binascii
import httpx
from .catalog import BY_ID, STYLES
from .config import Settings
from .images import decode_image, InvalidImage


class ProviderError(Exception):
    pass


def build_prompt(choices, style: str, grid):
    cols, rows = grid
    cells = " ".join(f"Cell {i+1} (column {i % cols + 1}, row {i // cols + 1}): {BY_ID[x.id]['action']}." for i, x in enumerate(choices))
    return (
        f"Create ONE transparent sprite ATLAS, exactly {cols} columns by {rows} rows of equal cells. "
        f"Place exactly {len(choices)} distinct upper-body chat sticker poses of the SAME PERSON in the supplied reference photo, in reading order. "
        "The reference photo is the identity anchor for every sticker in the set. "
        "Preserve recognizable identity, facial geometry, distinctive features, hairstyle, skin tone, and outfit. "
        "Do not change their age or invent a different person. "
        + STYLES[style] + " " + cells + " "
        "Change the facial expression and body pose to match the requested action; do not simply copy the reference. "
        "Each cell contains ONE centered head-and-shoulders or upper-body character with all hands visible, "
        "generous transparent margins of at least 15% on every side, and wide transparent gutters. "
        "Leave remaining unused cells completely transparent. "
        "No visible grid lines, text, letters, captions, watermarks, frames, or extra people. "
        "True alpha transparency, not a painted checkerboard. Keep facial details crisp."
    )


class OpenAIImageProvider:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.transport = transport

    async def edit_atlas(self, photo: bytes, choices, style: str, grid):
        data = {
            "model": self.settings.model,
            "prompt": build_prompt(choices, style, grid),
            "n": "1", "size": "1536x1024" if grid[0] > grid[1] else "1024x1024", "quality": "medium",
            "background": "transparent", "output_format": "png",
        }
        if self.settings.model.startswith("gpt-image-1.5"):
            data["input_fidelity"] = "high"
        # No retries: retrying an uncertain image request may incur another charge.
        async with httpx.AsyncClient(timeout=httpx.Timeout(240, connect=20), transport=self.transport, follow_redirects=False) as client:
            try:
                response = await client.post(
                    self.settings.api_base + "/images/edits",
                    headers={"Authorization": "Bearer " + self.settings.api_key},
                    data=data, files={"image[]": ("reference.png", photo, "image/png")},
                )
            except httpx.TimeoutException as exc:
                raise ProviderError("图像服务超时。请求可能已产生费用；请检查服务商记录后再重试。") from exc
            except httpx.HTTPError as exc:
                raise ProviderError("无法连接图像服务，请检查服务器网络和 API 地址。") from exc
        if response.status_code != 200:
            hints = {
                400: "图像服务拒绝了请求，请检查模型参数或换一张照片。",
                401: "图像服务密钥无效，请检查服务端配置。",
                403: "图像服务无访问权限，请检查模型权限或账号验证。",
                429: "图像服务额度不足或触发限流，请检查账号额度后再试。",
            }
            # Never send upstream error bodies to users: providers can echo secrets or inputs.
            raise ProviderError(hints.get(response.status_code, "图像服务暂时不可用。请检查服务商记录后再重试。"))
        try:
            encoded = response.json()["data"][0]["b64_json"]
            if not isinstance(encoded, str) or len(encoded) > 34 * 1024 * 1024:
                raise ValueError("Invalid payload size")
            decoded = base64.b64decode(encoded, validate=True)
            image = decode_image(decoded)
            return image
        except (KeyError, IndexError, TypeError, ValueError, binascii.Error, InvalidImage) as exc:
            raise ProviderError("图像服务未返回有效的图片。没有使用原照片或演示图片替代。") from exc
