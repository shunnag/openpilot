$marker

Automatically built wpa_supplicant; published WITHOUT any device test. CI tests do not test a physical device.
自動ビルドの wpa_supplicant は、実機テストなしで公開します。CI のテストは実機テストではありません。

$identity

Device-tested: $device_tested
Last device-tested baseline: $baseline_tested
wpa_supplicant: $wpa_status

$checks

$toolchain

$assets

$risks

$requirements

An auto-built wpa_supplicant is used only if the stock binary matches; on failure the device keeps stock. Recovery may need https://flash.comma.ai. Do not report problems to comma.
自動ビルドの wpa_supplicant は純正バイナリが一致する場合だけ使い、失敗した端末では純正を使います。復旧には https://flash.comma.ai が必要になることがあります。問題を comma に報告しないでください。
