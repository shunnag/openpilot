# Follow dryrun, Parts 2 and 3

`follow.yml` implements discovery → pre-build gates → isolated stock/WPA3 builds
→ independent verification and assembly. It is **dryrun only**: outputs are
Actions artifacts and job summaries. There is no schedule, issue update, release,
tag, state commit, push, or workflow dispatch. `nightly.yml`, `rollback.yml`,
`pins.py`, `compose.py` and `gates.py` are unchanged.

After the orchestrator has reviewed and made this branch available on GitHub:

```bash
gh workflow run follow.yml --repo shunnag/openpilot --ref wpa3-ci -f replay=19.9 -f mode=dryrun
```

Then replay `19.8` and `neg-caff1d8d`. The latter succeeds only when the forced
parent fails publish-side K5. `replay=latest` invokes the existing `pins.resolve`
kernel trigger against the selected upstream branch(es); `branch=all` includes
tizi. Items are deduplicated by stock hash. Integrity failures stop builds;
K3/K4 risk failures remain visible while producing review artifacts. A pause or
withdrawn target always stops the run. `force` only bypasses a recent held attempt.

The only mode names are `off`, `dryrun`, `state`, `on`. This workflow clamps
`state` and `on` to dryrun, and a historical replay forces dryrun even in `off`.
Without a replay, `off` exits in detect. There is no canary or soak behavior.

## Local, offline verification

The harness uses read-only cached builder heads/history, kernel heads/history,
the real stock boot and a kernel repository with the baseline/candidate blobs:

```bash
python3 scripts/kernel_dryrun.py --out /tmp/kernel-follow-199 --assemble
```

Defaults refer to `.autofollow_1001/kernel_src/{b,k}.git` and `/Volumes/agnos`.
Override `--builder`, `--history`, `--kernel`, and `--volume` for another cache.
No download or compilation occurs; missing cached objects fail closed. The
cached PR list is empty (the research cache does not contain the deleted PR
head); the all-heads scan still finds `agnos18.1.1@2862c8f8` and its `8b0e4d28`
gitlink. Temp-repository unit tests separately exercise same-repository and
fork PR heads. Online discovery uses every API page of PRs in all states and
fetches only same-repository PR heads. Network code refuses to run outside
GitHub Actions.

For individual commands, supply the explicit cached contexts:

```bash
python3 scripts/kernel_discover.py --version 19.9 \
  --stock /Volumes/agnos/ref199/boot-b9c9b926.img \
  --builder .autofollow_1001/kernel_src/b.git \
  --kernel .autofollow_1001/kernel_src/k.git \
  --prs follow/replay/builder-prs.json --heads follow/replay/kernel-heads.json \
  --offline --out /tmp/cand.json
```

`kernel_gates.py --help` lists its manifest, recipe, baseline and git contexts.
For the short design command, the known stock hash selects its recorded replay
context and the same cache defaults as the harness. Unknown stocks require
explicit contexts. `--assemble` also checks the cached Mac stock
rebuild and the tag3 kernel. It labels absent local build proofs/manifests as
SKIP; it does not claim a CI build occurred.

## Build and verification boundary

- Workflow/job permissions are `{}` / `{contents: read}`. Build jobs have no
  secrets or `gh` calls. Checkout credentials are not persisted. Every external
  action is pinned to a commit. The workflow is written in the JSON subset of
  YAML 1.2 so a standard-library test can parse and check the entire structure,
  including permissions, trigger, action pins, and forbidden write steps.
- Builder gitlinks propose sources. Only heads of the comma kernel repository
  can establish source membership; pull refs cannot. Tree deduplication and
  oracle ordering precede a maximum of `policy.max_full_builds` full builds
  **across the run**, including certificate retries. Extra work is listed in
  `omitted_by_budget`. A spare slot funds at most one retry per candidate. All
  scheduled candidates must return a conclusive result before uniqueness can
  be settled. Incremental WPA3 builds follow only a reproducing stock build.
- Host preparation checks the patches, seven original blob IDs, and normalized
  diff, then exports stock and patched trees with `git archive`. The host git
  directory is removed before any compilation. The container mounts only the
  export and read-only toolchain, with no network, capabilities, credentials,
  Docker socket or repository metadata. All `make` commands use `O=out` there.
- Cache entries contain only ARM's tarball, verified after every restore and
  again by each wrapper invocation. No LFS objects are downloaded. The Ubuntu
  20.04 digest is from the successful local GCC 8.2 build logs, including
  `/Volumes/agnos/build-199-stock-gcc8.log`. The unmodified Dockerfile is built
  after pulling that digest and retagging it locally. Package and image
  inspection records accompany the artifacts.
- Publish restores no cache and executes no build output. It verifies bounded
  data and recomputes K5, patch evidence, config, SAE/RSNXE, layout, exact stock
  DTB order, signatures, sizes, padded on-device hashes, xz round trips, revert
  checks and K12. Both manual boot images are downloaded and hash checked for
  the on-device hash self-test. K10 produces proposed numbers only; historical
  replay numbers are deliberately reused only in local/Actions artifacts.
- Publish extracts the **wrapped** Image with
  `kernel_equiv.split_kernel(wpa3.Image-dtb)[0]`. The raw `wpa3.Image` and
  `stock.Image` files start with `MZ` and are build diagnostics, not assembly
  inputs. K7 consumes the wrapped Image; K9 and Q1 inspect the assembled boot.
- K7b and K8 hashes, dependency lists and compilation/source linkage are
  explicitly identified as computed in the build job. They cannot be recovered
  from an Image. Missing reviewed references are SKIP in this dryrun-only part.
  K8 is advisory even when a comparison is available.

Two implementation details correct shorthand in the design: the original
recipe's `dyndbg=\"\"` requires shell-quote-aware cmdline normalization; and the
real 19.8/19.9 stock config omits `WLAN_FEATURE_SAE` altogether because patch
0001 introduces that Kconfig symbol. K7 accepts only absent-or-disabled → `y`
for this one option, with no other option delta and `MODULE_SIG_FORCE` unset.

### Q1 replay equivalence

Q1 compares the assembled WPA3 boot with the hash-checked manual replay boot
(19.9 tag3 or 19.8 tag2). The only cmdline allowance is replacing its single,
final `wpa3.sae=<positive decimal>` token with the expected assembly tag.
Every other cmdline byte, including whitespace, must match. Historical replays
use the same number, so 19.9 compares tag3 to tag3 without any cmdline change.
This normalization is confined to Q1; the stock rebuild comparator is unchanged.

After retagging the reference, `rebuild_equivalent` permits exactly its existing
bounded differences:

- Whole appended DTBs may be reordered, with identical bytes and multiplicity.
  K9 separately requires the assembled DTBs to retain stock bytes and order.
- Linux banner, `proc_banner` and standalone `#N SMP PREEMPT` strings must
  start at matching offsets and terminate within 256 bytes. Length differences
  are at most 16 bytes, with identical terminators and zero padding in the
  shorter image. Only those bounded spans are masked.
- GNU build-id payloads (20 bytes) at matching offsets and validated generated
  X.509 certificate spans (at most 4096 bytes, identical starts/ends) may differ.
- Embedded newc initramfs archives must match after zeroing only cpio mtimes.
  Their gzip encodings may differ with a compressed-length delta at most 16,
  matching starts and aligned size-word locations, valid size words/padding,
  and no gzip flags except FNAME. One 32-bit symbol word may change by exactly
  that length delta if its original value is within 64 bytes of the original
  compressed member's end offset.

All other Image bytes, Image size, decompressed IKCONFIG and boot header bytes
must match. The Android SHA1 ID and signature trailer are excluded by the
comparator; K9 independently verifies the assembled signature, wrapper and
layout. Code, config, non-tag cmdline, DTB content or multiplicity changes fail.

To rerun a downloaded publish job locally, use the same entry point:

```bash
python3 scripts/kernel_follow.py publish --inputs /tmp/replay/kernel-detect \
  --builds .tmp/run36939004599 --out /tmp/replay/verified
```

If the code changed since detect, copy `kernel-detect` first and update only
that copy's `plan.json` `gate_version` to `follow_state.gate_version()` for an
explicit offline re-verification. Record both fingerprints and retain the
original downloads. This exercises the new verifier on old build bytes; it is
not a new CI run. Production still rejects fingerprints changed between jobs.

## Checks still requiring GitHub

The job summary retains TODOs for Q1 reference review, Q5 object determinism,
Q7 runner disk/time and discovery fallback cost, and Q8/Q10 job semantics.
`metrics.txt` samples free space every five seconds and records wall time;
`min_free_gb` is enforced before toolchain extraction/build. These are sampled
measurements, not guessed peak-use or duration claims.

Download the build artifacts from two independent executions of the same
replay, then run the implemented Q5 comparison:

```bash
python3 scripts/kernel_build_data.py compare-wifi --first /tmp/run-A --second /tmp/run-B
```

It requires identical source/patch proofs and compares every stripped object
hash. The result alone does not promote K8 to a gate. Review the generated
reference files before committing them under `follow/reference/`.

`queue: max` is deferred in this read-only part: local actionlint 1.7.12 rejects
it, while acceptance requires plain `actionlint .github/workflows/*.yml` to
pass. Publish retains the job-level `wpa3-state` group. No state-write correctness
depends on that group here. The future writing stage must restore and verify
the queue behavior. No `follow-dryrun` issue is written because Part 2 enforces
the requested no-write workflow boundary.

## Part 3: wpa_supplicant

The same workflow adds `probe`, `wpa-classify`, native `ubuntu-24.04-arm`
`wpa-build`, and `wpa-test`. Probe deduplicates the four upstream system images,
reuses known hashes, and emits new probe records only as artifacts. Existing G8
enforcement and off-mode composition behavior are preserved. A newly discovered
nonempty 4.9 module directory holds kernel verification.

Known supplicants do not rebuild unless the manual dispatch input `wpa_reference`
is true. The build authenticates Ubuntu indices, checks W1–W3 and P1/P2, builds
twice under the pinned image/snapshot, and retains R1/R0 evidence. T0–T2 use the
verified read-only AGNOS image. See the [recipe](../userspace/wpa-build/README.md).

`test-request.json` and its six assets are uploaded as Actions artifacts only.
Their future public release URLs are not published in Part 3. The Mac mini
[runner and Japanese setup guide](macmini/README_ja.md) use public release assets
for anonymous discovery and a locally reviewed suite commit. Its token is scoped
only to `shunnag/wpa3-test-results`; the VM has no host mounts or forwarded agent.

Publish rechecks candidate identities and reads a public Mac mini result only
when `wpa_result_id` is supplied. It must match all rebuilt asset hashes and the
suite commit. A prior public request can supply the original deadline and ID.
Otherwise the summary says `T3: PENDING (dryrun)`. `policy.wpa.auto_publish`
remains false; publishing, async request continuation, deadline issues and state
writes are Part 4a. No automation depends on the MacBook or research caches.

See [Part 3 verification](PART3-VERIFICATION.md) for exact commands, full outputs,
and checks that still need the orchestrator's environment.
