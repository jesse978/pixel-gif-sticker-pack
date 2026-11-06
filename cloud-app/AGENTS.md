# User requirement

The user explicitly requires using WoYun520/pixel-gif-sticker-pack directly.
Do not replace or reimplement its compositor, motion presets, validation, gallery,
or ZIP export. The repository root is the original checkout, pinned by
`UPSTREAM.json`; do not modify its core files. The web service is only a thin
input/configuration/review wrapper and must invoke the original `export_pack.py`.
Run both upstream tests and wrapper integration/UI checks after relevant changes.
Do not claim example assets are newly generated or derived from a user's photo.
Do not publish or send personal photos without the user's instruction.

The user explicitly requests a fork under `jesse978` and wants future changes
committed and pushed there. The user supplied the new fork URL; GitHub confirmed
`jesse978/pixel-gif-sticker-pack` is a fork of WoYun520's repo with push access.
Push completed, tested changes to `origin`, never to `upstream`. Keep `.env`,
personal photos, generated personal outputs, and temporary runtime files out of commits.
