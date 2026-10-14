from pathlib import Path
from .config import settings

def local_path(key):
    root=Path(settings.data_dir).resolve()
    target=(root/key).resolve()
    if not target.is_relative_to(root):raise ValueError("Invalid storage key")
    return target

def client():
    import boto3
    return boto3.client("s3",endpoint_url=settings.s3_endpoint,aws_access_key_id=settings.s3_key,aws_secret_access_key=settings.s3_secret,region_name="auto")

def upload(path,key):
    if settings.s3_bucket:
        client().upload_file(str(path),settings.s3_bucket,key,ExtraArgs={"ContentType":"video/mp4"})
    return key

def signed_download(key):
    return client().generate_presigned_url("get_object",Params={"Bucket":settings.s3_bucket,"Key":key},ExpiresIn=300)
