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

1. **Kernel:** the `boot` entry in the AGNOS manifest points to a boot image that enables SAE in the qcacld-3.0 Wi-Fi driver ([commaai/agnos-kernel-sdm845#142](https://github.com/commaai/agnos-kernel-sdm845/pull/142)). All other AGNOS images, including `system`, are comma's. `AGNOS_VERSION` is unchanged.
2. **UI:** when the driver supports SAE, WPA3-only networks are listed and connected with a `sae` profile.
3. **Launcher and updater:** they install the WPA3 kernel if the running kernel doesn't have it. See [Kernel install](#kernel-install).

各ビルドは、comma のビルド済みコミットに次の変更を加えたものです。

1. **カーネル:** AGNOS の manifest の `boot` を、qcacld-3.0 Wi-Fi ドライバの SAE を有効にした boot イメージに差し替えます（[commaai/agnos-kernel-sdm845#142](https://github.com/commaai/agnos-kernel-sdm845/pull/142)）。`system` を含むほかの AGNOS イメージは comma のままです。`AGNOS_VERSION` も変えません。
2. **UI:** ドライバが SAE に対応していれば、WPA3 専用のネットワークを一覧に表示し、`sae` のプロファイルで接続します。
3. **ランチャーと updater:** 起動中のカーネルが WPA3 対応でなければ、WPA3 カーネルをインストールします。[Kernel install](#kernel-install) を参照してください。


Installing
------

The first install needs a network that isn't WPA3-only: WPA2, WPA2/WPA3 mixed mode, a phone hotspot, or LTE. AGNOS setup and the stock kernel can't join WPA3-only networks. After install, the WPA3 kernel is flashed through the normal A/B AGNOS update, which may download about 1 GB. After the next reboot, WPA3-only networks work.

This fork was tested only on the comma four. The comma 3X uses the same kernel and firmware, but it is untested.

初回のインストールには、WPA3 専用ではないネットワーク（WPA2、WPA2/WPA3 混在モード、スマートフォンのテザリング、LTE のいずれか）が必要です。AGNOS のセットアップ画面と純正カーネルは、WPA3 専用のネットワークにつながりません。インストール後、通常の A/B 方式の AGNOS 更新で WPA3 カーネルを書き込みます。このとき約 1 GB をダウンロードすることがあります。再起動後は、WPA3 専用のネットワークも使えます。

動作確認は comma four でのみ行っています。comma 3X はカーネルとファームウェアが同じですが、未確認です。


Kernel install
------

The WPA3 boot image adds `wpa3.sae=1` to the kernel command line. On every boot, `launch_chffrplus.sh` looks for this tag in `/proc/cmdline`. If it's missing, the launcher runs the same A/B path as an AGNOS update: it swaps to the inactive slot if that slot already has the image, and otherwise flashes the slot first. `updated` stages the image in the background under the same condition.

To prevent boot loops, the launcher tries at most 3 times per boot image hash. Attempts are recorded in `/data/wpa3_boot_attempts` as `<hash_raw> <count>`. After 3 attempts, it stops, and the device keeps running the stock kernel. Regular AGNOS version updates still work. The count resets when the boot image hash changes, and the file is removed once the tag is present. A malformed count, or a count that can't be saved, also stops the retries. `updated` only reads the count.

WPA3 の boot イメージは、カーネルのコマンドラインに `wpa3.sae=1` を追加します。`launch_chffrplus.sh` は起動のたびに、このタグが `/proc/cmdline` にあるかを確認します。なければ、AGNOS 更新と同じ A/B の手順を実行します。待機中のスロットにイメージが用意済みならそのスロットに切り替え、なければ先にそのスロットへ書き込みます。`updated` も同じ条件で、バックグラウンドでイメージを準備します。

起動の繰り返しを防ぐため、ランチャーの試行は boot イメージのハッシュごとに 3 回までです。試行回数は `/data/wpa3_boot_attempts` に `<hash_raw> <count>` の形で記録します。3 回試してもタグがなければ試行をやめ、純正カーネルのまま動き続けます。通常の AGNOS のバージョン更新は、その後も行われます。boot イメージのハッシュが変わると回数はリセットされ、タグを確認できた時点で記録ファイルは削除されます。記録の内容が壊れている場合や、記録を保存できない場合も、試行を止めます。`updated` は回数を読むだけで、増やしません。


Nightly builds
------

The **Nightly WPA3** workflow runs every day at 11:00 UTC (20:00 JST), with a catch-up run at 12:30 UTC (21:30 JST). It rebuilds each branch from comma's latest commit. comma's branches are squashed orphan commits, so each build is a new commit on top of theirs, and nothing is merged. Builds are deterministic: the same inputs always produce the same commit SHA. If comma hasn't published a new build, the branch is left as is.

**Nightly WPA3** ワークフローは、毎日 11:00 UTC（20:00 JST）に実行されます。取りこぼしに備えて、12:30 UTC（21:30 JST）にも実行されます。実行のたびに、comma の最新コミットをもとに各ブランチを作り直します。comma のブランチは履歴を 1 つにまとめた親なしのコミットなので、各ビルドはその上に新しいコミットを 1 つ作るだけで、マージはしません。ビルドは再現可能で、入力が同じなら必ず同じコミット SHA になります。comma が新しいビルドを出していなければ、ブランチは変えません。

Before publishing, the workflow checks:

公開前に、次の項目を確認します。

| check | English                                                                       | 日本語                                                                              |
|-------|-------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| G1    | The upstream `AGNOS_VERSION` has a pin in `agnos/pins.json`.                  | upstream の `AGNOS_VERSION` に対応する pin が `agnos/pins.json` にある。           |
| G2    | The upstream stock `boot` and `system` hashes match the pin's `derived_from`. | upstream の純正 `boot` と `system` のハッシュが、pin の `derived_from` と一致する。 |
| G3    | The upstream `agnos.py` is unchanged, and the launcher patch applies.         | upstream の `agnos.py` が変わっておらず、ランチャーのパッチが当たる。               |
| G4    | The pinned boot image downloads, and its decompressed SHA-256 and size match. | pin の boot イメージをダウンロードでき、展開後の SHA-256 とサイズが一致する。       |
| G5    | The UI patch applies, or is already applied.                                  | UI のパッチが当たる、または適用済みである。                                         |

If a check fails, that branch isn't published and keeps its last build. The workflow opens or updates one issue per branch, labeled `nightly-hold` and `branch:<branch>`, and closes it after the next successful build. An AGNOS version bump holds the nightly this way until a pin for the new version is added.

After publishing, the workflow checks that installer.comma.ai serves an installer for the branch. If this fails, it opens a `nightly-smoke` issue but keeps the new build.

確認に失敗したブランチは公開せず、前回のビルドのままにします。ワークフローは、`nightly-hold` と `branch:<branch>` のラベルを付けた issue をブランチごとに 1 件作成または更新し、次に公開できたときに閉じます。AGNOS のバージョンが上がったときも同じように公開を止め、新しいバージョン用の pin が追加されるまで待ちます。

公開後は、installer.comma.ai がそのブランチ用のインストーラーを返すかを確認します。失敗した場合は `nightly-smoke` の issue を作りますが、公開した新しいビルドはそのまま残します。


Maintenance
------

* **New boot images:** a replacement boot image needs a new command line tag (e.g. `wpa3.sae=2`), a new release tag and a new pin. The launcher only checks the tag, so devices already running a tagged kernel won't reflash an image with the same tag.
* **Orphan commits:** publishing assumes comma's branches are orphan commits. If that changes, the nightly is held.
* **Scheduled runs:** GitHub may disable scheduled workflows after 60 days without repository activity. If the nightly stops, re-enable **Nightly WPA3** from the Actions tab.
* **Setting up a fork:** upload the boot image to the release named in `agnos/pins.json`, make `wpa3-ci` the default branch (scheduled workflows only run there), enable Actions and Issues, then run **Nightly WPA3** manually. A manual run builds both branches. `force` rebuilds even if the inputs haven't changed, but it doesn't skip any checks.

* **boot イメージの差し替え:** 新しい boot イメージには、新しいコマンドラインのタグ（例: `wpa3.sae=2`）、新しいリリースタグ、新しい pin が必要です。ランチャーはタグしか見ないため、タグが同じだと、すでにタグ付きのカーネルで動いている端末には書き込まれません。
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

The scripts need only Python 3 (standard library), git and bash. Each tree is composed in a bare repository with a temporary index, so nothing is checked out, and LFS objects are never downloaded or pushed. `.github/workflows` is removed from the composed tree, and a post-check verifies that only the 7 expected files changed.

The tests need the reference files in the gitignored `ref/nightly-chestnut/`. The upstream SHA they came from is in `UPSTREAM_SHA`.

スクリプトに必要なのは、Python 3（標準ライブラリのみ）、git、bash だけです。ツリーは bare リポジトリと一時的なインデックスだけで組み立てるので、作業ツリーへの展開も、LFS オブジェクトのダウンロードや push も行いません。組み立てたツリーからは `.github/workflows` を取り除き、想定した 7 ファイル以外が変わっていないことを事後に確認します。

テストには、git の管理対象外の `ref/nightly-chestnut/` にある参照ファイルが必要です。参照元の upstream の SHA は `UPSTREAM_SHA` にあります。

```sh
export GIT_LFS_SKIP_SMUDGE=1 GIT_LFS_SKIP_PUSH=1
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/gates.py --repo /path/to/upstream.git --upstream <U> --skip-download
python3 scripts/compose.py --repo /path/to/upstream.git --upstream <U>
```

`--skip-download` skips G4 and is only for offline tests. `compose.py` prints the new commit SHA, then the `WPA3-Inputs` hash. This is the SHA-256 of canonical JSON with the upstream commit, the hashes of both patches, the pin and the hash of `compose.py`. The author and committer are fixed, and both dates are the upstream commit date.

`--skip-download` は G4 を省略するオプションで、オフラインのテスト専用です。`compose.py` は、新しいコミットの SHA と `WPA3-Inputs` のハッシュをこの順に出力します。このハッシュは、upstream のコミット、両パッチのハッシュ、pin、`compose.py` のハッシュを並べた正規化 JSON の SHA-256 です。author と committer は固定で、日時はどちらも upstream のコミットの日時を使います。
