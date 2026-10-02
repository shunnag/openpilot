# Classification transport regression

Derived from the `wpa-classified-b0f1c8ee9bb32153` artifact of GitHub dryrun
36949831071 (`replay=19.9`, `mode=dryrun`, `wpa_reference=true`).

- `classification.json` and `input.json` are unchanged artifact metadata.
- `Sources-wpa` is the single `wpa` / `2:2.10-21ubuntu0.4` stanza from
  `archive/Sources-noble-updates-main.xz`, decompressed without changing fields.

The large indexes, packages and tarballs are omitted. These fixtures exercise
the JSON boundary, not signature verification: the tests mock recomputation
using the original checksum tuples parsed from `Sources-wpa`. Signature and
hash rejection have separate tests; full real-artifact recomputation is recorded
in the verification report.
