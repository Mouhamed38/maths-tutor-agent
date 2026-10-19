import io
import os
from dotenv import load_dotenv

load_dotenv()

from src.storage import _client, photo_url, r2_enabled

print("R2 configuré :", r2_enabled())
_client().upload_fileobj(io.BytesIO(b"test r2"), os.environ["R2_BUCKET_NAME"], "test.txt")
print("Upload OK")
print(photo_url("test.txt", 300))