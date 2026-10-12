# APN authentication diagnostics

Set credentials in Settings → Network on the APN auth test build. These tools
are read-only diagnostics for advanced testers running over SSH as `comma`.

```bash
./modem_at_read.py --preset probe --secrets-from-store
./modem_at_read.py --summary
./collect_modem_logs.sh
```

Settings are stored privately in `/data/apn_auth/settings.json`. Empty auth is
unmanaged; `chap` and `pap` opt in; `none` actively clears modem auth. The UI's off
and delete actions retain `none` in the store. Before changing SIMs or leaving
the test branch, turn auth off and delete the saved credentials in the UI, then
wait for the modem to reconnect. Deleting the file alone does not clear modem auth.

The AT reader uses the same exclusive lock as modem.py and releases it after
each command. It waits up to 10 seconds for the lock; queries have a 5 second
deadline, or 10 seconds for the MBN list. Examples:

```bash
./modem_at_read.py 'AT+CGAUTH?' 'AT+QICSGP=1' --secrets-from-store
./modem_at_read.py --preset eg25 --json --secrets-from-store
./modem_at_read.py --redact-stdin --secrets-from-store < captured_log.txt
```

Identity commands, writes, chained commands and unsupported syntax are refused.
Auth fields are redacted even when the credentials are absent from the store.
With `--secrets-from-store`, literal username/password occurrences of at least
three characters are also masked. Identity numbers, IPv4 addresses, registration
locations, modem identity log values and modem JSON identity fields are masked.
Device hostnames and serving-cell identities are also masked. LTE cellID, PCID
and TAC are removed while radio metrics stay; other RATs or unexpected layouts
are redacted after the RAT.
Other hex/decimal runs of at least 16 characters keep only their first four
characters plus `<id>`. Existing IMEI/ICCID masks and redaction placeholders stay.
Modem `ERROR` replies, query failures and timeouts produce a nonzero exit status;
the remaining queries still run. JSON output is an array of `command`/`lines`
objects with the same redaction.

Developers checking known dummy credentials may use `--show-auth-values` to
disable only CGAUTH/QICSGP user/password field masking. It warns on stderr,
refuses `--secrets-from-store`, and refuses a non-empty stored password. If the
store cannot be checked, it also refuses. All other
redaction stays active, including identity numbers, IPv4 and registration
locations. This flag also applies to `--json` and `--redact-stdin`. The collector
never uses it.

The collector creates a private `~/modem_logs_<UTC timestamp>/` directory and
matching `.tar.gz`. Every captured stream, including stderr, passes through the
redactor before being saved. The tmux pane is captured with `TERM=xterm` and
streamed through a filter keeping only lines containing ` modem: `, then through
redaction into `tmux_modem.txt`. The full pane is never written to disk, and the
bundle contains no `tmux_full.txt`. It collects pppd/chat and ModemManager journals;
it never requests the sudo journal. Check every file before sharing the bundle.
Missing diagnostics are recorded; a redaction failure stops collection.

`OPENPILOT_DIR` defaults to `/data/openpilot`. The AT reader accepts `--port`,
`--lock`, `--lock-timeout` and `--store-dir`. The collector accepts the test
overrides `MODEM_AT_PORT`, `MODEM_AT_LOCK` and `APN_AUTH_STORE_DIR`.

Offline tests use pytest; the tools themselves require only bash and Python's
standard library. The collector saves credential lengths/presence only, never
the credential store itself.

```bash
python3 -m pytest -p no:cacheprovider -q openpilot/common/hardware/comma/tests/test_modem.py
bash -n tools/modem_auth/collect_modem_logs.sh
ruff check tools/modem_auth/modem_at_read.py
```
