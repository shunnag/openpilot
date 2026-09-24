# openpilot nightly-chestnut + WPA3

**個人利用向けの非公式カーネルです。comma 公式のサポート対象ではありません。**
対象は comma four（mici）、現在の pin は AGNOS 19.8 です。

この `wpa3-ci` ブランチには配布用 openpilot 本体ではなく、生成用 workflow・スクリプト・パッチを置きます。
毎日 20:00 JST（11:00 UTC）と、取りこぼし確認用の 21:30 JST（12:30 UTC）に、
commaai/openpilot のその時点の `nightly-chestnut` を親とする WPA3 対応コミットを作り、
この fork の `nightly-chestnut` を更新します。upstream は毎回置き換わる orphan コミットなので、履歴の merge は行いません。
同じ入力の再実行は同じコミット SHA になります。upstream が更新されなかった日は変更しません。

## インストール

インストール URL: **https://installer.comma.ai/shunnag/nightly-chestnut**

**初回インストールには WPA3-only 以外の通信手段が必要です。**
WPA2、WPA2/WPA3 mixed、WPA2 のスマートフォン hotspot、または利用可能な LTE を用意してください。
AGNOS setup と初期の stock カーネルには SAE 対応がなく、WPA3-only のネットワークだけでは最初のダウンロードを完了できません。
初回は AGNOS の通常の A/B 更新により **約 1 GB の AGNOS ダウンロード**が発生し得ます。
通信容量と電源に余裕がある状態で進めてください。

AGNOS_VERSION は `19.8` のまま、system イメージを含む boot 以外の manifest エントリは公式のままです。
boot だけを署名・実機検証済みの WPA3-SAE 対応イメージに置き換えます。
UI はドライバの SAE 対応を確認し、WPA3-only のアクセスポイントを表示して `sae` プロファイルで接続します。

## 起動時の適用と停止条件

稼働中カーネルの `/proc/cmdline` に独立したトークン `wpa3.sae=1` がない場合、
AGNOS のバージョンが同じでも既存の A/B 経路を実行します。
非稼働スロットを検証し、用意済みなら切り替え、そうでなければ通常の updater が非稼働スロットを書き込んで切り替えます。
バックグラウンドの updated も同じ条件で準備しますが、試行回数を増やすのはランチャーだけです。

`/data/wpa3_boot_attempts` に `<boot.hash_raw> <count>` を保存し、
同じ boot ハッシュに対する追加トリガーは最大 3 回に制限します。
3 回後もタグがなければ追加トリガーを停止し、stock のバージョン比較による更新は継続します。
manifest の boot ハッシュが変われば回数をリセットし、タグを検出したら記録ファイルを削除します。
同じハッシュの不正なカウンタも停止扱いにし、カウンタを保存できない場合も追加トリガーを実行しません。

## 公開開始と保守

1. release `agnos-19.8-wpa3.1` に `agnos/pins.json` の URL と一致する boot `.img.xz` を配置します。
   raw SHA-256 は `18c888b86f8846cd49bf3312b2c02fb60fc3f5e2f165d3a77417a7ad4e2c5549`、raw サイズは 46,962,688 bytes です。
2. `wpa3-ci` を fork の default branch に設定し、Actions と Issues を有効にします。
   schedule は default branch 上で動作します。`nightly-chestnut` と `nightly-chestnut-lastgood` に対する bot の force-push を許可してください。
3. Actions の **Nightly WPA3** を手動実行して最初の公開を確認します。
   `force=true` は入力一致によるスキップを解除しますが、ゲートは省略しません。

追加トリガーはカーネル cmdline のタグで判定します。同じ AGNOS バージョンの boot を差し替える場合も、
新しいタグ（例: `wpa3.sae=2`）をイメージに設定し、新しい `release_tag` と対応する pin を用意してください。
同じタグのままでは、既にタグ付きカーネルで動く端末は再フラッシュしません。

公開処理は upstream `nightly-chestnut` が親を持たない orphan コミットであることを前提とし、
この条件が変わった場合は公開を保留して issue を作成・更新します。
comma 3X は同じカーネル／ファームウェア系統ですが未検証です。実機確認済みなのは comma four のみです。

GitHub はリポジトリに 60 日間活動がない場合、schedule workflow を無効化することがあります。
nightly が止まったら Actions 画面で状態を確認し、必要に応じて再有効化してください。

公開前に以下を確認します。

- G1: upstream の AGNOS_VERSION に対応する pin がある。
- G2: stock boot/system の raw ハッシュが pin の `derived_from` と一致する。
- G3: AGNOS 更新コードの blob が一致し、ランチャーパッチが適用できる。
- G4: boot URL をリダイレクト込みで取得し、xz 展開後の SHA-256 とサイズが一致する。
- G5: UI パッチが適用できる、または既に適用済みである。

AGNOS のバージョン更新などでゲート／合成が失敗すると公開を止め、`nightly-hold` ラベルの issue を 1 件作成・更新します。
現在の配布ブランチはそのまま残ります。新しい AGNOS 用にカーネルを用意・検証し、対応する pin と必要なパッチ更新を入れるまで保留します。
成功時に hold issue をコメント付きで閉じます。インストーラーの HTTP/ELF チェックだけが失敗した場合は
`nightly-smoke` issue と warning に留め、公開済みブランチを自動では戻しません。

## ロールバック・公式版へ戻す

Actions の **Roll back WPA3 nightly** を実行すると、`nightly-chestnut-lastgood` を
lease 付きで `nightly-chestnut` に戻し、その後 `nightly.yml` を無効化します。
lastgood は直前の配布コミットです。最初の公開直後などで存在しなければ、ロールバックは何も変更せず失敗します。
原因を修正して再開するときは `gh workflow enable nightly.yml --repo shunnag/openpilot` または Actions の画面で再有効化します。

公式版へ戻すには nightly の自動公開を止め、端末を comma 公式の配布先・インストール手順へ戻してください。
**ブランチを戻すだけでは、AGNOS 19.8 の WPA3 カーネルは消えません。**
公式側も AGNOS_VERSION が同じなら再フラッシュしないため、通常は comma の次回 AGNOS バージョン更新まで残ります。
すぐに stock カーネルへ戻す必要がある場合は、公式の OS 復旧・再インストール手順が必要です。
ブランチのロールバックと OS の復旧は別の操作です。

## ローカル検証

Python 3 標準ライブラリ、git、bash を使います。配布 tree は bare repo と一時 `GIT_INDEX_FILE` だけで合成します。
構文検査用の数個の blob 以外は展開せず、モデルを含む LFS pointer はそのまま保持します。
workflow 全体で `GIT_LFS_SKIP_SMUDGE=1` / `GIT_LFS_SKIP_PUSH=1` を設定し、LFS の取得・push は行いません。
`.github/workflows` は配布 tree から除去します。それ以外は指定した 7 ファイル以外を変えないことを合成後に検証します。

テストには gitignored の `ref/nightly-chestnut/` にある参照ファイルが必要です（参照元 SHA は `UPSTREAM_SHA`）。
参照ファイル自体は変更せず、`.tmp/` に小さな synthetic bare repo を作って検証します。

```sh
export GIT_LFS_SKIP_SMUDGE=1 GIT_LFS_SKIP_PUSH=1
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/gates.py --repo /path/to/upstream.git --upstream <U> --skip-download
python3 scripts/compose.py --repo /path/to/upstream.git --upstream <U>
```

`--skip-download` はオフラインテスト専用です。公開 workflow は必ず G4 を実行します。
compose の標準出力は 1 行目が生成コミット SHA、2 行目が `WPA3-Inputs` です。
入力 ID は U、両パッチの SHA-256、選択された pin、compose.py の SHA-256 を含む canonical JSON
（キーを sort、区切りは `,` と `:`）の SHA-256 です。
Git の author/committer は固定し、両日時は U の committer 日時を使います。
