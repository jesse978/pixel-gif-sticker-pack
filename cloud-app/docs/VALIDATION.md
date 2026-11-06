# Verification record

Validated on 2026-11-06 in a managed Linux cloud environment, Python 3.12.14,
Pillow 12.3.0, FastAPI 0.141.1, Playwright 1.62.0 and system Chromium.

## Automated checks

- Upstream: `python3 -m unittest discover -s tests -v` from the repository root:
  **6 passed**. No changes to upstream scripts, references, `SKILL.md`, or `LICENSE`.
- Cloud wrapper: `python3 -m unittest discover -s tests -v` from `cloud-app/`:
  **21 passed**. Includes real subprocess execution of the original exporter in
  pixel and HD modes, ZIP integrity, GIF frame timing/loop/alpha, exact first-frame
  PNG extraction, review requirement, session isolation, deletion, expiry,
  invalid/opaque uploads, consent, missing-key handling, EXIF removal and dimensions.
- Provider requests checked using `httpx.MockTransport`: exact reference bytes,
  multipart `image[]`, atlas cell prompts, `input_fidelity` compatibility,
  redacted errors, no automatic retry, and no original-photo/example fallback.
  A fixture-provider integration test covers the complete photo request → atlas review
  → original HD exporter path without making a billable API request.
- JavaScript syntax and Python compilation passed.

## Browser checks

`python3 scripts/check_ui.py --url http://127.0.0.1:8000`:

- Desktop at 1440px and mobile at 390px; no horizontal overflow.
- Original example GIFs load; file selection is local and performs no POST.
- Missing image-service key is visible; photo generation is disabled.
- Expression count limit, editable captions and dialogs work.
- Six-pose example → manual atlas review → original CLI export → downloadable ZIP
  with six valid GIFs and the original offline gallery.
- Static PNG preview and individual downloads work.
- Mobile atlas import exports 512px HD; page refresh restores the same job.
- A different browser session cannot read result files; clearing removes them.
- No JavaScript page errors.

Screenshots and a replay-only example ZIP are retained in ignored `artifacts/` for
internal inspection. They are not personal-photo outputs and are not uploaded to
Library. A technical check is not visual/user acceptance of a generated person.

## Limits that remain

No personal photo or image-model key was supplied. No billable generation was
performed. Real API access, actual likeness preservation, hands/face quality and
atlas layout must be accepted with a user-authorized photo and configured key.
The UI uses original light-motion presets, not new per-frame character actions.

The development server and browser checks run inside the cloud workspace. No
public website deployment, paid service purchase, API-key creation, or personal
photo publication was performed. The authorized GitHub fork is the source handoff;
the README contains startup instructions.
