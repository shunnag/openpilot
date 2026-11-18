"""Download an xz boot image with bounded raw size and mandatory SHA-256 checks."""
import hashlib
import http.client
import lzma
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

MAX_BOOT_SIZE = 64 * 1024 * 1024
STOCK_HOST = "commadist.azureedge.net"
RELEASE_HOST = "github.com"
# GitHub answers a release download with a redirect to its asset storage.
ASSET_HOSTS = ("release-assets.githubusercontent.com", "objects.githubusercontent.com",
               "github-releases.githubusercontent.com")
STOCK_PATH = re.compile(r"/agnosupdate/boot-[0-9a-f]{64}\.img\.xz")
RELEASE_PATH = re.compile(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/[A-Za-z0-9._-]+/boot-[0-9a-f]{64}\.img\.xz")


def check_boot_url(url, stock=False):
  """Allow only comma's stock boot images and boot assets of a GitHub release.

  The URL can come from an upstream manifest, so it is checked before any request:
  https, an exact host, no credentials, port, query or fragment, and a boot image
  path. stock=True allows only commadist, the host compose.py requires for
  derived_from.boot_url. The downloaded bytes are still checked against hash_raw.
  """
  allowed = ("https://commadist.azureedge.net/agnosupdate/boot-<sha256>.img.xz"
             + ("" if stock else " or a GitHub release asset boot-<sha256>.img.xz"))
  parts = urlsplit(url) if isinstance(url, str) and not re.search(r"[^\x21-\x7e]|[?#]", url) else None
  if not (parts and parts.scheme == "https"
          and ((parts.netloc == STOCK_HOST and STOCK_PATH.fullmatch(parts.path))
               or (not stock and parts.netloc == RELEASE_HOST and RELEASE_PATH.fullmatch(parts.path)))):
    raise ValueError(f"boot URL refused; expected {allowed}")


class BootRedirects(urllib.request.HTTPRedirectHandler):
  """Follow a redirect only within commadist, or from GitHub to its asset hosts."""
  def redirect_request(self, req, fp, code, msg, headers, newurl):
    origin, target = urlsplit(req.full_url).netloc, urlsplit(newurl)
    allowed = (STOCK_HOST,) if origin == STOCK_HOST else (RELEASE_HOST, *ASSET_HOSTS)
    if target.scheme != "https" or target.netloc not in allowed or target.username or target.port:
      fp.close()
      raise ValueError(f"boot download refused a redirect from {origin} to another host")
    return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(BootRedirects)


def urlopen(request, timeout):
  return OPENER.open(request, timeout=timeout)


def fetch_boot(url, hash_raw, size=None):
  if not isinstance(hash_raw, str) or not re.fullmatch(r"[0-9a-f]{64}", hash_raw):
    raise ValueError("boot download requires a SHA-256 hash_raw")
  if size is not None and (type(size) is not int or not 0 < size <= MAX_BOOT_SIZE):
    # The size can come from an upstream manifest: name only its type, never its value.
    raise ValueError(f"invalid boot raw size of type {type(size).__name__}; expected an int from 1 to {MAX_BOOT_SIZE}")
  limit = MAX_BOOT_SIZE if size is None else size
  check_boot_url(url)
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
  with urlopen(request, timeout=60) as response, lzma.LZMAFile(response) as image:
    while chunk := image.read(min(1024 * 1024, limit - len(raw) + 1)):
      if len(raw) + len(chunk) > limit:
        raise ValueError(f"boot download exceeds raw size limit {limit}")
      raw.extend(chunk)
      digest.update(chunk)
  if (size is not None and len(raw) != size) or digest.hexdigest() != hash_raw:
    raise ValueError(f"boot download mismatch: raw size={len(raw)}, sha256={digest.hexdigest()}")
  return bytes(raw)
