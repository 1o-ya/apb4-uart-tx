# 意図的な故障でテストの検出力を確認する

これは制御RTLに12種類の単一故障を入れる固定実験です。未変更RTLが同じ8試験に合格した後でのみ実施します。
各故障は文字列アンカーが原本に1個だけあることを確認して適用し、原本と生成RTLのSHA-256を保存します。
候補生成の失敗、自然に発見された不具合、全バグの検出率とは区別します。

実行：依存を用意して、未使用の出力先を指定します。

```sh
.venv/bin/python scripts/mutation_check.py --out reports/runs/manual-mutations-001
```

未変更RTLが合格し、12故障すべてを対象の名前付き試験の`AssertionError`で検出した場合のみ、終了コード0です。
結果は`summary.json`、各ディレクトリには生成RTL、事前コンパイル結果、シミュレーションログ、xUnit結果を残します。
全ミュータントで共通の8試験を実行します。通常は1 MHz/100000 baud、丸め故障のみ1 MHz/400000 baudです。

故障と対応する観測：

- `baud_early`：bit長がD−1。bit全期間の参照列との照合。
- `rounding_floor`：最近接丸めを切捨てへ変更。D=3でbit長を照合。
- `start_high`：STARTが1。フレーム先頭の0を照合。
- `first_bit_msb`：最初のデータbitをMSBから出力。全256値のbit順序を照合。
- `stop_low`：STOPが0。STOP全期間を照合。
- `ignore_low_strobe`：`PSTRB[0]=0`でも受理。無操作書込みの参照応答・送信を照合。
- `no_busy_backpressure`：BUSY時も書込みを完了。待機数と参照APB応答を照合。
- `high_address_alias`：上位アドレスを無視。全32-bitアドレスによる不正アクセス判定を照合。
- `suppress_access_error`：未知アドレスのエラーを消去。不正アクセスの応答を照合。
- `setup_response_enabled`：`PENABLE=0`で応答。未受理状態のAPB応答を照合。
- `busy_ends_before_stop`：STOP期間中にBUSYが0。BUSY全期間とAPB待機を照合。
- `reset_tx_low`：リセット時のtxが0。非同期リセット出力を照合。

コンパイル拒否、タイムアウト、XML欠落・破損、試験欠落・skip、想定外の実行時エラーは、故障検出の成功として数えません。
同じソースとテストの1点故障を選んだ検査であり、現実の全バグ、複合故障、FPGA／ASIC実装後の品質を保証しません。
