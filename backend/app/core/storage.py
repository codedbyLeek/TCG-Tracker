"""Upload card images to Cloudflare R2, migrating them off external CDNs."""


import logging
import mimetypes
from pathlib import Path
from urllib.parse import urlparse


import boto3
import httpx
from botocore.exceptions import ClientError


from app.core.config import settings


logger = logging.getLogger(__name__)


_client = boto3.client(
    "s3",
    endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
    region_name="auto",
)


def _guess_extension(content_type: str | None, source_url: str) -> str:
    """Pick a file extension from the response Content-Type, falling back to the URL path."""
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if ext:
            return ext
        url_ext = Path(urlparse(source_url).path).suffix
        return url_ext if url_ext else ".jpg"
    


def _object_exists(key: str) -> bool:
    """Check whether this exact key already exists in the R2 bucket."""
    try:
        _client.head_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False
        raise



def upload_image_to_r2(source_url: str, game: str, external_id: str) -> str:
    """Download a card image from its source CDN and uplaod it to R2, returning the new public URL.
    
    Idempotent: if the image already exists in R2, skips the download/upload entirely."""

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        try:
            head = client.head(source_url)
            content_type = head.headers.get("content-type") if head.status_code < 400 else None
        except httpx.HTTPError:
            content_type = None


        extension = _guess_extension(content_type, source_url)
        key = f"{game}/{external_id}{extension}"

        if _object_exists(key):
            logger.info("image already in R2, skipping: %s", key)
            return f"{settings.R2_PUBLIC_URL}/{key}"
        
        response = client.get(source_url)
        response.raise_for_status()
        image_bytes = response.content
        content_type = response.headers.get("content-type", content_type or "image/jpeg")

    _client.put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        Body=image_bytes,
        ContentType=content_type,
    )

    logger.info("Upload image to R2: %s", key)
    return f"{settings.R2_PUBLIC_URL}/{key}"