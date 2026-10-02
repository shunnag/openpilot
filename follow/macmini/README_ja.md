# Mac mini の WPA3 hwsim テストランナー

Mac mini から公開 HTTPS をポーリングする専用ランナーです。GitHub Actions の
self-hosted runner には登録しません。MacBook、ローカルの `/Volumes/agnos`、
研究用ディレクトリには依存しません。macOS 側の sudo は使いません。

## ユーザーが行う初期設定

1. GitHub に公開リポジトリ `shunnag/wpa3-test-results` を作り、README を追加して
   `main` ブランチを作成してください。Fine-grained personal access token を作成し、
   **Only select repositories: `shunnag/wpa3-test-results` のみ**、
   **Contents: Read and write** を許可します。`shunnag/openpilot` は選びません。
   Actions / Issues 権限も不要です。有効期限を設定し、失効前に更新してください。
2. Mac mini の「キーチェーンアクセス」で **ログイン** キーチェーンに新しい
   パスワード項目を作成します。「キーチェーン項目名」（サービス名）を
   `wpa3-test-results`、アカウント名を自分のユーザー名、パスワードを上記トークンに
   します。初回の push で `/usr/bin/security` のアクセス許可を求められたら、
   このランナー用として許可してください。トークンを plist、シェル履歴、環境変数、
   git remote、リポジトリに書かないでください。
   読み出しは Git の askpass 内部で
   `security find-generic-password -s wpa3-test-results -w` を使います。
   このコマンドをターミナルで直接実行するとトークンが表示されるため、実行不要です。
3. 必要なツールを用意します。

   ```bash
   brew install colima python@3.12 zstd
   git clone --branch wpa3-ci --single-branch https://github.com/shunnag/openpilot.git "$HOME/wpa3-hwsim-code"
   cd "$HOME/wpa3-hwsim-code"
   ```

   レビュー済みの **Part 3 を含む完全な 40 桁のコミット**に checkout してください。
   この実装は自動でコミットを作りません。Part 2 の `2b22eb529` にはテストコードが
   ないため、そのコミットをピンにするとエラーになります。コードの更新は人が
   レビューして checkout し、plist のコミットを差し替えます。要求からの自動更新はありません。

4. 既に確認済みの `wpa3hwsim` プロファイルを使用します（colima 0.10.3、vz、
   aarch64、containerd、Ubuntu 24.04、kernel 6.8.0-117）。通常の colima プロファイルとは
   分けてください。VM はテストごとに起動・停止されます。`--mount=none`、SSH agent
   転送無効、port forwarding 無効で起動し、ホストのホームやトークンを VM に渡しません。
   ファイルは標準入力で転送します。VM 内のみ sudo を使い、modules-extra、iw、
   hostapd、wpasupplicant、python3、iproute2 を必要に応じて apt で導入します。
   candidate は独立した実行ファイルとして配置し、要求の `.deb` のスクリプトは実行しません。

## オーケストレーターが Mac mini 上で行う self-test

レビュー済みコミットを配置した後、Mac mini のターミナルで以下を実行します。
トークンも結果リポジトリも、この self-test には不要です。

```bash
cd "$HOME/wpa3-hwsim-code"
WPA3_SUITE_COMMIT=$(git rev-parse HEAD)
git cat-file -e "$WPA3_SUITE_COMMIT:userspace/wpa-build/hwsim/suite.py"
git cat-file -e "$WPA3_SUITE_COMMIT:follow/macmini/vm_run.sh"
bash follow/macmini/wpa3_hwsim_poll.sh \
  --self-test --dry-run --suite-repo "$PWD" --suite-commit "$WPA3_SUITE_COMMIT"
```

公開済み `agnos-19.8-wpa3.2` の `.deb`（`6c25f125…`）と展開した binary
（`139be31d…`）、Ubuntu の stock `.deb`（`dbb661fe…`）と binary（`b0f1c8ee…`）を
固定 SHA256 で検証します。16 ケースすべて PASS で終了コード 0。
結果 JSON と伏字済みログは
`~/Library/Application Support/wpa3-hwsim/self-tests/` に保存します。
失敗時も VM を停止します。self-test は常にローカルのみで push しません。

## launchd の登録

```bash
cd "$HOME/wpa3-hwsim-code"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs/wpa3-hwsim"
python3 - <<'PY'
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape
repo = Path.cwd()
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
text = (repo / 'follow/macmini/com.shunnag.wpa3-hwsim.plist.in').read_text()
for key, value in {'REPO': str(repo), 'HOME': str(Path.home()), 'COMMIT': commit}.items():
  text = text.replace('@@' + key + '@@', escape(value))
path = Path.home() / 'Library/LaunchAgents/com.shunnag.wpa3-hwsim.plist'
path.write_text(text)
print(path)
PY
plutil -lint "$HOME/Library/LaunchAgents/com.shunnag.wpa3-hwsim.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.shunnag.wpa3-hwsim.plist"
```

ログイン中に 30 分ごとに実行され、ログは `~/Library/Logs/wpa3-hwsim/` に出ます。
ログアウト中・スリープ中は動かないので、常時稼働用のユーザーセッションを維持してください。
停止は `launchctl bootout "gui/$(id -u)/com.shunnag.wpa3-hwsim"`。
手動で確認する場合は以下を使います。

```bash
bash follow/macmini/wpa3_hwsim_poll.sh --dry-run --suite-commit "$(git rev-parse HEAD)"
```

`--dry-run` はテストとローカル結果作成まで行い、commit/push は行いません。
結果は `~/wpa3-test-results/results/<request-id>.json` と `.log` に残ります。
次回の通常実行前に、その未コミット結果をレビューして退避してください。
通常実行は結果リポジトリだけに commit/push します。push 競合・期限切れトークンは
終了コード 1 で停止し、ローカルの結果・コミットを保持します。強制 push はしません。
失敗した push の復旧後にローカルと origin/main を同期してください。
異常終了で `poll.lock` が残った場合はプロセスが動いていないことを確認してから削除します。

## 要求と結果の取り決め

- 公開済みの release/prerelease のタグ `wpa-test-wpa3-<run-id>-<binary-sha先頭12桁>` を
  匿名の Releases API で列挙します。draft と Actions artifacts は匿名取得できないため
  対象外です。**Part 3 の follow.yml は artifacts を作るだけ**なので通常は未処理要求 0 件。
  release への発行は Part 4a の仕事です。
- release 内の `test-request.json` に ID、作成日時、期限（最大 7 日）、suite commit、
  6 個の asset の URL・サイズ・SHA256 を記録します。同一 release 内の
  `candidate`、`candidate.deb`、`candidate.copyright`、`stock`、`stock.copyright`、
  `test-suite.tar.gz` だけを許可し、全件の hash を検証します。
- 未知のフィールド、コマンド、別 repo の URL、期限切れ、ローカル pin と異なる suite
  commit を拒否します。`test-suite.tar.gz` は証跡として hash を確認するだけで、展開も
  実行もしません。`suite.py` と `vm_run.sh` はローカルの pin から `git show` で読みます。
- 公開ログは固定のケース名と PASS/FAIL のみ。生の daemon ログ、apt 出力、ホスト名、
  実 SSID、トークンは送信しません。VM の一時ログは実行終了時に破棄されます。
- JSON は候補 asset 全件の hash、suite commit、テストごとの結果、colima/kernel
  version、実行日時、ログ hash を含みます。既存結果は再実行せず、要求の新しい ID を待ちます。
- `follow.yml` の publish は匿名 raw URL で JSON とログを読み、要求との一致を確認します。
  dryrun で result ID がなければ `T3: PENDING (dryrun)`。過去の公開要求を指定した場合も、
  この run で再ビルドした asset 全件の hash・サイズと suite commit の一致が必須です。
  期限は元の要求と照合します。不一致なら HOLD。要求の公開・自動再開・期限超過 issue は
  Part 4a で配線します。

T3 は mac80211 の supplicant SME を確認します。qcacld の external auth、NetworkManager、
実機での認証は対象外です。R0、T1/T2、T3 の実行成功は別々に確認する必要があります。

参照: [Colima 0.10.3 の mount/SSH flags](https://github.com/abiosoft/colima/blob/v0.10.3/cmd/start.go)、
[Ubuntu Snapshot](https://snapshot.ubuntu.com/)。
