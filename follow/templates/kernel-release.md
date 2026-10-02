$marker

Automatically built kernel; published WITHOUT any device test unless Device-tested below explicitly records one.
自動ビルドのカーネルです。下の Device-tested に実機確認の記録がある場合を除き、実機テストなしで公開します。

$identity

Device-tested: $device_tested
Last device-tested baseline: $baseline_tested
wpa_supplicant: $wpa_status

$checks

$toolchain

$assets

$risks

No WPA3 kernel has ever booted on a comma 3X unless an explicit comma 3X test is recorded above. Recovery may need a computer and https://flash.comma.ai. Do not report problems to comma.
上に comma 3X での実機確認が明記されていない限り、comma 3X では WPA3 カーネルを一度も起動していません。復旧にはパソコンと https://flash.comma.ai が必要になることがあります。問題を comma に報告しないでください。

Withdraw with follow-admin revoke. The boot signature checks integrity, not builder identity.
取り下げには follow-admin revoke を使います。boot の署名はファイルの整合性を確認するもので、ビルドした人を証明しません。
