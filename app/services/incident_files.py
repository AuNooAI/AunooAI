"""Disk storage for Brand Watcher incident file attachments.

Files live under data/incident_files/<incident_id>/<sha256><ext> (content-
addressed, so re-uploading the same bytes to the same incident dedupes on
disk). The DB row lives in bw_incident_files; the evidence-locker entry embeds
the file's sha256 in its content, so the incident hash chain covers the file
bytes transitively. There is deliberately no delete: evidence is append-only.
"""

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 25 * 1024 * 1024
_CHUNK = 1024 * 1024

# extension -> mime we trust for serving. The browser-supplied content type is
# advisory only; the extension is what gates the allowlist.
ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
    ".txt": "text/plain", ".csv": "text/csv", ".json": "application/json",
    ".html": "text/html", ".eml": "message/rfc822", ".md": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip": "application/zip",
}

STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "incident_files"


class FileValidationError(ValueError):
    """Bad filename/extension — surface as HTTP 400."""


class FileTooLargeError(ValueError):
    """Over MAX_FILE_BYTES — surface as HTTP 413."""


def sanitize_filename(name: str) -> str:
    base = os.path.basename(name or "").strip()
    base = re.sub(r"[^\w.\- ()\[\]]", "_", base, flags=re.UNICODE)
    return base[:200] or "attachment"


def validate_extension(filename: str) -> Tuple[str, str]:
    """Return (extension, served_mime); raise FileValidationError if not allowed."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise FileValidationError(f"File type '{ext or '(none)'}' not allowed. Allowed: {allowed}")
    return ext, ALLOWED_EXTENSIONS[ext]


async def save_upload(incident_id: int, upload) -> dict:
    """Stream a FastAPI UploadFile to disk with a running sha256 and size cap.

    Returns {filename, mime, size_bytes, sha256, stored_path (relative)}.
    """
    filename = sanitize_filename(upload.filename)
    ext, mime = validate_extension(filename)

    incident_dir = STORAGE_ROOT / str(incident_id)
    incident_dir.mkdir(parents=True, exist_ok=True)
    part_path = incident_dir / f".upload-{os.getpid()}-{id(upload)}.part"

    sha = hashlib.sha256()
    size = 0
    try:
        with open(part_path, "wb") as out:
            while True:
                chunk = await upload.read(_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise FileTooLargeError(
                        f"File exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB limit")
                sha.update(chunk)
                out.write(chunk)
        if size == 0:
            raise FileValidationError("Empty file")
        digest = sha.hexdigest()
        final_path = incident_dir / f"{digest}{ext}"
        os.replace(part_path, final_path)
    finally:
        if part_path.exists():
            part_path.unlink(missing_ok=True)

    return {
        "filename": filename,
        "mime": mime,
        "size_bytes": size,
        "sha256": digest,
        "stored_path": str(final_path.relative_to(STORAGE_ROOT)),
    }


def resolve_path(stored_path: str) -> Optional[Path]:
    """Absolute path for a stored file; None if it escapes the root or is missing."""
    p = (STORAGE_ROOT / stored_path).resolve()
    if not str(p).startswith(str(STORAGE_ROOT.resolve()) + os.sep):
        return None
    return p if p.is_file() else None


def file_sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            sha.update(chunk)
    return sha.hexdigest()
