openpilot + WPA3
======

**This is an unofficial fork for personal use. Automatically built kernels and wpa_supplicant builds are published WITHOUT any device test.** CI checks do not establish that a build boots or works on a device. The device-tested history is limited to one comma four: AGNOS 19.8 (`wpa3.sae=2`), AGNOS 19.9 (`wpa3.sae=3`), and the 19.8 → 19.9 migration on `nightly-chestnut`. This does not test future automatic builds or other devices. **No WPA3 kernel has ever booted on a comma 3X.** If an auto-built kernel doesn't boot, the bootloader should switch back to the previous kernel. This was seen on one comma four only. The fork retries at most 3 times and then installs comma's kernel for the new AGNOS. That can mean about 20 restarts, and a boot that hangs needs a power cycle. Recovery may need a computer and [flash.comma.ai](https://flash.comma.ai). comma has not reviewed or tested these builds. **Do not report problems to comma.**

**個人利用向けの非公式 fork です。自動ビルドのカーネルと wpa_supplicant は、実機テストなしで公開します。** CI の確認は、実機で起動・動作することを保証しません。実機で確認した履歴は、comma four 1 台での AGNOS 19.8（`wpa3.sae=2`）、AGNOS 19.9（`wpa3.sae=3`）、および `nightly-chestnut` での 19.8 → 19.9 の移行だけです。今後の自動ビルドや、ほかの端末を確認したものではありません。**comma 3X では、WPA3 カーネルを一度も起動していません。** 自動ビルドのカーネルが起動しない場合、ブートローダーは前のカーネルに戻るはずですが、これを確認したのも comma four 1 台だけです。fork は最大 3 回試したあと、新しい AGNOS 用の comma のカーネルを入れます。その間に約 20 回再起動することがあり、起動中に止まった場合は電源を入れ直す必要があります。復旧にはパソコンと [flash.comma.ai](https://flash.comma.ai) が必要になることがあります。これらのビルドは comma のレビューもテストも受けていません。**問題を comma に報告しないでください。**

**`release-mici-staging` and `release-tizi-staging` have NOT been tested on any device. Nobody has run them yet.** They combine comma's AGNOS 19.6 with this fork's WPA3 boot image from AGNOS 19.8 (`wpa3.sae=2`). That boot image was device-tested only on one comma four running `nightly-chestnut` on AGNOS 19.8. Running it with AGNOS 19.6, the release launcher, and switching from this fork's `nightly` (AGNOS 19.9) down to 19.6 are all untested. **No WPA3 kernel has ever booted on a comma 3X.** (On the comma four, the bootloader picked the right device tree from the WPA3 boot image, which suggests it selects by board ID rather than by position; this was not checked on a comma 3X.) If it fails on your device, you may need a computer and [flash.comma.ai](https://flash.comma.ai) to recover it. comma has not reviewed or tested these builds. Do not report problems with them to comma.

**`release-mici-staging` と `release-tizi-staging` は、どの実機でもテストしていません。まだ誰も動かしたことがありません。** これらは comma の AGNOS 19.6 に、この fork の AGNOS 19.8 用 WPA3 boot イメージ（`wpa3.sae=2`）を組み合わせたものです。この boot イメージを実機で確認したのは、AGNOS 19.8 の `nightly-chestnut` を動かした comma four 1 台だけです。AGNOS 19.6 との組み合わせ、release 用のランチャー、この fork の `nightly`（AGNOS 19.9）から 19.6 への切り替えは、どれも未確認です。**comma 3X では、WPA3 カーネルを一度も起動していません。**（comma four では、ブートローダーが WPA3 boot イメージから正しいデバイスツリーを選んでいたため、並び順ではなくボード ID で選んでいると考えられます。comma 3X では確かめていません。）端末で動かなかった場合、復旧にはパソコンと [flash.comma.ai](https://flash.comma.ai) が必要になることがあります。これらのビルドは comma のレビューもテストも受けていません。問題があっても comma に報告しないでください。

This fork adds WPA3 (SAE) Wi-Fi support to openpilot on the comma four. Every night, it rebuilds four prebuilt branches from comma's branches of the same name: two nightly branches and two UNTESTED release-staging branches. This `wpa3-ci` branch holds the workflows, scripts and patches that build them.

この fork は、comma four の openpilot に WPA3（SAE）の Wi-Fi 対応を追加します。comma の同名ブランチをもとに、nightly 2 ブランチと、実機では未確認の release-staging 2 ブランチ、計 4 つのビルド済みブランチを毎晩作り直します。この `wpa3-ci` ブランチには、それを作るワークフロー、スクリプト、パッチを置いています。


Branches
------

| branch             | URL                                         | description                                                                     |
|--------------------|---------------------------------------------|---------------------------------------------------------------------------------|
| `nightly`          | installer.comma.ai/shunnag/nightly          | comma's `nightly` with WPA3 support. Use this on a comma four without chestnut. |
| `nightly-chestnut` | installer.comma.ai/shunnag/nightly-chestnut | comma's `nightly-chestnut` with WPA3 support. For [chestnut](https://comma.ai/shop/chestnut). |
| `release-mici-staging` | installer.comma.ai/shunnag/release-mici-staging | **UNTESTED: never run on any device.** comma's release-mici-staging (comma four) with WPA3 support. |
| `release-tizi-staging` | installer.comma.ai/shunnag/release-tizi-staging | **UNTESTED: never run on any device; no WPA3 kernel has ever booted on a comma 3X.** comma's release-tizi-staging (comma 3X) with WPA3 support. |

The two nightly branches have the same source and the same WPA3 changes. `nightly-chestnut` also includes the large driving model for chestnut (about 773 MB, downloaded through Hugging Face LFS) and a debug panda build (`PANDA_DEBUG_BUILD=1`). These are bleeding edge development branches. Do not expect them to be stable.

| ブランチ | URL | 説明 |
|----------|-----|------|
| `nightly` | installer.comma.ai/shunnag/nightly | comma の `nightly` に WPA3 対応を追加。chestnut を使わない comma four 向け。 |
| `nightly-chestnut` | installer.comma.ai/shunnag/nightly-chestnut | comma の `nightly-chestnut` に WPA3 対応を追加。[chestnut](https://comma.ai/shop/chestnut) 向け。 |
| `release-mici-staging` | installer.comma.ai/shunnag/release-mici-staging | **未確認: どの実機でも動かしたことがありません。** comma の release-mici-staging（comma four）に WPA3 対応を追加。 |
| `release-tizi-staging` | installer.comma.ai/shunnag/release-tizi-staging | **未確認: どの実機でも動かしたことがなく、comma 3X では WPA3 カーネルを一度も起動していません。** comma の release-tizi-staging（comma 3X）に WPA3 対応を追加。 |

nightly の 2 つのブランチは、ソースも WPA3 の変更も同じです。`nightly-chestnut` には、chestnut 用の大きな運転モデル（約 773 MB、Hugging Face の LFS から取得）と、panda のデバッグビルド（`PANDA_DEBUG_BUILD=1`）が加わります。chestnut を使わない comma four では `nightly` を使ってください。どちらも開発中の最新ブランチなので、安定性は期待しないでください。


What's changed
------

Each build is comma's prebuilt commit with these changes:

1. **Kernel:** the `boot` entry in the AGNOS manifest points to a boot image that enables SAE in the qcacld-3.0 Wi-Fi driver ([commaai/agnos-kernel-sdm845#142](https://github.com/commaai/agnos-kernel-sdm845/pull/142)) and puts the RSNXE in the association request for SAE hash-to-element (H2E, [#143](https://github.com/commaai/agnos-kernel-sdm845/pull/143)). All other AGNOS images, including `system`, are comma's. `AGNOS_VERSION` is unchanged. comma's original manifest is kept next to it as `agnos.stock.json`.
2. **UI:** when the driver supports SAE, WPA3-only networks are listed and connected with a `sae` profile.
3. **Launcher and updater:** they install the WPA3 kernel if the running kernel doesn't have it. See [Kernel install](#kernel-install).
4. **wpa_supplicant:** a patched `wpa_supplicant` ships in `wpa3/` and runs instead of AGNOS's stock one. It enables H2E and has SAE security fixes. See [wpa_supplicant](#wpa_supplicant).
5. **Modem:** `modem.py` includes [commaai/openpilot#39061](https://github.com/commaai/openpilot/pull/39061). It applies a new APN while registration is denied and re-registers with `AT+COPS=2` / `AT+COPS=0` (at most twice, only while denied) if the modem had already tried to attach with the old APN and was denied. This is included only in `nightly`, `nightly-chestnut` and `release-mici-staging`, not `release-tizi-staging` (comma 3X, EG25; untested). It was device-tested only on one comma four (Quectel EG916Q-GL) with one SoftBank SIM. The local patch is dropped automatically once comma merges it or changes `modem.py` so it no longer applies.

各ビルドは、comma のビルド済みコミットに次の変更を加えたものです。

1. **カーネル:** AGNOS の manifest の `boot` を、qcacld-3.0 Wi-Fi ドライバの SAE を有効にした boot イメージに差し替えます（[commaai/agnos-kernel-sdm845#142](https://github.com/commaai/agnos-kernel-sdm845/pull/142)）。このイメージは、SAE の hash-to-element（H2E）に必要な RSNXE を接続要求に載せます（[#143](https://github.com/commaai/agnos-kernel-sdm845/pull/143)）。`system` を含むほかの AGNOS イメージは comma のままです。`AGNOS_VERSION` も変えません。comma の元の manifest は、`agnos.stock.json` として隣に残します。
2. **UI:** ドライバが SAE に対応していれば、WPA3 専用のネットワークを一覧に表示し、`sae` のプロファイルで接続します。
3. **ランチャーと updater:** 起動中のカーネルが WPA3 対応でなければ、WPA3 カーネルをインストールします。[Kernel install](#kernel-install) を参照してください。
4. **wpa_supplicant:** 修正版の `wpa_supplicant` を `wpa3/` に同梱し、AGNOS の純正の代わりに動かします。H2E を有効にし、SAE の脆弱性修正も入っています。[wpa_supplicant](#wpa_supplicant) を参照してください。
5. **モデム:** `modem.py` に [commaai/openpilot#39061](https://github.com/commaai/openpilot/pull/39061) を適用します。登録が拒否されている間も新しい APN を反映し、モデムが古い APN で登録しに行って拒否されていた場合は、`AT+COPS=2` / `AT+COPS=0` で登録し直します（拒否されている間だけ、多くて 2 回）。対象は `nightly`、`nightly-chestnut`、`release-mici-staging` のみで、`release-tizi-staging`（comma 3X、EG25、未確認）には含めません。実機確認は comma four（Quectel EG916Q-GL）1 台と SoftBank SIM 1 枚のみです。comma がマージするか、`modem.py` が変わってパッチが当たらなくなれば、ローカルのパッチは自動的に外れます。


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

AGNOS version updates use the same count. If the running kernel doesn't have the tag, each update attempt counts, and after 3 attempts the launcher and `updated` flash comma's manifest (`agnos.stock.json`) instead. If the running kernel already has the tag, the update uses the WPA3 manifest without counting; the tag proves only that the kernel started.

WPA3 の boot イメージは、カーネルのコマンドラインに `wpa3.sae=2` のようなタグを追加します（タグは boot イメージごとに異なります）。`launch_chffrplus.sh` は起動のたびに、このタグが `/proc/cmdline` にあるかを確認します。なければ、AGNOS 更新と同じ A/B の手順を実行します。待機中のスロットにイメージが用意済みならそのスロットに切り替え、なければ先にそのスロットへ書き込みます。`updated` も同じ条件で、バックグラウンドでイメージを準備します。

起動の繰り返しを防ぐため、ランチャーの試行は boot イメージのハッシュごとに 3 回までです。試行回数は `/data/wpa3_boot_attempts` に `<hash_raw> <count>` の形で記録します。3 回試してもタグがなければ試行をやめ、純正カーネルのまま動き続けます。boot イメージのハッシュが変わると回数はリセットされ、タグを確認できた時点で記録ファイルは削除されます。記録の内容が壊れている場合や、記録を保存できない場合も、試行を止めます。`updated` は回数を読むだけで、増やしません。

AGNOS のバージョン更新でも、同じ回数を使います。起動中のカーネルにタグがなければ、更新のたびに 1 回と数え、3 回を超えたらランチャーと `updated` は comma の manifest（`agnos.stock.json`）で書き込みます。起動中のカーネルにすでにタグがあれば、回数を数えずに WPA3 の manifest で更新します。タグで分かるのは、カーネルが起動したことだけです。


These retry limits help only when the kernel cannot start openpilot. The launcher marks a boot successful immediately (`abctl --set_success`). A kernel that boots but breaks Wi-Fi or crashes later is not undone automatically. A device without another working network cannot receive a revert; recovery may need [flash.comma.ai](https://flash.comma.ai).

この試行回数の制限が役立つのは、カーネルが openpilot の起動まで進めない場合だけです。ランチャーは起動するとすぐに成功を記録します（`abctl --set_success`）。起動しても Wi-Fi が壊れる場合や、あとで落ちる場合は、自動では元に戻りません。ほかに使えるネットワークがない端末は取り下げの更新を受け取れず、復旧に [flash.comma.ai](https://flash.comma.ai) が必要になることがあります。


wpa_supplicant
------

AGNOS ships Ubuntu's wpa_supplicant 2.10, which never uses SAE hash-to-element (H2E) by default and lacks SAE fixes from hostap 2.11/2.12. The fork ships `wpa3/wpa_supplicant`, built from Ubuntu's package with those fixes and with `sae_pwe=2` as the default ([commaai/agnos-builder#629](https://github.com/commaai/agnos-builder/pull/629)). With it, SAE uses H2E when the AP advertises it. NetworkManager's behavior doesn't change: WPA2/WPA3 transition networks and the hotspot stay WPA2-PSK.

On every boot, the launcher bind-mounts it over `/usr/sbin/wpa_supplicant` and restarts the service, but only if:

* the stock binary matches the SHA-256 recorded for that build (the manual builds target Ubuntu's `2:2.10-21ubuntu0.4`),
* the patched binary runs (`wpa_supplicant -v`), and
* it hasn't failed on this device before.

If the service isn't running the patched binary within 15 seconds, the launcher unmounts it and restarts the stock one. A runtime systemd drop-in in `/run` does the same if the patched binary exits abnormally later. Failures are recorded in `/data/wpa3_supplicant_failed` as `<sha256> <reason>` lines. One start failure, or 3 abnormal exits, turns the override off on that device. Nothing is written to the system partition: after leaving the fork and rebooting, the stock binary is back. To turn the override off by hand, add a line `<sha256 of wpa3/wpa_supplicant> start` to that file and reboot.

AGNOS には Ubuntu の wpa_supplicant 2.10 が入っています。この版は、既定では SAE の hash-to-element（H2E）を使わず、hostap 2.11/2.12 の SAE の修正も入っていません。fork は、Ubuntu のパッケージにその修正を入れ、既定値を `sae_pwe=2` にして作り直した `wpa3/wpa_supplicant` を同梱します（[commaai/agnos-builder#629](https://github.com/commaai/agnos-builder/pull/629)）。これで、AP が H2E を広告していれば、SAE で H2E を使います。NetworkManager の動作は変わらず、WPA2/WPA3 混在のネットワークとホットスポットは WPA2-PSK のままです。

ランチャーは起動のたびに、これを `/usr/sbin/wpa_supplicant` に bind mount して、サービスを再起動します。ただし、次の場合に限ります。

* 純正バイナリが、そのビルド用に記録した SHA-256 と一致する（手動ビルドの対象は Ubuntu の `2:2.10-21ubuntu0.4`）。
* 修正版が起動できる（`wpa_supplicant -v`）。
* その端末で、以前に失敗していない。

15 秒以内に修正版がサービスとして動いていなければ、ランチャーは bind mount を外して純正を起動し直します。起動後に修正版が異常終了した場合も、`/run` に置いた systemd の一時設定が同じように戻します。失敗は `/data/wpa3_supplicant_failed` に `<sha256> <理由>` の形で記録し、起動時の失敗 1 回、または異常終了 3 回で、その端末では差し替えをやめます。system パーティションには何も書き込まないので、fork をやめて再起動すれば純正に戻ります。手動で差し替えを止めるには、このファイルに `<wpa3/wpa_supplicant の sha256> start` という行を足して再起動してください。


An auto-built wpa_supplicant is used only if the stock binary matches; on failure the device keeps stock. The system image is probed before selecting an override. A rebuilt binary must pass its source, reproducibility, ABI and CI checks, including the separately enabled hwsim result gate. These checks are not a device test; automatic wpa_supplicant builds are published without device testing.

自動ビルドの wpa_supplicant は、純正バイナリが一致する場合だけ使い、失敗した端末では純正を使います。system イメージを調べてから差し替えを選びます。再ビルドしたバイナリには、ソース、再現性、ABI、CI、および別途有効にする hwsim 結果の確認が必要です。これらは実機テストではなく、自動ビルドの wpa_supplicant は実機テストなしで公開します。


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
| G3    | The upstream `agnos.py` is unchanged, and the launcher patch for this upstream launcher applies (exactly one of `launcher-wpa3.patch` / `launcher-wpa3-release.patch`). | upstream の `agnos.py` が変わっておらず、この upstream のランチャーに対応するパッチが当たる（`launcher-wpa3.patch` / `launcher-wpa3-release.patch` のうち、ちょうど 1 つ）。 |
| G4    | The pinned boot image downloads, and its decompressed SHA-256 and size match.               | pin の boot イメージをダウンロードでき、展開後の SHA-256 とサイズが一致する。                   |
| G5    | The UI patch applies, or is already applied.                                                | UI のパッチが当たる、または適用済みである。                                                     |
| G6    | The command line tag and the boot image hash still match one to one, compared with the published build. | 公開中のビルドと比べて、コマンドラインのタグと boot イメージのハッシュが 1 対 1 のままである。 |
| G8    | Probed stock supplicant and selected override agree; advisory in off/dryrun and during withdrawal. | 調査した純正 supplicant と差し替え先が一致する。off/dryrun と取り下げ時は警告のみ。 |
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
| `pinned`  | A manual pin or an enabled automatic pin exists for this version.                                                                  | The pinned WPA3 boot image is used.                                      |
| `derived` | comma's new stock kernel is the same kernel as a pin's stock kernel, and `agnos.py` is unchanged.             | That pin's WPA3 boot image is reused. The rest of AGNOS is comma's new version. |
| `native`  | comma's new stock kernel already supports SAE and RSNXE (H2E).                                                 | The boot image isn't replaced. The UI patch and the `wpa_supplicant` override are still applied. |
| hold      | Anything else, e.g. the kernel code changed, or a download failed.                                             | Nothing is published. A `nightly-hold` issue explains why.               |

"Same kernel" is checked on the decompressed boot images. The boot header, command line, device tree and kernel config must be identical. In the kernel image, only build identity may differ: the build date strings, the GNU build ID, the autogenerated module signing certificate and the timestamps in the built-in initramfs. Each allowed difference must be at the same place in both images and within a size limit. comma's stock kernels for AGNOS 19.6, 19.7 and 19.8 all pass this check, so the WPA3 kernel is reused without a new build. A `derived` pin reuses a kernel from a different AGNOS system image; that pairing itself is not device-tested, even if the original kernel was tested.

The `native` check looks for four SAE log strings and the RSNXE log string in comma's kernel. A partial match, or SAE without RSNXE, holds the nightly.

With automatic kernel publishing enabled, a changed kernel becomes pending and requests follow. Otherwise it holds for a manual pin. Pending issues become red holds after 48 hours (a rate deferral gets until its deadline plus 48 hours), or immediately when follow records a hold.

comma が `AGNOS_VERSION` を上げると、`scripts/pins.py` は新しいバージョンを次の 4 通りのどれかで扱います。

| モード    | 条件                                                                                           | 結果                                                                            |
|-----------|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| `pinned`  | この版の手動 pin または有効な自動 pin がある。                                             | pin の WPA3 boot イメージを使う。                                               |
| `derived` | comma の新しい純正カーネルが、既存の pin の元になった純正カーネルと同じで、`agnos.py` も変わっていない。 | その pin の WPA3 boot イメージを使い回す。ほかの AGNOS は comma の新しいもの。 |
| `native`  | comma の新しい純正カーネルが、すでに SAE と RSNXE（H2E）に対応している。                     | boot イメージは差し替えない。UI のパッチと `wpa_supplicant` の差し替えは続ける。 |
| 保留      | それ以外（カーネルのコードが変わった、ダウンロードに失敗した、など）。                       | 公開しない。`nightly-hold` の issue で理由を知らせる。                          |

「同じカーネル」かどうかは、展開した boot イメージで判定します。boot のヘッダー、コマンドライン、デバイスツリー、カーネル設定は完全に一致している必要があります。カーネル本体で違ってよいのは、ビルドのたびに変わる情報だけです。具体的には、ビルド日時の文字列、GNU の build ID、自動生成されるモジュール署名用の証明書、組み込みの initramfs に入る時刻です。許容する違いは、どちらのイメージでも同じ位置にあり、決められた大きさに収まっていなければなりません。comma の AGNOS 19.6、19.7、19.8 の純正カーネルは、どれもこの判定を通ります。そのため、WPA3 カーネルを新しくビルドせずに使い回せます。`derived` の pin は、別の AGNOS system イメージ用のカーネルを使い回します。元のカーネルが確認済みでも、新しい組み合わせ自体は実機で確認していません。

`native` の判定では、comma のカーネルに SAE のログ文字列 4 つと、RSNXE のログ文字列があるかを調べます。一部だけの場合や、SAE だけで RSNXE がない場合は、公開を止めます。

カーネルの自動公開が有効なら、カーネル変更時は pending として follow を要求します。それ以外は手動の pin が必要です。pending は 48 時間後（公開間隔による延期は期限の 48 時間後）、または follow が hold を記録した時点で赤い hold の issue になります。


Maintenance
------

* **New boot images:** a replacement boot image needs a new command line tag (e.g. `wpa3.sae=2`), a new release tag and a new pin. The launcher only checks the tag, so a tag must always mean exactly one boot image. `pins.py` rejects pins that break this, and G6 compares against the published build.
* **Orphan commits:** publishing assumes comma's branches are orphan commits. If that changes, the nightly is held.
* **Scheduled runs:** GitHub may disable scheduled workflows after 60 days without repository activity. If the nightly stops, re-enable **Nightly WPA3** from the Actions tab.
* **Setting up a fork:** upload the boot image to the release named in `agnos/pins.json`, make `wpa3-ci` the default branch (scheduled workflows only run there), enable Actions and Issues, then run **Nightly WPA3** manually. A manual run builds all four branches. `force` rebuilds even if the inputs haven't changed, but it doesn't skip any checks.

* **boot イメージの差し替え:** 新しい boot イメージには、新しいコマンドラインのタグ（例: `wpa3.sae=2`）、新しいリリースタグ、新しい pin が必要です。ランチャーはタグしか見ないため、1 つのタグは必ず 1 つの boot イメージを指すようにします。これに反する pin は `pins.py` が受け付けず、G6 は公開中のビルドとも照らし合わせます。
* **親なしのコミット:** 公開の仕組みは、comma のブランチが親なしのコミットであることを前提にしています。この前提が崩れた場合は、公開を止めます。
* **定期実行:** GitHub は、60 日間活動のないリポジトリの定期実行を止めることがあります。nightly が止まった場合は、Actions の画面から **Nightly WPA3** を有効に戻してください。
* **fork の準備:** `agnos/pins.json` に書かれたリリースに boot イメージをアップロードし、`wpa3-ci` を既定のブランチにします（定期実行は既定のブランチでしか動きません）。Actions と Issues を有効にしてから、**Nightly WPA3** を手動で実行します。手動実行でも 4 つすべてのブランチを作ります。`force` を付けると入力が変わっていなくても作り直しますが、確認は省略しません。


Automatic kernel builds
------

The owner controls `WPA3_FOLLOW_MODE`: `off` → `dryrun` → `state` → `on`. In `on`, all four allowed branches, including `release-tizi-staging`, adopt a new automatic pin in the same run. Automatic releases are prereleases and do not become GitHub's latest release. They are published without any device test. Each release carries its exact pin, gate output, toolchain URL and SHA-256, asset names, baseline device type and supplicant status in `provenance.json`; release notes and the status block are rendered from that evidence.

所有者が `WPA3_FOLLOW_MODE` を `off` → `dryrun` → `state` → `on` の順に切り替えます。`on` では、`release-tizi-staging` を含む許可済みの 4 ブランチすべてが、同じ実行で新しい自動 pin を採用します。自動リリースは prerelease として実機テストなしで公開し、GitHub の latest にはしません。各リリースの `provenance.json` に、正確な pin、確認結果、ツールチェーンの URL と SHA-256、ファイル名、基準とした実機の種類、supplicant の状態を記録し、リリースノートと状態欄をその記録から生成します。

| Checks | English | 日本語 |
|---|---|---|
| K0–K2 | Input shape, source discovery and trusted recipe. | 入力形式、ソースの特定、信頼するビルド手順。 |
| K3–K4, K4(e), K4(f) | Limited changes from a tested baseline, including Wi-Fi dependencies and device trees. | 確認済みの基準からの変更範囲、Wi-Fi の依存ファイルとデバイスツリー。 |
| K5–K8, K7b | Stock rebuild identity, patch proof, configuration and changed objects; Wi-Fi object identity remains advisory until qualified. | 純正再ビルドの一致、パッチ、設定、変更したオブジェクト。Wi-Fi オブジェクトの一致は適格性確認までは参考情報。 |
| K9–K11 | Image integrity and format, unique reserved tags, and a verified stock revert image. | イメージの整合性と形式、重複しない予約済みタグ、確認済みの純正への復帰イメージ。 |
| K12–K13 | Brakes, global publication limit and immutable release verification. | 停止条件、全体の公開間隔、変更不能なリリースの検証。 |

The global limit is one automatic kernel per 7 days and at most 3 untested kernels in a row. Failures open `follow-hold`; risk holds may produce a draft for owner review, while integrity failures cannot be approved. Held inputs retry after 7 days or a gate change (source discovery also retries when relevant refs change). A yellow `nightly-pending` means a branch has requested follow, not that it published. The public signing key verifies integrity, not who built the image. Nightly's G1–G8 checks still apply.

全体の制限は自動カーネルを 7 日に 1 回まで、実機未確認のカーネルを連続 3 回までです。失敗は `follow-hold` で知らせます。リスクによる停止では所有者の確認用 draft を作ることがありますが、整合性の失敗は承認で解除できません。停止した入力は 7 日後か確認コードの変更後に再試行します（ソース特定は関連 ref の変更でも再試行）。黄色の `nightly-pending` は follow を要求した状態で、公開済みという意味ではありません。公開テスト鍵による署名は整合性の確認で、ビルドした人の証明ではありません。nightly の G1〜G8 も適用します。


Rolling back
------

Run **Roll back WPA3 nightly** and pick a branch. It restores `<branch>-lastgood`, the previous build, with a lease, then disables **Nightly WPA3**. This pauses publishing for **all four** branches. A branch, including each release-staging branch, has no `<branch>-lastgood` until its second build; in that case, nothing is changed. To resume, run `gh workflow enable nightly.yml --repo shunnag/openpilot`, or re-enable it from the Actions tab.

Prefer **follow-admin → revoke** with the release tag and a reason for an automatic kernel. It pauses automatic kernels, marks the release WITHDRAWN and dispatches nightly with `upstream=published`. Each affected branch composes its already-published upstream with comma's kernel for the same AGNOS version and the reserved revert tag. This does not downgrade AGNOS. A bad release does not replace `-lastgood`. No issue label triggers withdrawal. Offline devices need another network or [flash.comma.ai](https://flash.comma.ai). **Roll back WPA3 nightly** also disables follow; restoring `-lastgood` may restore another untested kernel or downgrade AGNOS, which has not been tested.

自動カーネルは **follow-admin → revoke** でリリースタグと理由を指定して取り下げる方法を優先してください。自動公開を停止し、リリースを WITHDRAWN にして、`upstream=published` で nightly を実行します。影響する各ブランチは、公開中の upstream に同じ AGNOS 用の comma のカーネルと予約済みの復帰タグを組み合わせます。AGNOS のダウングレードはしません。問題のあるリリースで `-lastgood` を上書きしません。issue のラベルでは取り下げを起動しません。オフラインの端末には別のネットワークか [flash.comma.ai](https://flash.comma.ai) が必要です。**Roll back WPA3 nightly** は follow も無効にします。`-lastgood` への復元では別の未確認カーネルに戻る場合や、未確認の AGNOS ダウングレードになる場合があります。

To go back to comma's openpilot, reinstall it from comma's URL. **The WPA3 kernel stays** until comma's next AGNOS version bump, because openpilot only reflashes AGNOS when the version changes. To remove it right away, reflash AGNOS from [flash.comma.ai](https://flash.comma.ai).

**Roll back WPA3 nightly** を実行し、戻すブランチを選びます。そのブランチの 1 つ前のビルド（`<branch>-lastgood`）を lease 付きで戻したあと、**Nightly WPA3** を無効にします。これで **4 つすべてのブランチ** の公開が止まります。release-staging の各ブランチも、2 回目のビルドまでは `<branch>-lastgood` がないため、その場合は何も変更しません。再開するには `gh workflow enable nightly.yml --repo shunnag/openpilot` を実行するか、Actions の画面から有効に戻してください。

comma の openpilot に戻すには、comma の URL から入れ直します。openpilot はバージョンが変わったときにしか AGNOS を書き直さないため、**WPA3 カーネルは** comma が次に AGNOS のバージョンを上げるまで **残ります**。すぐに消したい場合は、[flash.comma.ai](https://flash.comma.ai) で AGNOS を書き直してください。


Development
------

The compose and pin scripts need only Python 3 (standard library), git and bash. Each tree is composed in a bare repository with a temporary index, so nothing is checked out, and LFS objects are never downloaded or pushed. `.github/workflows` is removed from the composed tree. A post-check verifies that only the expected files changed: the launcher, `launch_env.sh`, `updated.py`, the manifest, `agnos.stock.json`, the three UI files and `wpa3/wpa_supplicant` with its license file. `modem.py` may change only when the modem patch was applied; it gets the same Python compile check as other changed `.py` files. In `native` mode the manifest and `agnos.stock.json` stay unchanged.

The tests need the reference files in the gitignored `ref/nightly-chestnut/` and `ref/release-staging/`; missing fixtures fail the tests. The upstream SHA each fixture came from is in its `UPSTREAM_SHA`. The existing stock/WPA3 comparison tests run only when `WPA3_REAL_BOOTS_DIR` points to a folder of images named `boot-<sha256>.img`.

`bootimg.py` additionally requires the `openssl` CLI. It parses, repacks and verifies Android v0 images with 4096-byte pages and no external ramdisk or second stage. Its synthetic tests run offline; the repacker and rebuild reference tests also run when `/Volumes/agnos` is mounted. `kernel_equiv.py` defaults to `--mode stock`, which is the comparator used by the pin resolver. `--mode rebuild` additionally permits DTB reordering (preserving duplicates) and bounded changes to `proc_banner`.

compose と pin のスクリプトに必要なのは、Python 3（標準ライブラリのみ）、git、bash だけです。ツリーは bare リポジトリと一時的なインデックスだけで組み立てるので、作業ツリーへの展開も、LFS オブジェクトのダウンロードや push も行いません。組み立てたツリーからは `.github/workflows` を取り除きます。そのうえで、想定したファイル以外が変わっていないことを事後に確認します。想定しているのは、ランチャー、`launch_env.sh`、`updated.py`、manifest、`agnos.stock.json`、UI の 3 ファイル、`wpa3/wpa_supplicant` とそのライセンスのファイルです。`modem.py` の変更はモデムのパッチが適用された場合だけ許可し、ほかの変更された `.py` ファイルと同じコンパイル確認を行います。`native` モードでは、manifest と `agnos.stock.json` は変えません。

テストには、git の管理対象外の `ref/nightly-chestnut/` と `ref/release-staging/` にある参照ファイルが必要です。参照ファイルがなければ、テストは失敗します。参照元の upstream の SHA は、それぞれの `UPSTREAM_SHA` にあります。既存の stock/WPA3 比較テストは、`WPA3_REAL_BOOTS_DIR` に `boot-<sha256>.img` という名前のイメージを置いたフォルダーを指定したときだけ実行されます。

`bootimg.py` には追加で `openssl` CLI が必要です。4096 バイトのページを使い、外部 ramdisk と second stage のない Android v0 イメージを解析・再パック・署名検証します。合成データのテストはオフラインで実行され、`/Volumes/agnos` がマウントされていれば再パックと再ビルド比較の参照テストも実行されます。`kernel_equiv.py` の既定値は pin resolver と同じ `--mode stock` です。`--mode rebuild` は、重複を保持した DTB の並べ替えと、範囲を制限した `proc_banner` の変更も許容します。

```sh
export GIT_LFS_SKIP_SMUDGE=1 GIT_LFS_SKIP_PUSH=1
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/pins.py --repo /path/to/upstream.git --upstream <U> --out pin.json
python3 scripts/gates.py --repo /path/to/upstream.git --upstream <U> --pin-file pin.json --skip-download [--published <F>]
python3 scripts/compose.py --repo /path/to/upstream.git --upstream <U> --pin-file pin.json
python3 scripts/kernel_equiv.py <base boot.img> <new boot.img>
python3 scripts/kernel_equiv.py --mode rebuild <stock boot.img> <rebuilt boot.img>
python3 scripts/bootimg.py selftest <boot.img> --key <private.pem>
python3 scripts/bootimg.py verify <boot.img> --pubkey <public.pem>
python3 scripts/bootimg.py tag <boot.img> --tag wpa3.sae=4 --key <private.pem> --out <tagged.img>
```

`--skip-download` skips G4 and is only for offline tests. `--published` is the currently published fork commit, used by G6. Both `gates.py` and `compose.py` accept `--modem apply|skip`, defaulting to `skip`. With `apply`, G5 reports whether the modem patch applies, is already upstream, or is skipped because it no longer applies; the last case does not block publication. `compose.py` prints the new commit SHA, then the `WPA3-Inputs` hash. This is the SHA-256 of canonical JSON with the upstream commit, the hashes of the chosen launcher patch and `ui-wpa3.patch`, the resolved pin, the hash of the `wpa_supplicant` license file and the hash of `compose.py`. With `--modem apply`, the JSON also includes the modem mode and the SHA-256 of `modem-apn.patch`; `skip` retains the existing inputs JSON. The commit message also records the resolved pin in a `WPA3-Pin` trailer, immediately followed by `WPA3-Launcher-Patch` with the chosen patch's file name, then `WPA3-Modem-Patch` with `applied`, `already upstream`, `skipped (does not apply)` or `off`. The author and committer are fixed, and both dates are the upstream commit date.

`--skip-download` は G4 を省略するオプションで、オフラインのテスト専用です。`--published` には公開中の fork のコミットを渡し、G6 で使います。`gates.py` と `compose.py` は `--modem apply|skip` を受け取り、既定値は `skip` です。`apply` の場合は、モデムのパッチが当たるか、upstream に取り込み済みか、当たらないため省略するかを G5 で表示します。当たらなくても公開は止めません。`compose.py` は、新しいコミットの SHA と `WPA3-Inputs` のハッシュをこの順に出力します。このハッシュは、upstream のコミット、選ばれたランチャーパッチと `ui-wpa3.patch` のハッシュ、決定した pin、`wpa_supplicant` のライセンスのファイルのハッシュ、`compose.py` のハッシュを並べた正規化 JSON の SHA-256 です。`--modem apply` では、モデムのモードと `modem-apn.patch` の SHA-256 も JSON に含めます。`skip` では既存の入力 JSON を保ちます。コミットメッセージには、決定した pin を `WPA3-Pin` として記録し、その直後に `WPA3-Launcher-Patch` として選ばれたパッチのファイル名、続けて `WPA3-Modem-Patch` として `applied`、`already upstream`、`skipped (does not apply)`、`off` のいずれかを記録します。author と committer は固定で、日時はどちらも upstream のコミットの日時を使います。


Automatic follow state
------

Bot state commits land on `wpa3-ci`. Use `git pull --rebase` before pushing; never force-push this branch. Commit at least every 60 days if upstream goes quiet, and check that scheduled workflows remain enabled. Before enabling automatic publication, the owner should post and pin an announcement for all four branches with the start date and the instructions above for returning to comma's openpilot.

The owner can run **follow-admin** with an action, target and note: `revoke` withdraws an automatic release and pauses publishing; `mark-tested` records the release's tested device (`mici` = comma four, `tizi` = comma 3X); `approve` publishes a risk-hold draft after verification, recording `device_tested=yes|no`; `unpause` clears the pause and its issue mirror; `retry` clears a stock-hash attempt and requests follow. Approval cannot bypass integrity failures. Changing the mode is the owner's separate repository-variable operation. Turning automatic follow off is a brake; it does not undo a kernel. Withdrawn pins still resolve to their stock revert in every mode.

bot の状態コミットは `wpa3-ci` に入ります。push 前に `git pull --rebase` を行い、このブランチを force-push しないでください。upstream が静かな場合も少なくとも 60 日ごとにコミットし、定期実行が有効か確認してください。自動公開を有効にする前に、所有者が開始日と上記の comma への戻し方を含む、4 ブランチ向けの告知 issue を投稿・固定してください。

所有者は **follow-admin** で操作、対象、メモを指定できます。`revoke` は自動リリースを取り下げて公開を停止し、`mark-tested` は確認した実機（`mici` = comma four、`tizi` = comma 3X）を記録します。`approve` はリスクで停止した draft を再検証して公開し、`device_tested=yes|no` を記録します。`unpause` は停止状態と対応する issue を解除し、`retry` は stock ハッシュの試行記録を消して follow を要求します。承認で整合性の失敗を迂回することはできません。モード変更は別途、所有者がリポジトリ変数を操作します。自動 follow の無効化は停止操作で、カーネルを元に戻す操作ではありません。取り下げた pin は、どのモードでも純正への復帰イメージを選びます。

<!-- wpa3-status:begin -->

`WPA3_FOLLOW_MODE` is currently `off`. / 現在の `WPA3_FOLLOW_MODE` は `off` です。

| Automatic release | Status | Tested devices |
|---|---|---|
| none | No automatic kernel pins | none |

<!-- wpa3-status:end -->
