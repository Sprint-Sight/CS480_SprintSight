# app/storage.py
import boto3
from botocore.client import Config
import os

def get_minio_client():
    return boto3.client(
        "s3",
        endpoint_url=f"http://{os.getenv('MINIO_ENDPOINT')}",
        aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"),
        config=Config(signature_version="s3v4"),
        region_name="us-east-1"        # MinIO ignores this but boto3 requires it
    )

def init_buckets():
    """Call this once at app startup to ensure buckets exist."""
    client = get_minio_client()
    for bucket in [
        os.getenv("MINIO_BUCKET_SPRINTS"),
        os.getenv("MINIO_BUCKET_REPORTS")
    ]:
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:
            client.create_bucket(Bucket=bucket)
            print(f"Created bucket: {bucket}")

def upload_object(bucket: str, key: str, data: bytes, mime_type: str = "application/octet-stream"):
    client = get_minio_client()
    client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=mime_type)
    return key

def download_object(bucket: str, key: str) -> bytes:
    client = get_minio_client()
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()

def get_presigned_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    """Generate a temporary download URL — useful for frontend file access."""
    client = get_minio_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in
    )
    
    # Add at the bottom of app/core/storage.py

class StorageService:
    def init_buckets(self):
        init_buckets()

    def upload(self, bucket, key, data, mime_type="application/octet-stream"):
        return upload_object(bucket, key, data, mime_type)

    def download(self, bucket, key):
        return download_object(bucket, key)

    def presigned_url(self, bucket, key, expires_in=3600):
        return get_presigned_url(bucket, key, expires_in)

# This is the instance main.py imports
storage = StorageService()