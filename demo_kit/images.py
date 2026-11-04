"""Image blob copy + URL rewrite.

Image-bearing fields store full public URLs into the prod bucket
(`https://storage.googleapis.com/<bucket>/<name>`). On refresh we copy each
referenced blob server-side (copy_blob — no download round trip) into the
demo bucket under the same object name and rewrite the stored URL, so demo
uploads/deletes operate on demo objects and can never reach prod.

Only non-PII surfaces are copied (venue pictures, promotion posters).
Player profile photos are PII — maskers clear `profile_image` instead.
"""

import logging

from google.cloud import storage

from demo_kit import config

logger = logging.getLogger("demo_kit.images")

_PUBLIC = "https://storage.googleapis.com"

# collection -> [(field, "scalar"|"list")]
_IMAGE_FIELDS = {
    "venue": [("pictures", "list")],
    "promotion": [("posterImage", "scalar"), ("thumbnailImage", "scalar")],
}

_client = None
_copied = 0


def _storage():
    global _client
    if _client is None:
        _client = storage.Client()
    return _client


def reset_stats():
    global _copied
    _copied = 0


def copied_count():
    return _copied


def _rewrite(url):
    """Copy the blob a prod-bucket public URL points at into the demo bucket;
    return the demo URL. Non-source URLs pass through; copy failures keep the
    original (a read-only public link — safe, just not demo-owned)."""
    global _copied
    if not isinstance(url, str) or not config.GCS_DEMO_BUCKET:
        return url
    prefix = f"{_PUBLIC}/{config.GCS_SOURCE_BUCKET}/"
    if not url.startswith(prefix):
        return url
    name = url[len(prefix):].split("?")[0]
    src_bucket = _storage().bucket(config.GCS_SOURCE_BUCKET)
    dst_bucket = _storage().bucket(config.GCS_DEMO_BUCKET)
    try:
        src_bucket.copy_blob(src_bucket.blob(name), dst_bucket, name)
        _copied += 1
        return f"{_PUBLIC}/{config.GCS_DEMO_BUCKET}/{name}"
    except Exception as exc:
        logger.warning("Image copy failed for %s: %s", name, exc)
        return url


def rewrite_doc_images(collection_name, doc):
    """Rewrite image URL fields in place; returns the doc."""
    for field, shape in _IMAGE_FIELDS.get(collection_name, ()):
        if shape == "list":
            value = doc.get(field)
            if isinstance(value, list):
                doc[field] = [_rewrite(u) for u in value]
        elif doc.get(field):
            doc[field] = _rewrite(doc[field])
    return doc
