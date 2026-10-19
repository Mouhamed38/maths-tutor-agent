import os
import boto3
from botocore.client import Config


def r2_enabled():
    keys = ("R2_ENDPOINT_URL", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")
    return all(os.environ.get(k) for k in keys)


def _client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def save_photo(file_storage, filename, local_folder):
    if r2_enabled():
        _client().upload_fileobj(
            file_storage.stream,
            os.environ["R2_BUCKET_NAME"],
            filename,
            ExtraArgs={"ContentType": file_storage.mimetype},
        )
    else:
        file_storage.save(os.path.join(local_folder, filename))


def photo_url(filename, expires=3600):
    if r2_enabled():
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": os.environ["R2_BUCKET_NAME"], "Key": filename},
            ExpiresIn=expires,
        )
    return f"/static/uploads/{filename}"