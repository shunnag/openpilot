# modem.py の 2 つの修正：手元の openpilot に取り込むためのまとめ

対象：openpilot のフォークや手元のブランチを持っているコントリビューター
元のブランチ：[shunnag/openpilot `modem-auth-test`](https://github.com/shunnag/openpilot/tree/modem-auth-test)（upstream master `6f4c0faf1` の上に 3 コミット）

| コミット | 内容 | 実機での確認 |
|---|---|---|
| `08f582ea212fd52cbeda7131c8cceebb4b09d91f` | **A. 登録を拒否されているときにも APN の変更を反映する**（[commaai/openpilot#39061](https://github.com/commaai/openpilot/pull/39061) と同じ） | comma four（EG916Q-GL）と SoftBank の SIM で確認済み |
| `81ed502e15b5bea22fb5a49eb8b6f96c6e629375` | **B. APN の認証（CHAP/PAP）を設定できるようにする** | **未確認**（試験版。テスターが試験中） |
| `19a18a8b9164ab18788f6af3f3e4f0c0c14d815a` | C. テスター用の道具（`tools/modem_auth/`） | 手元の試験のみ。取り込みは任意 |

B は A の上に作ってあります。B だけを取り込むことはできません。

---

## 1. 取り込み方

```bash
cd /path/to/your/openpilot
git fetch https://github.com/shunnag/openpilot modem-auth-test
git cherry-pick 08f582ea212fd52cbeda7131c8cceebb4b09d91f    # A だけならここまで
git cherry-pick 81ed502e15b5bea22fb5a49eb8b6f96c6e629375    # B
git cherry-pick 19a18a8b9164ab18788f6af3f3e4f0c0c14d815a    # C（任意）
```

パッチのファイルが欲しいときは、GitHub のコミットの URL の末尾に `.patch` を付けると取れます（例：`https://github.com/shunnag/openpilot/commit/08f582ea2.patch`）。

### 当たる場所と、衝突しやすいところ
- 対象のファイルは `openpilot/common/hardware/comma/modem.py` と `openpilot/common/params_keys.h` です。
- modem.py は、upstream の master、nightly、release-tizi-staging で同じ中身です（2026-10-11 時点）。A と B は、それらの上にそのまま当たるはずです。
- params_keys.h は、`GsmApn` の近くの行が違うブランチでは衝突することがあります。3 行を、アルファベット順の位置に足すだけです（§3）。
- **古いブランチ（0.11.1 の release-tizi／release-mici など）は、ファイルの場所が違います**（`system/hardware/tici/modem.py`）。そのままでは当たりません。パッチのパスを書き換えれば当たる可能性はありますが、中身が同じかは確かめていません。
- **B は params_keys.h を変えるので、ビルドが要ります。** prebuilt のブランチ（`prebuilt` ファイルがあるもの）に取り込むときは、自分の CI などでビルドし直してください。端末の上でビルドするブランチなら、起動時にビルドされます。

---

## 2. A：登録を拒否されているときにも APN の変更を反映する（実機で確認済み）

### 直した不具合
APN を明示しないとつながらない SIM は、CID 1 の APN が空のあいだ登録を拒否されます（CREG/CGREG が 3、`AT+CEER` が ESM cause 32）。このとき：
- **P1**：設定で APN（`GsmApn`）を入れても、モデムに書かれない。`_params_changed()` を見ているのが `_do_connected()` だけで、`_do_searching()` が見ていないため。
- **P2**：再起動すると CID 1 には新しい APN が入るが、モデムは電源が入った直後に古い APN で登録しに行っていて、自分でやり直すまで約 12 分（実測 740 秒前後）拒否されたまま。

### 変更点（modem.py に 39 行を足す。消す行はなし）
- `_do_searching()` でも `_params_changed()` を見る。
- `_do_initializing()` で、書く前に CID 1 の APN を読む（`AT+CGDCONT?`）。違う APN が入っていたら、つなぎ直しの回数 `_reattach_tries = 2` を用意する。
- 拒否（`denied`）のときだけ `_reattach()`：`AT+COPS=2`（登録を外す）→ 読み返し → `AT+CGDCONT` を書き直す → `AT+COPS=0`（自動で登録）→ 読み返し。電波と SIM は切らない。
- 途中で止まって `AT+COPS=2` のまま残ったときのために、INITIALIZING で COPS のモードが 2 なら `AT+COPS=0` を送る。
- 登録できているモデムには何もしない。ふつうの起動で増えるのは読み取り 2 つ（`AT+CGDCONT?`、`AT+COPS?`）だけ。

### 実機の結果（comma four、EG916QGLLGR01A05M04、AGNOS 19.9、SoftBank のデータ SIM）
- 拒否のあいだに APN を入れた：変更から 7 秒で CONNECTED（master は 7 回中 7 回、書かれないまま）。
- 古い APN を覚えたまま再起動：起動から 23〜24 秒で CONNECTED（master は約 740 秒）。
- ふつうの起動：21〜22 秒で CONNECTED（master は 20〜22 秒）。
- 間違った APN：つなぎ直しは 1 回だけで、そのあとくり返さない。

---

## 3. B：APN の認証（CHAP/PAP）を設定できるようにする（未確認の試験版）

modem.py に 182 行を足して 11 行を消し、params_keys.h に 3 行を足します。認証を設定しない人の動きは、今と変わりません。

### 新しい設定（params_keys.h に 3 行）
```cpp
{"GsmAuth", {PERSISTENT, STRING}},
{"GsmPassword", {PERSISTENT | DONT_LOG, STRING}},
{"GsmUsername", {PERSISTENT | DONT_LOG, STRING}},
```

| GsmAuth | 動き |
|---|---|
| 空（既定） | **何もしない。** 認証の AT コマンドを一切送らず、pppd の起動の仕方も今と同じ。ユーザー名やパスワードだけが入っていても使わない（警告を 1 回出す） |
| `chap` / `pap` | ユーザー名とパスワードを CID 1 の認証として書き、pppd にも同じ値を渡す |
| `none` | モデムの CID 1 の認証を消す（`AT+CGAUTH=1,0` など） |

ユーザー名とパスワードは、64 バイト以内、ASCII の `!`〜`~`、ただし `"`、`\`、`,` を除く文字だけを受け付けます。外れたら認証を使わず、値を出さない警告を出します。

### modem 側（AT コマンド）
- **コマンドの選び方**：`modem_version` が `EG25` で始まる（comma 3X）なら `AT+QICSGP`、それ以外（comma four の EG916Q-GL）は `AT+CGAUTH`。それぞれ `=?` で使えることを確かめ、だめならもう一方を試す。どちらも返事がない（ロックが取れない場合を含む）ときは INITIALIZING をやり直し、3 回でモデム側をあきらめる（pppd には値を渡す）。
- **書く順番**：`AT+CGDCONT=1,"IP","<APN>"` のあとに認証を書く。A の `_reattach()` の中（COPS=2 と COPS=0 のあいだ）でも同じく書く。
  - CGAUTH：`AT+CGAUTH=1,<1|2>,"<user>","<pass>"`、消すときは `AT+CGAUTH=1,0`
  - QICSGP：`AT+QICSGP=1,1,"<APN>","<user>","<pass>",<0|1|2>`
- **読み返しと、つなぎ直しの準備**：書く前に CID 1 の認証を読み（`AT+CGAUTH?` の `+CGAUTH: 1,` の行、または `AT+QICSGP=1`）、方式とユーザー名が違えばつなぎ直しを用意する。パスワードは、モデムが読み返しで見せたときだけ比べる。設定が変わったとき（`_params_changed()` が気づいたとき）も用意する。
- **「検索中」でのつなぎ直し**：認証の失敗は、拒否（CREG 3）ではなく検索中（CREG 2）に見えることがある（EC25-J と KDDI の報告で `+CREG: 0,2` と `+CEER: 5,29`）。そのため、**認証で用意したときだけ**、検索中か未登録が 60 秒続いたらつなぎ直す。回数は A と同じく INITIALIZING ごとに多くて 2 回。A の「拒否のときだけ」の動きは変えていない。
- **診断のログ**：書いたあとの読み返しを、真偽だけでログに出す（`APN auth via CGAUTH: protocol=chap, readback protocol ok=True, user ok=True, password ok=True|not shown`）。登録が denied／searching／not_registered に変わったときに `AT+CEER` を 1 回ログに出す（「古い値のことがある」と添えて）。

### pppd 側
- 認証を使わないとき（GsmAuth が空、または `none`）：`PPPD_CMD` は 1 バイトも変えない（今の `user '""' password '""'` のまま）。
- `chap`／`pap` のとき：その 4 つの引数を `file <path>` に置き換える。ファイルは `tempfile.mkstemp(dir="/dev/shm", prefix="modem_pppd_auth_")`（0600、持ち主 comma、sudo の pppd が root で読む）で、中身は `user "<u>"` と `password "<p>"` の 2 行。`refuse-*` は付けない（方式はモデムに任せる。一部だけ拒むと NAK の繰り返しになるため）。
- ファイルは pppd を起動するたびに作り直し、`kill()`、`stop()`、`run()` の開始時（前回の残り）に消す。作れなかったときは今の引数に戻す（パスワードを引数に回さない）。

### パスワードを漏らさないための決まり（取り込むときに崩さないでください）
- **params に登録してから使う。** 登録していない設定は、マネージャーの起動のたびに bootlog に値ごと記録されてから消されます（`Params::clearAll` と `logger_build_init_data`）。`DONT_LOG` が付いていれば値は記録されません。
- **pppd の引数にパスワードを入れない。** AGNOS の sudo は、許したコマンドの引数を `COMMAND=` としてジャーナルに残し、openpilot はジャーナルを bootlog と rlog に入れます。
- `_at()` の失敗のログは、認証の書き込みのときは `AT+CGAUTH=1,<redacted>` のように伏せた表示にする。`AT+CGAUTH?` と `AT+QICSGP=1` の返事（パスワードを含むことがある）はログに出さない。
- `/dev/shm/modem`（athena から読める状態）にも入れない。

### 確かめていないこと
- 認証が要る SIM での動き（そもそもの目的）。comma 3X での `AT+QICSGP` の動き。
- モデムが `AT+CGAUTH?` でパスワードを読み返すか。`@` などの文字がモデムの中で変わらないか。
- 認証の設定が再起動で残るか。`AT+CGDCONT` を書き直すと消えるか（どちらでも動くよう、毎回書き直す作りにしてある）。

---

## 4. C：テスター用の道具（`tools/modem_auth/`、任意）
| ファイル | 役目 |
|---|---|
| `set_apn_auth.sh` | ユーザー comma のまま、Params の API で 3 つの設定を書く／消す。パスワードは画面に出さず、引数にも入れない。書くときも消すときも GsmAuth を最後にする |
| `modem_at_read.py` | modem.py と同じロック（`/dev/shm/modem.lock`）を取る、読み取り専用の AT の問い合わせ。IMEI、ICCID、位置の番号、認証の値を伏せる |
| `collect_modem_logs.sh` | modem.py と pppd のログ、モデムの状態をまとめ、伏せて tar.gz にする |

---

## 5. 試験
- upstream は modem.py の試験を持っていません（#38213 で提案された試験は、マージの前にメンテナーが外しました）。そのため、ブランチにも試験は入れていません。
- 手元では、モデムを模した試験 137 件（A と B の場面：拒否、検索中の継続、ロックが取れない、パスワードを見せないモデム、EG25 の QICSGP、設定を消す順番、ログにパスワードが出ないこと など）で確かめています。欲しい方には渡せます。
