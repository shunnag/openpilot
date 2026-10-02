# Part 3 classification artifact fix — 2026-10-02

Branch `wpa3-ci`, HEAD `09a9187e17aef1a955a951fb9f931f83b0204792`.
No commit, push, workflow dispatch, Docker execution, or remote write.

## Root cause

Run 36949831071 (`replay=19.9`, `mode=dryrun`, `wpa_reference=true`) failed
because `wpa_classify.checksums()` returns `(sha256, size)` tuples.
`classify()` includes those tuples under `source_files`. JSON serialization
converts them to arrays, which load as Python lists. `wpa_follow.build()` compared
the freshly recomputed dictionary directly with the JSON-loaded dictionary;
Python tuples and lists compare unequal.

Real-artifact recomputation found exactly one differing top-level field,
`source_files`. All three hashes and sizes were identical:

| File | Size |
| --- | ---: |
| `wpa_2.10.orig.tar.xz` | 2549336 |
| `wpa_2.10-21ubuntu0.4.debian.tar.xz` | 93956 |
| `wpa_2.10-21ubuntu0.4.dsc` | 2794 |

After a JSON round-trip, the entire recomputation equals the original artifact.
Absolute paths, temporary directories, timestamps, runner architecture, keyring
paths and dictionary ordering did not cause this mismatch. The failure happens
after successful W1–W3 recomputation; a signature verification failure would
have raised before the comparison.

The original code separately failed locally because Homebrew gpgv 2.5.24
successfully verifies the signature without creating its requested `--output`
file. This was reproduced before changing the code.

## Diff and trust boundary

- `scripts/wpa_follow.py`: compare sorted JSON encodings, rejecting non-finite
  numbers. This normalizes checksum tuples to arrays and ignores object key
  ordering, while retaining every field, value, array order and JSON type.
  Even `schema: true` versus `schema: 1` now holds (Python equality accepts it).
- `scripts/wpa_classify.py`: when successful gpgv leaves no output, run
  `gpg --decrypt` with the same explicit keyring, an isolated home, no user
  configuration, no default keyring and no automatic key retrieval. Require
  both exit status zero and a `VALIDSIG` status before reading the output.
  Failed or missing gpgv never triggers the fallback. Missing gpg also holds.
- `scripts/test_wpa_follow.py`: six new tests plus strengthened signature tests.
  Cover the artifact boundary, relocation, key order, real metadata differences,
  signature failures, fallback output and missing tools.
- `scripts/fixtures/wpa_classified/`: 5,051 bytes including documentation;
  unchanged artifact metadata and the original wpa Sources stanza. Large
  packages, tarballs and indexes are omitted. The transport tests mock W1–W3;
  real signature verification was also exercised against the complete artifact.

Build-side verification is retained. W1 still follows the trusted Ubuntu keyring
through signed InRelease → index hashes → package hash → stock binary hash.
The fallback consumes verified output rather than trusting artifact-carried
Release bytes. Reference verification and both orig tarball checks remain.

## Verification and complete outputs

All output links point to files saved with the user's local run evidence.

| Command/check | Result | Output |
| --- | --- | --- |
| Original local classifier | Expected missing gpgv output failure | [baseline](../.tmp/run36949831071/verification/baseline.txt) |
| Full artifact, fallback only, original comparison | Tuple/list mismatch reproduced; JSON round-trip matches | [reproduction](../.tmp/run36949831071/verification/reproduction.txt) |
| New transport regression against HEAD's original build function | Expected original HOLD reproduced | [before fix](../.tmp/run36949831071/verification/regression-before.txt) |
| `python3 -m unittest discover -s scripts -p 'test_*.py' -v` | Python 3.14.8; 243 tests; OK (skipped=3) | [python3](../.tmp/run36949831071/verification/python3.txt) |
| `python3.12 -m unittest discover -s scripts -p 'test_*.py'` | Python 3.12.15; 243 tests; OK (skipped=3) | [python3.12](../.tmp/run36949831071/verification/python3.12.txt) |
| `shellcheck scripts/wpa_test.sh userspace/wpa-build/compile-wpasupplicant.sh follow/macmini/*.sh` | Exit 0; no diagnostics | [shellcheck](../.tmp/run36949831071/verification/shellcheck.txt) |
| `actionlint -ignore 'unexpected key "queue"' .github/workflows/*.yml` | Exit 0; no diagnostics | [actionlint](../.tmp/run36949831071/verification/actionlint.txt) |
| Real artifact preflight and seven tampering checks, Python 3.14.8 | PASS; every mutation HOLD | [real artifact](../.tmp/run36949831071/verification/recompute-python3.txt) |
| Same preflight and tampering checks, Python 3.12.15 | PASS; every mutation HOLD | [real artifact, 3.12](../.tmp/run36949831071/verification/recompute-python3.12.txt) |
| `git diff --check` | Exit 0; no diagnostics | |

The original baseline was 237 tests, OK (skipped=3). The same three real-boot
tests remain skipped because `WPA3_REAL_BOOTS_DIR` is unset.

The [local verification harness](../.tmp/run36949831071/verification/recompute.py)
uses `.autofollow_1001/wpa/ubuntu-archive-keyring.gpg`, the public keyring extracted
from the hash-verified image during Part 3. Run from the repository root:

```sh
python3 .tmp/run36949831071/verification/recompute.py
python3.12 .tmp/run36949831071/verification/recompute.py
```

It runs the actual build function through candidate/reference verification and
orig hashes, then stops at the recipe-copy boundary. It does not run a compiler
or Docker. Separate copies of the evidence are mutated for each negative check;
the original downloaded artifact is unchanged. Native R0/R1 and runtime tests
were not rerun, and no GitHub workflow was run.
