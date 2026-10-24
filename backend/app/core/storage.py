# app/storage.py
import boto3
from botocore.client import Config
import os

from app.core.config import get_settings

def get_minio_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint_url,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1"        # MinIO ignores this but boto3 requires it
    )

def init_buckets():
    """Call this once at app startup to ensure buckets exist."""
    client = get_minio_client()
    for bucket in [
        os.getenv("MINIO_BUCKET_SPRINTS"),
        os.getenv("MINIO_BUCKET_REPORTS")
        , os.getenv("MINIO_BUCKET_RAW"), os.getenv("MINIO_BUCKET_DOCUMENTS", "project-documents"),
        get_settings().minio_bucket_audit_archive,
    ]:
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:
            if not bucket:
                continue
            client.create_bucket(Bucket=bucket)
            print(f"Created bucket: {bucket}")

def upload_object(
    bucket: str,
    key: str,
    data: bytes,
    mime_type: str = "application/octet-stream",
    metadata: dict[str, str] | None = None,
):
    client = get_minio_client()
    request = {"Bucket": bucket, "Key": key, "Body": data, "ContentType": mime_type}
    if metadata:
        request["Metadata"] = metadata
    client.put_object(**request)
    return key

def download_object(bucket: str, key: str) -> bytes:
    client = get_minio_client()
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def head_object(bucket: str, key: str) -> dict:
    client = get_minio_client()
    return client.head_object(Bucket=bucket, Key=key)


def delete_object(bucket: str, key: str) -> None:
    client = get_minio_client()
    client.delete_object(Bucket=bucket, Key=key)

def get_presigned_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    """Generate a temporary download URL — useful for frontend file access."""
    client = get_minio_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in
    )

def list_objects(bucket: str, prefix: str = "") -> list[dict]:
    client = get_minio_client()
    paginator = client.get_paginator("list_objects_v2")
    objects = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        objects.extend(page.get("Contents", []))
    return objects
    
    # Add at the bottom of app/core/storage.py

class StorageService:
    def init_buckets(self):
        init_buckets()

    def upload(self, bucket, key, data, mime_type="application/octet-stream", metadata=None):
        return upload_object(bucket, key, data, mime_type, metadata)

    def download(self, bucket, key):
        return download_object(bucket, key)

    def head(self, bucket, key):
        return head_object(bucket, key)

    def delete(self, bucket, key):
        return delete_object(bucket, key)

    def list(self, bucket, prefix=""):
        return list_objects(bucket, prefix)

    def presigned_url(self, bucket, key, expires_in=3600):
        return get_presigned_url(bucket, key, expires_in)

# This is the instance main.py imports
storage = StorageService()