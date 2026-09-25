"""Download an xz boot image with bounded raw size and mandatory SHA-256 checks."""
import hashlib
import http.client
import lzma
import re
import sys
import time
import urllib.error
import urllib.request

MAX_BOOT_SIZE = 64 * 1024 * 1024


def fetch_boot(url, hash_raw, size=None):
  if not isinstance(hash_raw, str) or not re.fullmatch(r"[0-9a-f]{64}", hash_raw):
    raise ValueError("boot download requires a SHA-256 hash_raw")
  if size is not None and (type(size) is not int or not 0 < size <= MAX_BOOT_SIZE):
    raise ValueError(f"invalid boot raw size {size!r}; cap is {MAX_BOOT_SIZE}")
  limit = MAX_BOOT_SIZE if size is None else size
  request = urllib.request.Request(url, headers={"User-Agent": "openpilot-wpa3-ci", "Accept-Encoding": "identity"})
  for attempt, delay in enumerate((5, 15, None), 1):
    try:
      return download_once(request, hash_raw, size, limit)
    except (ValueError, EOFError, lzma.LZMAError):
      # Integrity/format failures are definitive, not transient CDN failures.
      raise
    except (OSError, http.client.HTTPException) as error:
      if isinstance(error, urllib.error.HTTPError):
        error.close()
        if error.code not in (408, 429) and not 500 <= error.code < 600:
          raise
      if delay is None:
        raise
      print(f"boot download: network error on attempt {attempt}/3: {error}; retrying in {delay}s", file=sys.stderr)
      time.sleep(delay)


def download_once(request, hash_raw, size, limit):
  digest = hashlib.sha256()
  raw = bytearray()
  # urlopen follows redirects; LZMAFile streams the decompressed bytes in bounded chunks.
  with urllib.request.urlopen(request, timeout=60) as response, lzma.LZMAFile(response) as image:
    while chunk := image.read(min(1024 * 1024, limit - len(raw) + 1)):
      if len(raw) + len(chunk) > limit:
        raise ValueError(f"boot download exceeds raw size limit {limit}")
      raw.extend(chunk)
      digest.update(chunk)
  if (size is not None and len(raw) != size) or digest.hexdigest() != hash_raw:
    raise ValueError(f"boot download mismatch: raw size={len(raw)}, sha256={digest.hexdigest()}")
  return bytes(raw)
