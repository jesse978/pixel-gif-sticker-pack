from contextlib import asynccontextmanager, suppress
import asyncio
from dataclasses import dataclass, field
import json
import re
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from .catalog import EXPRESSIONS
from .config import ROOT, Settings
from .images import MAX_UPLOAD, InvalidImage, decode_image, normalize_photo
from .models import PackOptions
from .provider import OpenAIImageProvider, ProviderError
from .upstream import UPSTREAM, demo_atlas, export_original, grid_for, inspect_atlas

TERMINAL = {"completed", "failed", "cancelled"}
MAX_REQUEST = MAX_UPLOAD + 512 * 1024


@dataclass
class PackJob:
    id: str
    owner: str
    folder: Path
    options: PackOptions
    mode: str
    created: float = field(default_factory=time.time)
    status: str = "generating"
    message: str = "正在生成透明姿势图集"
    error: str | None = None
    report: dict | None = None
    results: list = field(default_factory=list)
    files: dict = field(default_factory=dict)
    task: asyncio.Task | None = None


class ReviewRequest(BaseModel):
    reviewed: bool


class BodyTooLarge(Exception):
    pass


class LimitBodyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, send)
        total = 0
        started = False

        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > MAX_REQUEST:
                raise BodyTooLarge()
            return message

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except BodyTooLarge:
            if not started:
                await JSONResponse({"detail": "上传内容太大，照片最大 10 MB。"}, status_code=413)(scope, receive, send)


def create_app(settings: Settings | None = None, provider=None):
    settings = settings or Settings.from_env()
    jobs: dict[str, PackJob] = {}
    image_provider = provider or OpenAIImageProvider(settings)
    runtime = None

    def is_expired(job, now=None):
        return job.created + settings.ttl_seconds <= (time.time() if now is None else now)

    def live_jobs(owner=None):
        now = time.time()
        return [job for job in jobs.values()
                if not is_expired(job, now) and (owner is None or job.owner == owner)]

    async def remove_job(job):
        if job.task and not job.task.done():
            job.task.cancel()
            with suppress(asyncio.CancelledError):
                await job.task
        await asyncio.to_thread(shutil.rmtree, job.folder, True)
        jobs.pop(job.id, None)

    async def reap():
        while True:
            await asyncio.sleep(30)
            for job in list(jobs.values()):
                if is_expired(job):
                    await remove_job(job)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal runtime
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        runtime = tempfile.TemporaryDirectory(prefix="session-", dir=settings.data_dir)
        app.state.runtime = Path(runtime.name)
        cleaner = asyncio.create_task(reap())
        yield
        cleaner.cancel()
        with suppress(asyncio.CancelledError):
            await cleaner
        for job in list(jobs.values()):
            await remove_job(job)
        runtime.cleanup()

    app = FastAPI(title="像你 · 基于 pixel-gif-sticker-pack", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.jobs = jobs
    app.add_middleware(LimitBodyMiddleware)

    @app.middleware("http")
    async def session_and_headers(request: Request, call_next):
        owner = request.cookies.get("sticker_session", "")
        fresh = not re.fullmatch(r"[A-Za-z0-9_-]{43}", owner)
        if fresh:
            owner = secrets.token_urlsafe(32)
        request.state.owner = owner
        origin = request.headers.get("origin")
        if request.method in {"POST", "DELETE", "PUT", "PATCH"} and origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "请从本工具的网页提交请求。"}, status_code=403)
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "请求大小无效。"}, status_code=400)
        if length > MAX_REQUEST:
            return JSONResponse({"detail": "上传内容太大，照片最大 10 MB。"}, status_code=413)
        response = await call_next(request)
        # Renew the existing owner on API activity so a late-created job retains
        # its full access window. Job/file expiry is independent and never renewed.
        if fresh or request.url.path.startswith("/api/"):
            response.set_cookie("sticker_session", owner, httponly=True, samesite="strict", secure=settings.secure_cookie, max_age=settings.ttl_seconds + 300)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse({"detail": "提交的参数不正确，请检查照片、表情和文案。"}, status_code=422)

    @app.exception_handler(BodyTooLarge)
    async def too_large(request, exc):
        return JSONResponse({"detail": "上传内容太大，照片最大 10 MB。"}, status_code=413)

    def find_job(request, job_id):
        job = jobs.get(job_id)
        if not job or not secrets.compare_digest(job.owner, request.state.owner):
            raise HTTPException(404, "任务不存在或已过期，请重新生成。")
        if is_expired(job):
            raise HTTPException(410, "任务已过期。")
        return job

    def public_job(job):
        base = f"/api/jobs/{job.id}/files/"
        return {
            "id": job.id, "mode": job.mode, "status": job.status, "message": job.message,
            "error": job.error, "options": job.options.model_dump(),
            "grid": list(grid_for(len(job.options.expressions))),
            "atlas_url": base + "atlas" if "atlas" in job.files else None,
            "results": job.results,
            "gif_zip_url": base + "gif_zip" if "gif_zip" in job.files else None,
            "png_zip_url": base + "png_zip" if "png_zip" in job.files else None,
            "manifest_url": base + "manifest" if "manifest" in job.files else None,
            "verification": job.report,
            "expires_at": job.created + settings.ttl_seconds,
            "expires_in_seconds": max(0, job.created + settings.ttl_seconds - time.time()),
        }

    def new_job(request, options, mode):
        retained = live_jobs()
        owned = [j for j in retained if j.owner == request.state.owner]
        if any(j.status not in TERMINAL for j in owned):
            raise HTTPException(409, "请先完成或清除当前任务。")
        if len(owned) >= 4 or len(retained) >= settings.max_stored_jobs:
            raise HTTPException(429, "保留的任务已达到上限，请清除旧任务后再试。")
        if sum(j.status not in TERMINAL for j in retained) >= settings.max_active_jobs:
            raise HTTPException(429, "服务正在处理其他任务，请稍后再试。")
        job_id = secrets.token_urlsafe(18)
        folder = Path(runtime.name) / job_id
        folder.mkdir(mode=0o700)
        job = PackJob(job_id, request.state.owner, folder, options, mode)
        jobs[job_id] = job
        return job

    async def prepare(job, source=None):
        try:
            if job.mode == "demo":
                image = await asyncio.to_thread(demo_atlas, job.options.expressions)
            elif job.mode == "atlas":
                image = decode_image(source)
            else:
                normalized = await asyncio.to_thread(normalize_photo, source)
                source = None
                image = await image_provider.edit_atlas(normalized, job.options.expressions, job.options.style, grid_for(len(job.options.expressions)))
                normalized = None
            inspect_atlas(image, len(job.options.expressions))
            await asyncio.to_thread(image.save, job.folder / "atlas.png", "PNG")
            job.files["atlas"] = job.folder / "atlas.png"
            job.status = "review"
            job.message = "请检查每格人物、表情和透明边缘，确认后使用原项目导出"
        except asyncio.CancelledError:
            job.status = "cancelled"
            raise
        except (InvalidImage, ProviderError) as exc:
            job.status = "failed"
            job.error = str(exc)
            job.message = "图集准备未完成"
        except Exception:
            job.status = "failed"
            job.error = "处理图集失败，请检查图片格式和服务端配置。"
        finally:
            source = None

    async def run_export(job):
        try:
            report, gifs, pngs, bundle, png_zip = await export_original(job.folder, job.options, settings.font_path)
            base = f"/api/jobs/{job.id}/files/"
            for i, (gif, png, choice) in enumerate(zip(gifs, pngs, job.options.expressions)):
                job.files[f"gif_{i}"] = gif
                job.files[f"png_{i}"] = png
                job.results.append({"id": choice.id, "caption": choice.caption,
                                    "gif_url": base + f"gif_{i}", "png_url": base + f"png_{i}"})
            job.files.update(gif_zip=bundle, png_zip=png_zip, manifest=job.folder / "manifest.json")
            # Remove local paths from the public report.
            job.report = {k: v for k, v in report.items() if k != "zip"}
            job.status = "completed"
            job.message = "原项目导出完成，透明度、边距、循环和 ZIP 校验通过"
        except asyncio.CancelledError:
            job.status = "cancelled"
            raise
        except (ValueError, asyncio.TimeoutError) as exc:
            job.status = "failed"
            job.error = str(exc) if isinstance(exc, ValueError) else "导出超时，请减少表情数量。"
        except Exception:
            job.status = "failed"
            job.error = "原项目导出未完成，请检查服务器日志。"

    @app.get("/api/config")
    async def configuration(request: Request):
        owned = live_jobs(request.state.owner)
        latest = max(owned, key=lambda j: j.created) if owned else None
        return {"provider_configured": bool(settings.api_key), "provider_host": settings.provider_host,
                "model": settings.model, "ttl_minutes": settings.ttl_seconds // 60,
                "ttl_seconds": settings.ttl_seconds,
                "expressions": EXPRESSIONS, "latest_job": public_job(latest) if latest else None,
                "upstream": json.loads((ROOT / "UPSTREAM.json").read_text()),
                "max_count": 8, "max_upload_mb": 10}

    @app.post("/api/jobs", status_code=202)
    async def create_job(request: Request, options: str = Form(...), mode: Literal["photo", "atlas"] = Form("photo"), source: UploadFile = File(...)):
        try:
            parsed = PackOptions.model_validate_json(options)
        except ValidationError:
            raise HTTPException(422, "请选择 1–8 个表情，每条文案 1–12 字且不能重复。")
        if not parsed.consent:
            raise HTTPException(422, "请确认拥有素材使用权，并同意本次处理。")
        if mode == "photo" and not settings.api_key:
            raise HTTPException(503, "尚未配置图像服务。请在服务端设置 OPENAI_API_KEY，或导入已有透明图集。")
        raw = await source.read(MAX_UPLOAD + 1)
        await source.close()
        try:
            if mode == "photo":
                decode_image(raw, photo=True)
            else:
                inspect_atlas(decode_image(raw, photo=True), len(parsed.expressions))
        except InvalidImage as exc:
            raise HTTPException(422, str(exc))
        job = new_job(request, parsed, mode)
        job.task = asyncio.create_task(prepare(job, raw))
        return public_job(job)

    @app.post("/api/demo", status_code=202)
    async def create_demo(request: Request, options: PackOptions):
        # These are pixel examples from upstream, never photo-derived AI results.
        options = options.model_copy(update={"style": "pixel"})
        job = new_job(request, options, "demo")
        job.message = "正在载入开源项目示例图集（不调用 AI）"
        job.task = asyncio.create_task(prepare(job))
        return public_job(job)

    @app.get("/api/jobs/{job_id}")
    async def get_job(request: Request, job_id: str):
        return public_job(find_job(request, job_id))

    @app.post("/api/jobs/{job_id}/export", status_code=202)
    async def export_job(request: Request, job_id: str, review: ReviewRequest):
        job = find_job(request, job_id)
        if job.status != "review":
            raise HTTPException(409, "当前图集不能导出。")
        if not review.reviewed:
            raise HTTPException(422, "请先检查图集中的人物和表情。")
        job.status = "exporting"
        job.message = "正在调用开源项目 export_pack.py 合成并校验 GIF"
        job.task = asyncio.create_task(run_export(job))
        return public_job(job)

    @app.get("/api/jobs/{job_id}/files/{key}")
    async def get_file(request: Request, job_id: str, key: str):
        job = find_job(request, job_id)
        path = job.files.get(key)
        if not path or not path.is_file():
            raise HTTPException(404, "文件不存在。")
        media = {".png": "image/png", ".gif": "image/gif", ".zip": "application/zip", ".json": "application/json"}.get(path.suffix)
        disposition = "attachment" if path.suffix in {".zip", ".json"} else "inline"
        return FileResponse(path, media_type=media, filename=path.name, content_disposition_type=disposition)

    @app.delete("/api/jobs/{job_id}")
    async def delete_job(request: Request, job_id: str):
        await remove_job(find_job(request, job_id))
        return {"deleted": True}

    @app.delete("/api/jobs")
    async def delete_all(request: Request):
        for job in list(jobs.values()):
            if job.owner == request.state.owner:
                await remove_job(job)
        return {"deleted": True}

    @app.get("/healthz")
    async def health():
        return {"status": "ok", "engine": "pixel-gif-sticker-pack", "provider_configured": bool(settings.api_key)}

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "web/index.html", media_type="text/html")

    app.mount("/assets", StaticFiles(directory=ROOT / "web/assets"), name="assets")
    return app


app = create_app()
