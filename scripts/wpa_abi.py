#!/usr/bin/env python3
"""T0: ELF64/aarch64, BIND_NOW and no new libraries or symbol versions."""
import argparse
from pathlib import Path
import re
import subprocess
from system_probe import require


def abi(path):
  header = path.read_bytes()[:64]
  require(len(header) == 64 and header[:7] == b'\x7fELF\x02\x01\x01' and header[18:20] == b'\xb7\0'
          and int.from_bytes(header[16:18], 'little') in (2, 3), 'T0: not ELF64 aarch64 executable')
  dynamic = subprocess.check_output(['readelf', '-dW', str(path)], text=True)
  versions = subprocess.check_output(['readelf', '-VW', str(path)], text=True)
  needed = set(re.findall(r'\(NEEDED\).*?\[(.*?)\]', dynamic))
  symbols = set(re.findall(r'Name: (\S+)', versions))
  require('BIND_NOW' in dynamic or re.search(r'\(FLAGS_1\).*\bNOW\b', dynamic), 'T0: BIND_NOW missing')
  require(needed and symbols, 'T0: missing dynamic ABI')
  return needed, symbols


def check(candidate, stock):
  needed, symbols = abi(candidate)
  stock_needed, stock_symbols = abi(stock)
  require(needed <= stock_needed and symbols <= stock_symbols, 'T0: new library or symbol version')


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument('candidate', type=Path)
  parser.add_argument('stock', type=Path)
  args = parser.parse_args()
  check(args.candidate, args.stock)
  print('T0: PASS')
