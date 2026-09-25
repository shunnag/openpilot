"""Small synthetic Android v0 boots for offline resolver/equivalence tests."""
import gzip
import struct

from kernel_equiv import BUILD_ID, CERT_MARKER, FDT, RSNXE_MARKER, SAE_MARKERS

PAGE = 4096
IMAGE_SIZE = 128 * 1024
BANNER = 256
UTS = 512
NOTE = 1024
CERT = 1280
CONFIG = 2048
INITRAMFS = 4096
SYMBOL = 6144


def newc(mtime):
  archive = bytearray()
  for ino, (name, mode, rdev) in enumerate((
    ("dev", 0o40755, (0, 0)), ("dev/console", 0o20600, (5, 1)),
    ("root", 0o40700, (0, 0)), ("TRAILER!!!", 0, (0, 0)),
  )):
    encoded = name.encode() + b"\0"
    fields = (ino, mode, 0, 0, 1, mtime, 0, 0, 0, *rdev, len(encoded), 0)
    archive += b"070701" + b"".join(f"{value:08x}".encode() for value in fields) + encoded
    archive += b"\0" * (-len(archive) % 4)
  archive += b"\0" * (-len(archive) % 512)
  return bytes(archive)


def ramdisk(mtime, cpio=None):
  return gzip.compress(newc(mtime) if cpio is None else cpio, mtime=mtime)


def der(tag, payload):
  size = len(payload)
  length = bytes([size]) if size < 128 else b"\x81" + bytes([size]) if size < 256 else b"\x82" + struct.pack(">H", size)
  return bytes([tag]) + length + payload


def fdt(payload):
  # A 40-byte header, empty reservation map, and fixed payload; two form a chain.
  return FDT + struct.pack(">9I", 64, 56, 60, 40, 17, 16, 0, 4, 4) + bytes(16) + payload.ljust(8, b"\0")


def boot_image(*, mtime=1, date="Sep 2", identity=1, config=b"CONFIG_TEST=y\n", sae=0, rsnxe=False, cpio=None):
  img = bytearray(b"\xa5" * IMAGE_SIZE)

  def put(offset, data, reserve=None):
    if reserve:
      img[offset:offset + reserve] = bytes(reserve)
    img[offset:offset + len(data)] = data

  put(BANNER, f"Linux version 4.9.103-build{identity} #1 SMP PREEMPT {date} 2026\n".encode(), 256)
  put(UTS, f"#1 SMP PREEMPT {date} 12:34:56 UTC 2026\0".encode(), 256)
  put(NOTE, BUILD_ID + bytes([identity]) * 20)
  tbs = der(0x30, der(0x0c, CERT_MARKER) + der(0x04, bytes([identity]) * 300))
  algorithm = der(0x30, der(0x06, b"\x2a\x86\x48\x86\xf7\x0d\x01\x01\x0b") + der(0x05, b""))
  put(CERT, der(0x30, tbs + algorithm + der(0x03, b"\0" + bytes([identity]) * 64)), 512)
  put(CONFIG, b"IKCFG_ST" + gzip.compress(config, mtime=0) + b"IKCFG_ED", 512)
  ram = ramdisk(mtime, cpio)
  put(INITRAMFS, ram, 512)
  # The real Image aligns __initramfs_size after the gzip member.
  put((INITRAMFS + len(ram) + 3) & ~3, struct.pack("<Q", len(ram)))
  put(SYMBOL, struct.pack("<I", INITRAMFS + len(ram) - 0x14))
  put(6656, b"\0".join(SAE_MARKERS[:sae]) + b"\0", 512)
  put(7168, RSNXE_MARKER + b" %d)\0" if rsnxe else b"", 256)
  kernel = bytes(img) + fdt(b"dtb one") + fdt(b"dtb two")
  header = bytearray(PAGE)
  header[:8] = b"ANDROID!"
  struct.pack_into("<10I", header, 8, len(kernel), 0x80008000, 0, 0x80008000, 0, 0x81000000, 0x80000100, PAGE, 0, 0)
  header[64:64 + len(b"console=tty0")] = b"console=tty0"
  header[576:608] = bytes([identity]) * 32
  return bytes(header) + kernel + bytes(-len(kernel) % PAGE)


def identity_pair():
  # Find a reproducible +1 compressed-length change without depending on zlib's
  # exact compression output on the host. Only newc mtimes differ in the payload.
  size = len(ramdisk(1))
  for mtime in range(2, 2000):
    if len(ramdisk(mtime)) == size + 1:
      return boot_image(), boot_image(mtime=mtime, date="Sep 16", identity=2)
  raise AssertionError("could not construct initramfs length +1 fixture")


def mutate(boot, offset):
  changed = bytearray(boot)
  changed[offset] ^= 1
  return bytes(changed)
