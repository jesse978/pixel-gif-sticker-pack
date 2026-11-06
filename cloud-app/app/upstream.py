"""A thin adapter around the unmodified upstream command-line exporter."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image
from .config import ROOT
from .images import InvalidImage

UPSTREAM = ROOT.parent
SAMPLES = {
    "happy": 19, "ok": 49, "love": 25, "cry": 34,
    "tired": 85, "shock": 38, "angry": 46, "cheer": 69,
    "bye": 10, "think": 48, "thanks": 6, "awkward": 41,
}
INKS = {"dark": "#283C35", "coral": "#C85845", "purple": "#715393"}


def grid_for(count):
    cols = 1 if count == 1 else 2 if count <= 4 else 4
    return cols, (count + cols - 1) // cols


def inspect_atlas(image, count):
    cols, rows = grid_for(count)
    if image.getchannel("A").getextrema()[0] >= 144:
        raise InvalidImage("图集没有透明背景。请使用真正透明的 PNG，不能是画出来的棋盘格。")
    hashes = set()
    for i in range(count):
        x, y = i % cols, i // cols
        cell = image.crop((x * image.width // cols, y * image.height // rows,
                           (x + 1) * image.width // cols, (y + 1) * image.height // rows))
        alpha = cell.getchannel("A").point(lambda a: 255 if a >= 144 else 0)
        box = alpha.getbbox()
        if not box:
            raise InvalidImage(f"第 {i+1} 格为空，请重新生成或导入完整图集。")
        cell.putalpha(alpha)
        digest = hashlib.sha256(cell.crop(box).tobytes()).hexdigest()
        if digest in hashes:
            raise InvalidImage("图集中有完全重复的姿势。原项目要求每个表情有不同素材。")
        hashes.add(digest)
    return {"grid": [cols, rows], "count": count, "alpha": True,
            "visual_review": "pending", "user_acceptance": "pending"}


def demo_atlas(choices):
    """Extract body regions from upstream examples. This is explicitly a replay demo."""
    cols, rows = grid_for(len(choices))
    atlas = Image.new("RGBA", (cols * 320, rows * 320))
    root = UPSTREAM / "examples/whale-maid"
    for i, choice in enumerate(choices):
        path = next(root.glob(f"*/{SAMPLES[choice.id]:03}.gif"))
        with Image.open(path) as image:
            # The original captions sit below y=245. No new character art is synthesized.
            sprite = image.convert("RGBA").crop((0, 0, 320, 245))
        atlas.alpha_composite(sprite, ((i % cols) * 320, (i // cols) * 320 + 25))
    return atlas


def manifest_for(options):
    return {
        "title": "像你表情包", "count": len(options.expressions),
        "render_style": "pixel" if options.style == "pixel" else "hd",
        "groups": [{"name": "日常表情", "atlas": "atlas.png",
                    "grid": list(grid_for(len(options.expressions))),
                    "ink": INKS[options.ink], "tint": "#A9C9AF", "background": "#F1F4ED",
                    "entries": [{"text": item.caption, "cell": [i % grid_for(len(options.expressions))[0], i // grid_for(len(options.expressions))[0]],
                                 "motion": options.motion, "icon": "none"}
                                for i, item in enumerate(options.expressions)]}],
    }


async def export_original(folder: Path, options, font: Path):
    manifest = manifest_for(options)
    manifest_path = folder / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    output = folder / "export"
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(UPSTREAM / "scripts/export_pack.py"), str(manifest_path), str(output),
        "--font", str(font), "--jobs", "2",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=180)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 5)
            except asyncio.TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
        raise
    if process.returncode:
        # Local diagnostics only. No source photo or provider key is passed to this process.
        (folder / "export-error.log").write_bytes(stderr[-12000:])
        raise ValueError("原项目导出或校验未通过，请检查图集的姿势、透明边缘和文字。")
    report = json.loads(stdout.decode().strip().splitlines()[-1])
    (folder / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    gifs = sorted((output / "GIF合集").glob("*/*.gif"))
    if len(gifs) != len(options.expressions):
        raise ValueError("原项目返回的 GIF 数量不正确。")
    png_folder = folder / "PNG合集"
    png_folder.mkdir()
    pngs = []
    for gif in gifs:
        png = png_folder / (gif.stem + ".png")
        with Image.open(gif) as image:
            image.convert("RGBA").save(png)
        pngs.append(png)
    png_zip = folder / "PNG合集.zip"
    with ZipFile(png_zip, "w", ZIP_DEFLATED) as archive:
        for png in pngs:
            archive.write(png, png.name)
    return report, gifs, pngs, Path(report["zip"]), png_zip
