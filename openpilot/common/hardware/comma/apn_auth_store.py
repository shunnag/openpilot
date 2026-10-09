"""Private, atomic storage for APN authentication settings."""
import json
import os
import tempfile

STORE_DIR = os.environ.get("APN_AUTH_STORE_DIR", "/data/apn_auth")
STORE_PATH = STORE_DIR + "/settings.json"


def read() -> tuple[str, str, str]:
  try:
    with open(STORE_PATH) as f:
      settings = json.load(f)
    values = tuple(settings.get(key, "") for key in ("auth", "user", "password"))
    if all(isinstance(value, str) for value in values):
      return values
  except (OSError, ValueError, AttributeError, TypeError):
    pass
  return "", "", ""


def write(auth=None, user=None, password=None):
  values = dict(zip(("auth", "user", "password"), read(), strict=True))
  for key, value in (("auth", auth), ("user", user), ("password", password)):
    if value is not None:
      if not isinstance(value, str):
        raise TypeError("APN auth settings must be strings")
      values[key] = value
  os.makedirs(STORE_DIR, mode=0o700, exist_ok=True)
  fd, temporary = tempfile.mkstemp(dir=STORE_DIR, prefix=".settings-")
  try:
    with os.fdopen(fd, "w") as f:
      os.fchmod(f.fileno(), 0o600)
      json.dump(values, f)
      f.flush()
      os.fsync(f.fileno())
    os.replace(temporary, STORE_PATH)
  finally:
    try:
      os.unlink(temporary)
    except FileNotFoundError:
      pass


def clear():
  try:
    os.unlink(STORE_PATH)
  except FileNotFoundError:
    pass


def mtime() -> float | None:
  try:
    return os.stat(STORE_PATH).st_mtime
  except OSError:
    return None
