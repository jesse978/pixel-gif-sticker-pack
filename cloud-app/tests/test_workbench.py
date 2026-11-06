import asyncio
import base64
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
import unittest
from zipfile import ZipFile

from fastapi.testclient import TestClient
import httpx
from PIL import Image
from pydantic import ValidationError

from app.config import ROOT, Settings
from app.images import MAX_UPLOAD, InvalidImage, decode_image, normalize_photo
from app.main import create_app
from app.models import PackOptions
from app.provider import OpenAIImageProvider, ProviderError
from app.upstream import demo_atlas, grid_for


def pack_options(count=2, style="real"):
    return {"expressions": [{"id": "happy", "caption": "开心"}, {"id": "ok", "caption": "收到"}, {"id": "love", "caption": "爱你"}][:count],
            "style": style, "motion": "breathe", "ink": "dark", "consent": True}


def image_bytes(image):
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(data_dir=Path(self.temp.name))
        self.app = create_app(self.settings)
        self.client = self.enterContext(TestClient(self.app))

    def wait_for(self, job_id, expected):
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/jobs/{job_id}")
            self.assertEqual(response.status_code, 200, response.text)
            job = response.json()
            if job["status"] in expected:
                return job
            if job["status"] == "failed":
                self.fail(f"Unexpected failure: {job['error']}")
            time.sleep(0.05)
        self.fail("Job did not finish within 40 seconds")

    def create_demo(self, count=2):
        response = self.client.post("/api/demo", json=pack_options(count))
        self.assertEqual(response.status_code, 202, response.text)
        return self.wait_for(response.json()["id"], {"review"})

    def test_configuration_is_honest_and_does_not_expose_credentials(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["provider_configured"])
        self.assertEqual(response.json()["upstream"]["entrypoint"], "../scripts/export_pack.py")
        self.assertNotIn("api_key", response.json())
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_photo_generation_without_key_returns_503(self):
        photo = image_bytes(Image.new("RGB", (180, 180), "gray"))
        response = self.client.post("/api/jobs", data={"options": json.dumps(pack_options()), "mode": "photo"}, files={"source": ("portrait.png", photo, "image/png")})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(self.app.state.jobs), 0)

    def test_consent_is_required(self):
        opts = pack_options(); opts["consent"] = False
        response = self.client.post("/api/jobs", data={"options": json.dumps(opts)}, files={"source": ("photo.png", b"irrelevant", "image/png")})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.app.state.jobs), 0)

    def test_real_upstream_export_and_png_zip_integrity(self):
        job = self.create_demo()
        blocked = self.client.post(f"/api/jobs/{job['id']}/export", json={"reviewed": False})
        self.assertEqual(blocked.status_code, 422)
        response = self.client.post(f"/api/jobs/{job['id']}/export", json={"reviewed": True})
        self.assertEqual(response.status_code, 202)
        job = self.wait_for(job["id"], {"completed"})
        self.assertEqual(job["mode"], "demo")
        self.assertEqual(job["verification"]["gif_count"], 2)
        self.assertEqual(job["verification"]["render_style"], "pixel")
        self.assertGreaterEqual(job["verification"]["unique_frame_min"], 4)
        archive = ZipFile(BytesIO(self.client.get(job["gif_zip_url"]).content))
        self.assertIsNone(archive.testzip())
        self.assertEqual(len([name for name in archive.namelist() if name.endswith('.gif')]), 2)
        self.assertIn("动图浏览.html", archive.namelist())
        self.assertFalse(any('atlas' in name or 'reference' in name for name in archive.namelist()))
        for result in job["results"]:
            with Image.open(BytesIO(self.client.get(result["gif_url"]).content)) as gif:
                self.assertEqual(gif.size, (320, 320)); self.assertEqual(gif.n_frames, 24)
                self.assertEqual(gif.info["loop"], 0)
                self.assertEqual(gif.info["duration"], 80)
                self.assertEqual(gif.convert("RGBA").getchannel("A").getextrema(), (0, 255))
                first = gif.convert("RGBA").copy()
            with Image.open(BytesIO(self.client.get(result["png_url"]).content)) as png:
                self.assertEqual(png.tobytes(), first.tobytes())
        png_archive = ZipFile(BytesIO(self.client.get(job["png_zip_url"]).content))
        self.assertEqual(len(png_archive.namelist()), 2)
        self.assertIsNone(png_archive.testzip())
        manifest = self.client.get(job["manifest_url"]).json()
        self.assertEqual(manifest["groups"][0]["grid"], [2, 1])

    def test_atlas_import_uses_hd_upstream_path_without_provider(self):
        opts = PackOptions.model_validate(pack_options(1))
        atlas = demo_atlas(opts.expressions)
        response = self.client.post("/api/jobs", data={"options": opts.model_dump_json(), "mode": "atlas"}, files={"source": ("../unexpected.png", image_bytes(atlas), "image/png")})
        self.assertEqual(response.status_code, 202, response.text)
        job = self.wait_for(response.json()["id"], {"review"})
        self.client.post(f"/api/jobs/{job['id']}/export", json={"reviewed": True})
        job = self.wait_for(job["id"], {"completed"})
        self.assertEqual(job["mode"], "atlas")
        self.assertEqual(job["verification"]["size"], 512)
        with Image.open(BytesIO(self.client.get(job["results"][0]["gif_url"]).content)) as gif:
            self.assertEqual(gif.size, (512, 512))
        self.assertFalse((Path(self.temp.name) / 'unexpected.png').exists())

    def test_another_session_cannot_read_or_delete_job_or_files(self):
        job = self.create_demo(1)
        other = TestClient(self.app)
        self.assertEqual(other.get(f"/api/jobs/{job['id']}").status_code, 404)
        self.assertEqual(other.get(job["atlas_url"]).status_code, 404)
        self.assertEqual(other.delete(f"/api/jobs/{job['id']}").status_code, 404)
        self.assertEqual(self.client.get(job["atlas_url"]).status_code, 200)

    def test_clear_removes_files_and_blocks_download(self):
        job = self.create_demo(1)
        folder = self.app.state.jobs[job["id"]].folder
        self.assertTrue((folder / "atlas.png").exists())
        self.assertEqual(self.client.delete("/api/jobs").status_code, 200)
        self.assertFalse(folder.exists())
        self.assertEqual(self.client.get(job["atlas_url"]).status_code, 404)

    def test_unreviewed_job_prevents_duplicate_active_requests(self):
        self.create_demo(1)
        response = self.client.post("/api/demo", json=pack_options(1))
        self.assertEqual(response.status_code, 409)

    def test_expired_job_is_not_accessible(self):
        job = self.create_demo(1)
        self.app.state.jobs[job["id"]].created -= 3700
        self.assertEqual(self.client.get(job["atlas_url"]).status_code, 410)

    def test_opaque_and_empty_atlases_are_rejected(self):
        for im in [Image.new("RGBA", (200, 200), "white"), Image.new("RGBA", (200, 200))]:
            response = self.client.post("/api/jobs", data={"options": json.dumps(pack_options(1)), "mode": "atlas"}, files={"source": ("atlas.png", image_bytes(im), "image/png")})
            self.assertEqual(response.status_code, 422)

    def test_bad_images_and_parameter_validation(self):
        response = self.client.post("/api/jobs", data={"options": json.dumps(pack_options(1)), "mode": "atlas"}, files={"source": ("fake.png", b"not an image", "image/png")})
        self.assertEqual(response.status_code, 422)
        for invalid in [[], [{"id": "unknown", "caption": "a"}], [{"id": "happy", "caption": "\n"}]]:
            data = pack_options(); data["expressions"] = invalid
            self.assertEqual(self.client.post("/api/demo", json=data).status_code, 422)

    def test_cross_origin_writes_are_rejected(self):
        response = self.client.post("/api/demo", json=pack_options(1), headers={"origin": "https://unrelated.example"})
        self.assertEqual(response.status_code, 403)

    def test_upload_limit_is_enforced(self):
        response = self.client.post("/api/demo", content=b'x' * (MAX_UPLOAD + 600_000))
        self.assertEqual(response.status_code, 413)


class PhotoPipelineTests(unittest.TestCase):
    def test_photo_is_oriented_and_metadata_is_stripped(self):
        source = Image.new("RGB", (128, 256), "#808080")
        exif = source.getexif(); exif[274] = 6; exif[315] = "private metadata"
        buffer = BytesIO(); source.save(buffer, "JPEG", exif=exif)
        normalized = normalize_photo(buffer.getvalue())
        with Image.open(BytesIO(normalized)) as image:
            self.assertEqual(image.size, (256, 128))
            self.assertFalse(dict(image.getexif()))
            self.assertNotIn('exif', image.info)
        self.assertNotIn(b"private metadata", normalized)

    def test_size_and_format_checks(self):
        with self.assertRaises(InvalidImage): decode_image(b'')
        with self.assertRaises(InvalidImage): normalize_photo(image_bytes(Image.new('RGB', (127, 140))))
        with self.assertRaises(InvalidImage): decode_image(b'x' * (MAX_UPLOAD + 1), photo=True)

    def test_duplicate_captions_cannot_reach_upstream_assertion(self):
        data = pack_options(); data['expressions'][1]['caption'] = '开心'
        with self.assertRaises(ValidationError): PackOptions.model_validate(data)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_multipart_request_uses_real_reference_and_atlas_prompt(self):
        choices = PackOptions.model_validate(pack_options()).expressions
        result_image = demo_atlas(choices)
        sent = []
        def handler(request):
            sent.append(request)
            self.assertEqual(request.url.path, '/v1/images/edits')
            self.assertEqual(request.headers['authorization'], 'Bearer unit-test-placeholder')
            body = request.content
            self.assertIn(b'name="image[]"', body)
            self.assertIn(b'reference-pixels', body)
            self.assertIn(b'input_fidelity', body)
            self.assertIn(b'high', body)
            self.assertIn(b'Cell 1', body)
            self.assertIn(b'Cell 2', body)
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(image_bytes(result_image)).decode()}]})
        provider = OpenAIImageProvider(Settings(api_key='unit-test-placeholder'), transport=httpx.MockTransport(handler))
        image = await provider.edit_atlas(b'reference-pixels', choices, 'real', (2, 1))
        self.assertEqual(image.size, result_image.size)
        self.assertEqual(len(sent), 1)

    async def test_new_models_omit_unsupported_input_fidelity(self):
        def handler(request):
            self.assertNotIn(b'input_fidelity', request.content)
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(image_bytes(Image.new('RGBA', (200, 200)))).decode()}]})
        provider = OpenAIImageProvider(Settings(api_key='test', model='gpt-image-2'), transport=httpx.MockTransport(handler))
        await provider.edit_atlas(b'test', PackOptions.model_validate(pack_options(1)).expressions, 'real', (1, 1))

    async def test_upstream_errors_do_not_echo_secrets_and_do_not_retry(self):
        attempts = []
        def handler(request):
            attempts.append(1)
            return httpx.Response(401, json={'error': {'message': 'secret-key reference-photo'}})
        provider = OpenAIImageProvider(Settings(api_key='test'), transport=httpx.MockTransport(handler))
        with self.assertRaises(ProviderError) as error:
            await provider.edit_atlas(b'photo', PackOptions.model_validate(pack_options(1)).expressions, 'real', (1, 1))
        self.assertNotIn('secret-key', str(error.exception))
        self.assertEqual(len(attempts), 1)

    async def test_invalid_provider_result_has_no_photo_fallback(self):
        provider = OpenAIImageProvider(Settings(api_key='test'), transport=httpx.MockTransport(lambda request: httpx.Response(200, json={'data': [{'b64_json': 'not base64!'}]})))
        with self.assertRaises(ProviderError):
            await provider.edit_atlas(b'photo', PackOptions.model_validate(pack_options(1)).expressions, 'real', (1, 1))

    async def test_configured_photo_request_runs_through_review_and_original_export(self):
        choices = PackOptions.model_validate(pack_options(1)).expressions
        class FixtureProvider:
            calls = []
            async def edit_atlas(self, photo, requested, style, grid):
                self.calls.append((photo, requested, style, grid))
                return demo_atlas(choices)
        fake = FixtureProvider()
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Settings(api_key='test-only', data_dir=Path(folder)), provider=fake)
            def execute():
                with TestClient(app) as client:
                    photo = image_bytes(Image.new('RGB', (200, 200), '#888888'))
                    response = client.post('/api/jobs', data={'options': json.dumps(pack_options(1)), 'mode': 'photo'}, files={'source': ('photo.png', photo, 'image/png')})
                    self.assertEqual(response.status_code, 202)
                    job = response.json()
                    deadline = time.monotonic()+30
                    while time.monotonic() < deadline:
                        job=client.get(f"/api/jobs/{job['id']}").json()
                        if job['status']=='review': break
                        self.assertNotEqual(job['status'], 'failed', job)
                        time.sleep(.05)
                    self.assertEqual(job['status'], 'review')
                    self.assertEqual(len(fake.calls), 1)
                    self.assertEqual(fake.calls[0][2], 'real')
                    client.post(f"/api/jobs/{job['id']}/export", json={'reviewed':True})
                    while time.monotonic() < deadline:
                        job=client.get(f"/api/jobs/{job['id']}").json()
                        if job['status']=='completed': break
                        self.assertNotEqual(job['status'], 'failed', job)
                        time.sleep(.05)
                    self.assertEqual(job['status'], 'completed')
                    self.assertEqual(job['verification']['size'], 512)
            await asyncio.to_thread(execute)


if __name__ == '__main__':
    unittest.main()
