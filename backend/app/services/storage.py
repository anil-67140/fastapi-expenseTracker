"""Receipt file storage: validate, size-limit, sniff magic bytes, save with a random name."""
import asyncio
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import settings
from app.exceptions import BadRequestError, PayloadTooLargeError, UnsupportedMediaTypeError

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def upload_path() -> Path:
    path = Path(settings.upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _signature_matches(content_type: str, head: bytes) -> bool:
    """The Content-Type header is client-controlled, so also check the file's real first bytes."""
    if content_type == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if content_type == "application/pdf":
        return head.startswith(b"%PDF-")
    return False


async def save_receipt(file: UploadFile) -> str:
    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise UnsupportedMediaTypeError(
            f"Unsupported file type '{content_type}'. Allowed: {', '.join(ALLOWED_TYPES)}."
        )

    data = bytearray()
    while chunk := await file.read(64 * 1024):  # read in chunks so a huge upload is rejected early
        data.extend(chunk)
        if len(data) > settings.max_upload_bytes:
            raise PayloadTooLargeError(f"File exceeds the {settings.max_upload_mb} MB limit.")
    if not data:
        raise BadRequestError("The uploaded file is empty.")
    if not _signature_matches(content_type, bytes(data[:16])):
        raise UnsupportedMediaTypeError("File content does not match its declared type.")

    filename = f"{uuid4().hex}{ALLOWED_TYPES[content_type]}"  # never trust the client's filename
    await asyncio.to_thread((upload_path() / filename).write_bytes, bytes(data))  # keep the event loop free
    return filename


async def delete_receipt(filename: str | None) -> None:
    if filename:
        target = upload_path() / Path(filename).name  # .name strips any path tricks
        await asyncio.to_thread(target.unlink, missing_ok=True)
