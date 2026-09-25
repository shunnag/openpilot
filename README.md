openpilot + WPA3
======

**This is an unofficial fork for personal use. It ships a modified kernel and is not supported by comma.**

**個人利用向けの非公式 fork です。変更したカーネルを配布しており、comma のサポート対象ではありません。**

This fork adds WPA3 (SAE) Wi-Fi support to openpilot on the comma four. Every night, it rebuilds two prebuilt branches from comma's branches of the same name. This `wpa3-ci` branch holds the workflows, scripts and patches that build them.

この fork は、comma four の openpilot に WPA3（SAE）の Wi-Fi 対応を追加します。comma の同名ブランチをもとに、2 つのビルド済みブランチを毎晩作り直します。この `wpa3-ci` ブランチには、それを作るワークフロー、スクリプト、パッチを置いています。


Branches
------

| branch             | URL                                         | description                                                                     |
|--------------------|---------------------------------------------|---------------------------------------------------------------------------------|
| `nightly`          | installer.comma.ai/shunnag/nightly          | comma's `nightly` with WPA3 support. Use this on a comma four without chestnut. |
| `nightly-chestnut` | installer.comma.ai/shunnag/nightly-chestnut | comma's `nightly-chestnut` with WPA3 support. For [chestnut](https://comma.ai/shop/chestnut). |

Both branches have the same source and the same WPA3 changes. `nightly-chestnut` also includes the large driving model for chestnut (about 773 MB, downloaded through Hugging Face LFS) and a debug panda build (`PANDA_DEBUG_BUILD=1`). These are bleeding edge development branches. Do not expect them to be stable.

2 つのブランチは、ソースも WPA3 の変更も同じです。`nightly-chestnut` には、chestnut 用の大きな運転モデル（約 773 MB、Hugging Face の LFS から取得）と、panda のデバッグビルド（`PANDA_DEBUG_BUILD=1`）が加わります。chestnut を使わない comma four では `nightly` を使ってください。どちらも開発中の最新ブランチなので、安定性は期待しないでください。


What's changed
------

Each build is comma's prebuilt commit with these changes:

1. **Kernel:** the `boot` entry in the AGNOS manifest points to a boot image that enables SAE in the qcacld-3.0 Wi-Fi driver ([commaai/agnos-kernel-sdm845#142](https://github.com/commaai/agnos-kernel-sdm845/pull/142)) and puts the RSNXE in the association request for SAE hash-to-element (H2E, [#143](https://github.com/commaai/agnos-kernel-sdm845/pull/143)). All other AGNOS images, including `system`, are comma's. `AGNOS_VERSION` is unchanged. comma's original manifest is kept next to it as `agnos.stock.json`.
2. **UI:** when the driver supports SAE, WPA3-only networks are listed and connected with a `sae` profile.
3. **Launcher and updater:** they install the WPA3 kernel if the running kernel doesn't have it. See [Kernel install](#kernel-install).
4. **wpa_supplicant:** a patched `wpa_supplicant` ships in `wpa3/` and runs instead of AGNOS's stock one. It enables H2E and has SAE security fixes. See [wpa_supplicant](#wpa_supplicant).

各ビルドは、comma のビルド済みコミットに次の変更を加えたものです。

1. **カーネル:** AGNOS の manifest の `boot` を、qcacld-3.0 Wi-Fi ドライバの SAE を有効にした boot イメージに差し替えます（[commaai/agnos-kernel-sdm845#142](https://github.com/commaai/agnos-kernel-sdm845/pull/142)）。このイメージは、SAE の hash-to-element（H2E）に必要な RSNXE を接続要求に載せます（[#143](https://github.com/commaai/agnos-kernel-sdm845/pull/143)）。`system` を含むほかの AGNOS イメージは comma のままです。`AGNOS_VERSION` も変えません。comma の元の manifest は、`agnos.stock.json` として隣に残します。
2. **UI:** ドライバが SAE に対応していれば、WPA3 専用のネットワークを一覧に表示し、`sae` のプロファイルで接続します。
3. **ランチャーと updater:** 起動中のカーネルが WPA3 対応でなければ、WPA3 カーネルをインストールします。[Kernel install](#kernel-install) を参照してください。
4. **wpa_supplicant:** 修正版の `wpa_supplicant` を `wpa3/` に同梱し、AGNOS の純正の代わりに動かします。H2E を有効にし、SAE の脆弱性修正も入っています。[wpa_supplicant](#wpa_supplicant) を参照してください。


Installing
------

The first install needs a network that isn't WPA3-only: WPA2, WPA2/WPA3 mixed mode, a phone hotspot, or LTE. AGNOS setup and the stock kernel can't join WPA3-only networks. After install, the WPA3 kernel is flashed through the normal A/B AGNOS update, which may download about 1 GB. After the next reboot, WPA3-only networks work.

This fork was tested only on the comma four. The comma 3X uses the same kernel and firmware, but it is untested.

初回のインストールには、WPA3 専用ではないネットワーク（WPA2、WPA2/WPA3 混在モード、スマートフォンのテザリング、LTE のいずれか）が必要です。AGNOS のセットアップ画面と純正カーネルは、WPA3 専用のネットワークにつながりません。インストール後、通常の A/B 方式の AGNOS 更新で WPA3 カーネルを書き込みます。このとき約 1 GB をダウンロードすることがあります。再起動後は、WPA3 専用のネットワークも使えます。

動作確認は comma four でのみ行っています。comma 3X はカーネルとファームウェアが同じですが、未確認です。


Kernel install
------

The WPA3 boot image adds a tag such as `wpa3.sae=2` to the kernel command line (each boot image has its own tag). On every boot, `launch_chffrplus.sh` looks for this tag in `/proc/cmdline`. If it's missing, the launcher runs the same A/B path as an AGNOS update: it swaps to the inactive slot if that slot already has the image, and otherwise flashes the slot first. `updated` stages the image in the background under the same condition.

To prevent boot loops, the launcher tries at most 3 times per boot image hash. Attempts are recorded in `/data/wpa3_boot_attempts` as `<hash_raw> <count>`. After 3 attempts, it stops, and the device keeps running the stock kernel. The count resets when the boot image hash changes, and the file is removed once the tag is present. A malformed count, or a count that can't be saved, also stops the retries. `updated` only reads the count.

AGNOS version updates use the same count. If the running kernel doesn't have the tag, each update attempt counts, and after 3 attempts the launcher and `updated` flash comma's manifest (`agnos.stock.json`) instead. If the running kernel already has the tag, the WPA3 kernel has proven itself on this device, so the update uses the WPA3 manifest without counting.

WPA3 の boot イメージは、カーネルのコマンドラインに `wpa3.sae=2` のようなタグを追加します（タグは boot イメージごとに異なります）。`launch_chffrplus.sh` は起動のたびに、このタグが `/proc/cmdline` にあるかを確認します。なければ、AGNOS 更新と同じ A/B の手順を実行します。待機中のスロットにイメージが用意済みならそのスロットに切り替え、なければ先にそのスロットへ書き込みます。`updated` も同じ条件で、バックグラウンドでイメージを準備します。

起動の繰り返しを防ぐため、ランチャーの試行は boot イメージのハッシュごとに 3 回までです。試行回数は `/data/wpa3_boot_attempts` に `<hash_raw> <count>` の形で記録します。3 回試してもタグがなければ試行をやめ、純正カーネルのまま動き続けます。boot イメージのハッシュが変わると回数はリセットされ、タグを確認できた時点で記録ファイルは削除されます。記録の内容が壊れている場合や、記録を保存できない場合も、試行を止めます。`updated` は回数を読むだけで、増やしません。

AGNOS のバージョン更新でも、同じ回数を使います。起動中のカーネルにタグがなければ、更新のたびに 1 回と数え、3 回を超えたらランチャーと `updated` は comma の manifest（`agnos.stock.json`）で書き込みます。起動中のカーネルにすでにタグがあれば、その端末で WPA3 カーネルが動くことは確認済みなので、回数を数えずに WPA3 の manifest で更新します。


wpa_supplicant
------

AGNOS ships Ubuntu's wpa_supplicant 2.10, which never uses SAE hash-to-element (H2E) by default and lacks SAE fixes from hostap 2.11/2.12. The fork ships `wpa3/wpa_supplicant`, built from Ubuntu's package with those fixes and with `sae_pwe=2` as the default ([commaai/agnos-builder#629](https://github.com/commaai/agnos-builder/pull/629)). With it, SAE uses H2E when the AP advertises it. NetworkManager's behavior doesn't change: WPA2/WPA3 transition networks and the hotspot stay WPA2-PSK.

On every boot, the launcher bind-mounts it over `/usr/sbin/wpa_supplicant` and restarts the service, but only if:

* the stock binary is exactly Ubuntu's `2:2.10-21ubuntu0.4` (its SHA-256 is pinned), so a different AGNOS keeps its own,
* the patched binary runs (`wpa_supplicant -v`), and
* it hasn't failed on this device before.

If the service isn't running the patched binary within 15 seconds, the launcher unmounts it and restarts the stock one. A runtime systemd drop-in in `/run` does the same if the patched binary exits abnormally later. Failures are recorded in `/data/wpa3_supplicant_failed` as `<sha256> <reason>` lines. One start failure, or 3 abnormal exits, turns the override off on that device. Nothing is written to the system partition: after leaving the fork and rebooting, the stock binary is back. To turn the override off by hand, add a line `<sha256 of wpa3/wpa_supplicant> start` to that file and reboot.

AGNOS には Ubuntu の wpa_supplicant 2.10 が入っています。この版は、既定では SAE の hash-to-element（H2E）を使わず、hostap 2.11/2.12 の SAE の修正も入っていません。fork は、Ubuntu のパッケージにその修正を入れ、既定値を `sae_pwe=2` にして作り直した `wpa3/wpa_supplicant` を同梱します（[commaai/agnos-builder#629](https://github.com/commaai/agnos-builder/pull/629)）。これで、AP が H2E を広告していれば、SAE で H2E を使います。NetworkManager の動作は変わらず、WPA2/WPA3 混在のネットワークとホットスポットは WPA2-PSK のままです。

ランチャーは起動のたびに、これを `/usr/sbin/wpa_supplicant` に bind mount して、サービスを再起動します。ただし、次の場合に限ります。

* 純正のバイナリが Ubuntu の `2:2.10-21ubuntu0.4` と完全に一致する（SHA-256 を pin に固定）。別の AGNOS では純正のまま使う。
* 修正版が起動できる（`wpa_supplicant -v`）。
* その端末で、以前に失敗していない。

15 秒以内に修正版がサービスとして動いていなければ、ランチャーは bind mount を外して純正を起動し直します。起動後に修正版が異常終了した場合も、`/run` に置いた systemd の一時設定が同じように戻します。失敗は `/data/wpa3_supplicant_failed` に `<sha256> <理由>` の形で記録し、起動時の失敗 1 回、または異常終了 3 回で、その端末では差し替えをやめます。system パーティションには何も書き込まないので、fork をやめて再起動すれば純正に戻ります。手動で差し替えを止めるには、このファイルに `<wpa3/wpa_supplicant の sha256> start` という行を足して再起動してください。


Nightly builds
------

The **Nightly WPA3** workflow runs every day at 11:00 UTC (20:00 JST), with a catch-up run at 12:30 UTC (21:30 JST). It rebuilds each branch from comma's latest commit. comma's branches are squashed orphan commits, so each build is a new commit on top of theirs, and nothing is merged. Builds are deterministic: the same inputs always produce the same commit SHA. If comma hasn't published a new build, the branch is left as is.

**Nightly WPA3** ワークフローは、毎日 11:00 UTC（20:00 JST）に実行されます。取りこぼしに備えて、12:30 UTC（21:30 JST）にも実行されます。実行のたびに、comma の最新コミットをもとに各ブランチを作り直します。comma のブランチは履歴を 1 つにまとめた親なしのコミットなので、各ビルドはその上に新しいコミットを 1 つ作るだけで、マージはしません。ビルドは再現可能で、入力が同じなら必ず同じコミット SHA になります。comma が新しいビルドを出していなければ、ブランチは変えません。

First, `scripts/pins.py` picks the boot image for the upstream `AGNOS_VERSION`. See [AGNOS updates](#agnos-updates). Then the workflow checks:

最初に `scripts/pins.py` が、upstream の `AGNOS_VERSION` に使う boot イメージを決めます（[AGNOS updates](#agnos-updates) を参照）。そのあと、次の項目を確認します。

| check | English                                                                                     | 日本語                                                                                          |
|-------|---------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| G1    | A boot image was resolved for the upstream `AGNOS_VERSION`.                                 | upstream の `AGNOS_VERSION` に使う boot イメージが決まっている。                               |
| G2    | The upstream stock `boot` and `system` hashes match the pin's `derived_from`.               | upstream の純正 `boot` と `system` のハッシュが、pin の `derived_from` と一致する。             |
| G3    | The upstream `agnos.py` is unchanged, and the launcher patch applies.                       | upstream の `agnos.py` が変わっておらず、ランチャーのパッチが当たる。                           |
| G4    | The pinned boot image downloads, and its decompressed SHA-256 and size match.               | pin の boot イメージをダウンロードでき、展開後の SHA-256 とサイズが一致する。                   |
| G5    | The UI patch applies, or is already applied.                                                | UI のパッチが当たる、または適用済みである。                                                     |
| G6    | The command line tag and the boot image hash still match one to one, compared with the published build. | 公開中のビルドと比べて、コマンドラインのタグと boot イメージのハッシュが 1 対 1 のままである。 |
| G7    | The bundled `wpa_supplicant` matches its pinned SHA-256 and is an aarch64 ELF, and its license file exists. | 同梱の `wpa_supplicant` が pin の SHA-256 と一致する aarch64 の ELF で、ライセンスのファイルがある。 |

If a check fails, that branch isn't published and keeps its last build. The workflow opens or updates one issue per branch, labeled `nightly-hold` and `branch:<branch>`, and closes it after the next successful build.

After publishing, the workflow checks that installer.comma.ai serves an installer for the branch. If this fails, it opens a `nightly-smoke` issue but keeps the new build.

確認に失敗したブランチは公開せず、前回のビルドのままにします。ワークフローは、`nightly-hold` と `branch:<branch>` のラベルを付けた issue をブランチごとに 1 件作成または更新し、次に公開できたときに閉じます。

公開後は、installer.comma.ai がそのブランチ用のインストーラーを返すかを確認します。失敗した場合は `nightly-smoke` の issue を作りますが、公開した新しいビルドはそのまま残します。


AGNOS updates
------

When comma bumps `AGNOS_VERSION`, `scripts/pins.py` resolves the new version in one of four ways:

| mode      | when                                                                                                           | result                                                                   |
|-----------|----------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| `pinned`  | `agnos/pins.json` has a pin for this version.                                                                  | The pinned WPA3 boot image is used.                                      |
| `derived` | comma's new stock kernel is the same kernel as a pin's stock kernel, and `agnos.py` is unchanged.             | That pin's WPA3 boot image is reused. The rest of AGNOS is comma's new version. |
| `native`  | comma's new stock kernel already supports SAE and RSNXE (H2E).                                                 | The boot image isn't replaced. The UI patch and the `wpa_supplicant` override are still applied. |
| hold      | Anything else, e.g. the kernel code changed, or a download failed.                                             | Nothing is published. A `nightly-hold` issue explains why.               |

"Same kernel" is checked on the decompressed boot images. The boot header, command line, device tree and kernel config must be identical. In the kernel image, only build identity may differ: the build date strings, the GNU build ID, the autogenerated module signing certificate and the timestamps in the built-in initramfs. Each allowed difference must be at the same place in both images and within a size limit. comma's stock kernels for AGNOS 19.6, 19.7 and 19.8 all pass this check, so the device-tested WPA3 kernel is reused without a new build.

The `native` check looks for four SAE log strings and the RSNXE log string in comma's kernel. A partial match, or SAE without RSNXE, holds the nightly.

A hold because the kernel code changed needs a new WPA3 boot image: build it, test it on a device, and add a pin.

comma が `AGNOS_VERSION` を上げると、`scripts/pins.py` は新しいバージョンを次の 4 通りのどれかで扱います。

| モード    | 条件                                                                                           | 結果                                                                            |
|-----------|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| `pinned`  | `agnos/pins.json` にこのバージョンの pin がある。                                             | pin の WPA3 boot イメージを使う。                                               |
| `derived` | comma の新しい純正カーネルが、既存の pin の元になった純正カーネルと同じで、`agnos.py` も変わっていない。 | その pin の WPA3 boot イメージを使い回す。ほかの AGNOS は comma の新しいもの。 |
| `native`  | comma の新しい純正カーネルが、すでに SAE と RSNXE（H2E）に対応している。                     | boot イメージは差し替えない。UI のパッチと `wpa_supplicant` の差し替えは続ける。 |
| 保留      | それ以外（カーネルのコードが変わった、ダウンロードに失敗した、など）。                       | 公開しない。`nightly-hold` の issue で理由を知らせる。                          |

「同じカーネル」かどうかは、展開した boot イメージで判定します。boot のヘッダー、コマンドライン、デバイスツリー、カーネル設定は完全に一致している必要があります。カーネル本体で違ってよいのは、ビルドのたびに変わる情報だけです。具体的には、ビルド日時の文字列、GNU の build ID、自動生成されるモジュール署名用の証明書、組み込みの initramfs に入る時刻です。許容する違いは、どちらのイメージでも同じ位置にあり、決められた大きさに収まっていなければなりません。comma の AGNOS 19.6、19.7、19.8 の純正カーネルは、どれもこの判定を通ります。そのため、実機で確認済みの WPA3 カーネルを、新しくビルドせずに使い回せます。

`native` の判定では、comma のカーネルに SAE のログ文字列 4 つと、RSNXE のログ文字列があるかを調べます。一部だけの場合や、SAE だけで RSNXE がない場合は、公開を止めます。

カーネルのコードが変わって保留になった場合は、新しい WPA3 boot イメージが必要です。ビルドして実機で確認し、pin を追加してください。


Maintenance
------

* **New boot images:** a replacement boot image needs a new command line tag (e.g. `wpa3.sae=2`), a new release tag and a new pin. The launcher only checks the tag, so a tag must always mean exactly one boot image. `pins.py` rejects pins that break this, and G6 compares against the published build.
* **Orphan commits:** publishing assumes comma's branches are orphan commits. If that changes, the nightly is held.
* **Scheduled runs:** GitHub may disable scheduled workflows after 60 days without repository activity. If the nightly stops, re-enable **Nightly WPA3** from the Actions tab.
* **Setting up a fork:** upload the boot image to the release named in `agnos/pins.json`, make `wpa3-ci` the default branch (scheduled workflows only run there), enable Actions and Issues, then run **Nightly WPA3** manually. A manual run builds both branches. `force` rebuilds even if the inputs haven't changed, but it doesn't skip any checks.

* **boot イメージの差し替え:** 新しい boot イメージには、新しいコマンドラインのタグ（例: `wpa3.sae=2`）、新しいリリースタグ、新しい pin が必要です。ランチャーはタグしか見ないため、1 つのタグは必ず 1 つの boot イメージを指すようにします。これに反する pin は `pins.py` が受け付けず、G6 は公開中のビルドとも照らし合わせます。
* **親なしのコミット:** 公開の仕組みは、comma のブランチが親なしのコミットであることを前提にしています。この前提が崩れた場合は、公開を止めます。
* **定期実行:** GitHub は、60 日間活動のないリポジトリの定期実行を止めることがあります。nightly が止まった場合は、Actions の画面から **Nightly WPA3** を有効に戻してください。
* **fork の準備:** `agnos/pins.json` に書かれたリリースに boot イメージをアップロードし、`wpa3-ci` を既定のブランチにします（定期実行は既定のブランチでしか動きません）。Actions と Issues を有効にしてから、**Nightly WPA3** を手動で実行します。手動実行でも両方のブランチを作ります。`force` を付けると入力が変わっていなくても作り直しますが、確認は省略しません。


Rolling back
------

Run **Roll back WPA3 nightly** and pick a branch. It restores `<branch>-lastgood`, the previous build, with a lease, then disables **Nightly WPA3**. This pauses publishing for **both** branches. A branch has no lastgood until its second build; in that case, nothing is changed. To resume, run `gh workflow enable nightly.yml --repo shunnag/openpilot`, or re-enable it from the Actions tab.

To go back to comma's openpilot, reinstall it from comma's URL. **The WPA3 kernel stays** until comma's next AGNOS version bump, because openpilot only reflashes AGNOS when the version changes. To remove it right away, reflash AGNOS from [flash.comma.ai](https://flash.comma.ai).

**Roll back WPA3 nightly** を実行し、戻すブランチを選びます。そのブランチの 1 つ前のビルド（`<branch>-lastgood`）を lease 付きで戻したあと、**Nightly WPA3** を無効にします。これで **両方のブランチ** の公開が止まります。2 回目のビルドまでは lastgood がないため、その場合は何も変更しません。再開するには `gh workflow enable nightly.yml --repo shunnag/openpilot` を実行するか、Actions の画面から有効に戻してください。

comma の openpilot に戻すには、comma の URL から入れ直します。openpilot はバージョンが変わったときにしか AGNOS を書き直さないため、**WPA3 カーネルは** comma が次に AGNOS のバージョンを上げるまで **残ります**。すぐに消したい場合は、[flash.comma.ai](https://flash.comma.ai) で AGNOS を書き直してください。


Development
------

The scripts need only Python 3 (standard library), git and bash. Each tree is composed in a bare repository with a temporary index, so nothing is checked out, and LFS objects are never downloaded or pushed. `.github/workflows` is removed from the composed tree. A post-check verifies that only the expected files changed: the launcher, `launch_env.sh`, `updated.py`, the manifest, `agnos.stock.json`, the three UI files and `wpa3/wpa_supplicant` with its license file. In `native` mode the manifest and `agnos.stock.json` stay unchanged.

The tests need the reference files in the gitignored `ref/nightly-chestnut/`. The upstream SHA they came from is in `UPSTREAM_SHA`. Tests on real boot images run only when `WPA3_REAL_BOOTS_DIR` points to a folder of images named `boot-<sha256>.img`.

スクリプトに必要なのは、Python 3（標準ライブラリのみ）、git、bash だけです。ツリーは bare リポジトリと一時的なインデックスだけで組み立てるので、作業ツリーへの展開も、LFS オブジェクトのダウンロードや push も行いません。組み立てたツリーからは `.github/workflows` を取り除きます。そのうえで、想定したファイル以外が変わっていないことを事後に確認します。想定しているのは、ランチャー、`launch_env.sh`、`updated.py`、manifest、`agnos.stock.json`、UI の 3 ファイル、`wpa3/wpa_supplicant` とそのライセンスのファイルです。`native` モードでは、manifest と `agnos.stock.json` は変えません。

テストには、git の管理対象外の `ref/nightly-chestnut/` にある参照ファイルが必要です。参照元の upstream の SHA は `UPSTREAM_SHA` にあります。実物の boot イメージを使うテストは、`WPA3_REAL_BOOTS_DIR` に `boot-<sha256>.img` という名前のイメージを置いたフォルダーを指定したときだけ実行されます。

```sh
export GIT_LFS_SKIP_SMUDGE=1 GIT_LFS_SKIP_PUSH=1
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/pins.py --repo /path/to/upstream.git --upstream <U> --out pin.json
python3 scripts/gates.py --repo /path/to/upstream.git --upstream <U> --pin-file pin.json --skip-download [--published <F>]
python3 scripts/compose.py --repo /path/to/upstream.git --upstream <U> --pin-file pin.json
python3 scripts/kernel_equiv.py <base boot.img> <new boot.img>
```

`--skip-download` skips G4 and is only for offline tests. `--published` is the currently published fork commit, used by G6. `compose.py` prints the new commit SHA, then the `WPA3-Inputs` hash. This is the SHA-256 of canonical JSON with the upstream commit, the hashes of both patches, the resolved pin, the hash of the `wpa_supplicant` license file and the hash of `compose.py`. The commit message also records the resolved pin in a `WPA3-Pin` trailer. The author and committer are fixed, and both dates are the upstream commit date.

`--skip-download` は G4 を省略するオプションで、オフラインのテスト専用です。`--published` には公開中の fork のコミットを渡し、G6 で使います。`compose.py` は、新しいコミットの SHA と `WPA3-Inputs` のハッシュをこの順に出力します。このハッシュは、upstream のコミット、両パッチのハッシュ、決定した pin、`wpa_supplicant` のライセンスのファイルのハッシュ、`compose.py` のハッシュを並べた正規化 JSON の SHA-256 です。コミットメッセージには、決定した pin も `WPA3-Pin` として記録します。author と committer は固定で、日時はどちらも upstream のコミットの日時を使います。
