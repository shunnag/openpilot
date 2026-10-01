#!/usr/bin/env python3
"""Parse, sign and check AGNOS Android v0 boot images using Python and openssl."""
import argparse
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

from kernel_equiv import der_field, split_kernel

PAGE = 4096
HEADER_SIZE = 1632
SIGNATURE_SIZE = 2048
FIELDS = ("kernel_size", "kernel_addr", "ramdisk_size", "ramdisk_addr",
          "second_size", "second_addr", "tags_addr", "page_size", "header_version", "os_version")


def _header(raw):
  if len(raw) < HEADER_SIZE or raw[:8] != b"ANDROID!":
    raise ValueError("invalid or truncated Android boot header")
  fields = dict(zip(FIELDS, struct.unpack_from("<10I", raw, 8)))
  if fields["header_version"] != 0 or fields["ramdisk_size"] or fields["second_size"]:
    raise ValueError("expected Android v0 with no ramdisk or second stage")
  if fields["page_size"] != PAGE:
    raise ValueError("expected page size 4096")
  cmdline, nul, padding = raw[64:576].partition(b"\0")
  if not nul or any(padding) or any(raw[608:HEADER_SIZE]):
    raise ValueError("expected a NUL-terminated cmdline shorter than 512 bytes")
  fields.update(header=bytes(raw[:HEADER_SIZE]), name=bytes(raw[48:64]),
                cmdline=cmdline.decode("utf-8"), id=bytes(raw[576:608]))
  return fields


def parse(boot):
  """Return a dict of v0 fields, raw header/name/id, text cmdline and kernel.

  signature is the full 2048-byte block, or b'' for an unsigned fixture.
  header contains the 1632 header bytes and can be passed directly to repack.
  Unsupported layouts, truncated pages and unexpected trailers raise ValueError.
  """
  fields = _header(boot)
  size = fields["kernel_size"]
  end = PAGE + size
  padded_end = end + (-size % PAGE)
  if not size or padded_end > len(boot):
    raise ValueError("empty or truncated kernel/page")
  if len(boot) - padded_end not in (0, SIGNATURE_SIZE):
    raise ValueError("expected a 2048-byte signature block or unsigned boot")
  kernel = bytes(boot[PAGE:end])
  split_kernel(kernel)
  fields.update(kernel=kernel, signature=bytes(boot[padded_end:]))
  return fields


def _openssl(*args, data=None):
  result = subprocess.run(["openssl", *map(str, args)], input=data, capture_output=True)
  if result.returncode:
    raise ValueError(f"openssl {args[0]} failed: {result.stderr.decode(errors='replace').strip()}")
  return result.stdout


def repack(header_from, kernel, cmdline, key_path):
  """Return a signed boot, using a raw v0 header (or boot) as the template.

  Preserve every header field except kernel_size, cmdline and SHA1 id. cmdline
  is UTF-8 text or bytes; kernel is the complete Image-dtb, in the desired order.
  """
  fields = _header(header_from)
  encoded = cmdline.encode("utf-8") if isinstance(cmdline, str) else bytes(cmdline)
  if len(encoded) >= 512 or b"\0" in encoded:
    raise ValueError("cmdline must be shorter than 512 bytes without embedded NULs")
  encoded.decode("utf-8")
  if not kernel or len(kernel) > 0xffffffff:
    raise ValueError("invalid kernel size")
  split_kernel(kernel)
  header = bytearray(fields["header"])
  struct.pack_into("<I", header, 8, len(kernel))
  header[64:576] = encoded.ljust(512, b"\0")
  digest = hashlib.sha1(kernel + struct.pack("<3I", len(kernel), 0, 0)).digest()
  header[576:608] = digest + bytes(12)
  unsigned = bytes(header).ljust(PAGE, b"\0") + kernel + bytes(-len(kernel) % PAGE)
  signature = _openssl("pkeyutl", "-sign", "-inkey", key_path,
                       "-pkeyopt", "digest:sha256", "-pkeyopt", "rsa_padding_mode:pkcs1",
                       data=hashlib.sha256(unsigned).digest())
  if not signature or len(signature) > SIGNATURE_SIZE:
    raise ValueError("signature does not fit the 2048-byte block")
  return unsigned + signature.ljust(SIGNATURE_SIZE, b"\0")


def _signature_size(pubkey_pem):
  # RSA signatures have the modulus size, even if their final byte is zero.
  # Do not rstrip signature padding to infer their length.
  der = _openssl("rsa", "-pubin", "-RSAPublicKey_out", "-outform", "DER", data=pubkey_pem)
  tag, start, end = der_field(der, 0, len(der))
  if tag != 0x30 or end != len(der):
    raise ValueError("invalid RSA public key sequence")
  tag, start, end = der_field(der, start, end)
  if tag != 0x02:
    raise ValueError("invalid RSA modulus")
  size = len(der[start:end].lstrip(b"\0"))
  if not 0 < size <= SIGNATURE_SIZE:
    raise ValueError("RSA signature does not fit the signature block")
  return size


def verify(boot, pubkey_pem):
  """Return whether the signature and its zero padding verify; fail closed."""
  try:
    fields = parse(boot)
    block = fields["signature"]
    size = _signature_size(pubkey_pem)
    if len(block) != SIGNATURE_SIZE or any(block[size:]):
      return False
    with tempfile.TemporaryDirectory(prefix="bootimg-") as work:
      public, signature = Path(work) / "public.pem", Path(work) / "signature"
      public.write_bytes(pubkey_pem)
      signature.write_bytes(block[:size])
      _openssl("pkeyutl", "-verify", "-pubin", "-inkey", public, "-sigfile", signature,
               "-pkeyopt", "digest:sha256", "-pkeyopt", "rsa_padding_mode:pkcs1",
               data=hashlib.sha256(boot[:-SIGNATURE_SIZE]).digest())
    return True
  except (ValueError, OSError):
    return False


def pubkey_sha256(pem):
  """SHA-256 of canonical RSA SubjectPublicKeyInfo PEM (not DER)."""
  public = _openssl("rsa", "-pubin", "-pubout", data=pem)
  return hashlib.sha256(public).hexdigest()


def ondevice_hash(raw):
  """SHA-256 after zero padding to the next 4096-byte boundary."""
  digest = hashlib.sha256(raw)
  digest.update(bytes(-len(raw) % PAGE))
  return digest.hexdigest()


def with_tag(boot, tag, key):
  """Replace/append one wpa3.sae=N token and sign, preserving kernel bytes.

  tag is the complete token, as in pins.json. All other cmdline bytes remain.
  """
  if not isinstance(tag, str) or not re.fullmatch(r"wpa3\.sae=[1-9][0-9]*", tag):
    raise ValueError("expected tag wpa3.sae=N with positive decimal N")
  fields = parse(boot)
  cmdline = fields["cmdline"]
  tokens = list(re.finditer(r"(?<!\S)wpa3\.sae=\S*", cmdline))
  if len(tokens) > 1:
    raise ValueError("multiple wpa3.sae tags in cmdline")
  if tokens:
    token = tokens[0]
    cmdline = cmdline[:token.start()] + tag + cmdline[token.end():]
  else:
    cmdline += (" " if cmdline else "") + tag
  return repack(fields["header"], fields["kernel"], cmdline, key)


def selftest(stock, key):
  """Return whether parse/repack reproduces every input byte, signature included."""
  fields = parse(stock)
  return repack(fields["header"], fields["kernel"], fields["cmdline"], key) == stock


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  commands = parser.add_subparsers(dest="command", required=True)
  check = commands.add_parser("selftest", help="repack and compare every byte")
  check.add_argument("boot", type=Path)
  check.add_argument("--key", type=Path, required=True)
  verify_command = commands.add_parser("verify", help="verify with an RSA public PEM")
  verify_command.add_argument("boot", type=Path)
  verify_command.add_argument("--pubkey", type=Path, required=True)
  tag_command = commands.add_parser("tag", help="set wpa3.sae=N and sign a new image")
  tag_command.add_argument("boot", type=Path)
  tag_command.add_argument("--tag", required=True, help="complete wpa3.sae=N token")
  tag_command.add_argument("--key", type=Path, required=True)
  tag_command.add_argument("--out", type=Path, required=True)
  args = parser.parse_args()
  try:
    boot = args.boot.read_bytes()
    if args.command == "selftest":
      ok = selftest(boot, args.key)
      print(f"{'IDENTICAL' if ok else 'DIFFERENT'}: {args.boot}")
    elif args.command == "verify":
      ok = verify(boot, args.pubkey.read_bytes())
      print(f"{'VERIFIED' if ok else 'INVALID'}: {args.boot}")
    else:
      tagged = with_tag(boot, args.tag, args.key)
      args.out.write_bytes(tagged)
      ok = True
      print(f"TAGGED: {args.out}")
    return 0 if ok else 1
  except (ValueError, OSError) as error:
    print(f"FAIL: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
  sys.exit(main())
