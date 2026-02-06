"""
File Storage Service - Local VPS storage for file uploads.

Handles image uploads with validation and secure filename generation.
"""

import logging
import uuid
import os
import aiofiles
from typing import Optional
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

from shared.settings import settings

logger = logging.getLogger(__name__)

# Allowed image types and max size
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class FileStorageService:
    """
    Service for uploading files to local VPS storage.

    Handles:
    - File validation (type, size)
    - Secure filename generation
    - Directory creation
    - URL generation
    """

    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        self.base_url = settings.UPLOAD_BASE_URL
        self.max_size = settings.MAX_UPLOAD_SIZE

    async def upload_profile_image(
        self,
        file: UploadFile,
        user_id: str
    ) -> Optional[str]:
        """
        Uploads a profile image to local storage.

        Args:
            file: FastAPI UploadFile object
            user_id: UUID of the user (used for folder organization)

        Returns:
            Public URL of the uploaded image, or None if failed

        Raises:
            ValueError: If file validation fails
        """
        # Validate content type
        content_type = file.content_type
        if content_type not in ALLOWED_CONTENT_TYPES:
            allowed = ", ".join(ALLOWED_CONTENT_TYPES.keys())
            raise ValueError(f"Tipo de archivo no permitido. Permitidos: {allowed}")

        # Read file content
        content = await file.read()

        # Validate file size
        if len(content) > self.max_size:
            max_mb = self.max_size // (1024 * 1024)
            raise ValueError(f"El archivo excede el tamano maximo de {max_mb} MB")

        # Generate secure filename
        extension = ALLOWED_CONTENT_TYPES[content_type]
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{timestamp}_{unique_id}{extension}"

        # Create directory structure
        user_dir = Path(self.upload_dir) / "profiles" / user_id
        user_dir.mkdir(parents=True, exist_ok=True)

        file_path = user_dir / filename

        try:
            # Write file to disk
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(content)

            # Generate URL
            relative_path = f"profiles/{user_id}/{filename}"
            url = f"{self.base_url}/{relative_path}"

            logger.info(f"[FILE_STORAGE] Uploaded profile image: {relative_path}")
            return url

        except Exception as e:
            logger.error(f"[FILE_STORAGE] Upload failed: {e}")
            # Clean up partial file if exists
            if file_path.exists():
                file_path.unlink()
            raise ValueError("Error al guardar la imagen. Intente nuevamente.")

    async def delete_file(self, file_url: str) -> bool:
        """
        Deletes a file from local storage by URL.

        Args:
            file_url: Full URL of the file to delete

        Returns:
            True if deleted, False otherwise
        """
        try:
            # Extract relative path from URL
            if not file_url.startswith(self.base_url):
                logger.warning(f"[FILE_STORAGE] URL not from this storage: {file_url}")
                return False

            relative_path = file_url.replace(f"{self.base_url}/", "")
            file_path = Path(self.upload_dir) / relative_path

            if file_path.exists():
                file_path.unlink()
                logger.info(f"[FILE_STORAGE] Deleted file: {relative_path}")
                return True

            logger.warning(f"[FILE_STORAGE] File not found: {relative_path}")
            return False

        except Exception as e:
            logger.error(f"[FILE_STORAGE] Delete failed: {e}")
            return False


# Singleton instance
file_storage_service = FileStorageService()
