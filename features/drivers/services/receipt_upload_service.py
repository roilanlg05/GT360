"""
Receipt upload service - Handles file uploads for receipts and W-9 documents.
Supports local storage (dev) and S3 (production).
"""

import aiofiles
import os
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4
from fastapi import UploadFile, HTTPException

from shared.settings import settings


# Configuration
UPLOAD_DIR = Path("uploads")
RECEIPTS_DIR = UPLOAD_DIR / "receipts"
W9_DIR = UPLOAD_DIR / "w9"

# File size limits (in bytes)
MAX_RECEIPT_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_W9_SIZE = 5 * 1024 * 1024  # 5 MB

# Allowed file types
RECEIPT_ALLOWED_TYPES = ["image/jpeg", "image/png", "application/pdf"]
W9_ALLOWED_TYPES = ["application/pdf"]


def ensure_upload_dirs():
    """Create upload directories if they don't exist."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    W9_DIR.mkdir(parents=True, exist_ok=True)


def get_file_extension(filename: str) -> str:
    """Extract file extension from filename."""
    return filename.split('.')[-1].lower() if '.' in filename else ''


def validate_file_size(file: UploadFile, max_size: int, file_type: str):
    """
    Validate file size.

    Args:
        file: Uploaded file
        max_size: Maximum size in bytes
        file_type: Type description for error message

    Raises:
        HTTPException: If file is too large
    """
    # Note: file.size might be None, so we'll check during read
    # This is a basic check - actual size validation happens during read
    pass


def validate_file_type(file: UploadFile, allowed_types: list, file_type: str):
    """
    Validate file content type.

    Args:
        file: Uploaded file
        allowed_types: List of allowed MIME types
        file_type: Type description for error message

    Raises:
        HTTPException: If file type is not allowed
    """
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {file_type} file type. Allowed: {', '.join(allowed_types)}"
        )


async def upload_receipt_photo(
    file: UploadFile,
    expense_id: UUID
) -> str:
    """
    Upload a receipt photo.

    Args:
        file: Uploaded file
        expense_id: Expense UUID (used as filename)

    Returns:
        URL or path to uploaded file

    Raises:
        HTTPException: If upload fails or validation fails
    """
    # Validate file type
    validate_file_type(file, RECEIPT_ALLOWED_TYPES, "receipt")

    # Ensure upload directory exists
    ensure_upload_dirs()

    # Generate filename
    file_extension = get_file_extension(file.filename or "")
    if not file_extension:
        file_extension = "jpg"  # default

    filename = f"{expense_id}.{file_extension}"
    file_path = RECEIPTS_DIR / filename

    try:
        # Read file content
        content = await file.read()

        # Validate size
        if len(content) > MAX_RECEIPT_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"Receipt file too large (max {MAX_RECEIPT_SIZE / 1024 / 1024}MB)"
            )

        # Write file
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)

        # Return URL (relative path for now)
        # In production, this would be an S3 URL
        return f"/uploads/receipts/{filename}"

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload receipt: {str(e)}"
        )


async def upload_w9_document(
    file: UploadFile,
    driver_id: UUID
) -> str:
    """
    Upload a W-9 document.

    Args:
        file: Uploaded file
        driver_id: Driver UUID (used as filename)

    Returns:
        URL or path to uploaded file

    Raises:
        HTTPException: If upload fails or validation fails
    """
    # Validate file type
    validate_file_type(file, W9_ALLOWED_TYPES, "W-9")

    # Ensure upload directory exists
    ensure_upload_dirs()

    # Generate filename
    filename = f"{driver_id}.pdf"
    file_path = W9_DIR / filename

    try:
        # Read file content
        content = await file.read()

        # Validate size
        if len(content) > MAX_W9_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"W-9 file too large (max {MAX_W9_SIZE / 1024 / 1024}MB)"
            )

        # Write file
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)

        # Return URL (relative path for now)
        return f"/uploads/w9/{filename}"

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload W-9: {str(e)}"
        )


async def delete_file(file_url: str) -> bool:
    """
    Delete an uploaded file.

    Args:
        file_url: URL or path to file

    Returns:
        True if deleted, False if not found
    """
    # Extract filename from URL
    if file_url.startswith("/uploads/"):
        file_path = Path(file_url.lstrip("/"))

        try:
            if file_path.exists():
                os.remove(file_path)
                return True
        except Exception:
            pass

    return False


# TODO: S3 upload functions for production
# Uncomment and configure when ready to use S3

"""
import boto3
from botocore.exceptions import ClientError

s3_client = boto3.client('s3',
    aws_access_key_id=settings.AWS_ACCESS_KEY,
    aws_secret_access_key=settings.AWS_SECRET_KEY,
    region_name=settings.AWS_REGION
)

async def upload_to_s3(
    file: UploadFile,
    bucket: str,
    key: str
) -> str:
    '''Upload file to S3.'''
    try:
        content = await file.read()

        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=file.content_type,
            ServerSideEncryption='AES256'
        )

        url = f"https://{bucket}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
        return url

    except ClientError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload to S3: {str(e)}"
        )
"""
