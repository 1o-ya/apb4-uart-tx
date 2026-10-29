# Seed付きAPB/UARTストレス試験

`test_uart_stress` は1件のCocotb試験。`uart_stress_model` を同じPython検索パスに置く。
実行条件は `CLK_FREQ_HZ`、`BAUD_RATE`、`UART_TEST_SEED`。既定seedは20261028。
これはテスト刺激を再現するseedで、モデル生成のseedではない。

既存試験の「受理したbyteから期待bit列を作り全クロック照合する参照」とは別に、
TX端子の1→0をSTARTとして検出し、各bitの中央クロックで10bitを読み、START/STOPを検査してbyteへ復号する。
APBで実際に成立した有効DATA書込みをキューに積み、その復号結果と順番・値を照合する。
内部FSM、分周カウンタ、シフトレジスタは一切参照しない。
busのBUSY期待値は、受理時刻から仕様の10Dクロックを数えて独立に求める。
復号器自体も、D=1/3/10それぞれ全256byteの合成波形で自己試験し、不正STOP・誤byte・無要求フレームを拒否する。
この自己試験はPython参照器の確認であり、768件のRTL試験としては数えない。

必須の前置試験では全16ストローブ・全8保護属性、7種類の不正アクセスをidle中と送信中に実行する。
全8種の `PSTRB[0]=0` を送信中にも実行し、待たず・余分な送信をしないことを調べる。
連続DATA書込みはSTOPが終わるまで待機し、ACCESS中のaddress/data/controlを保持する。
読取り時のPSTRBは0。通常SETUPは1クロック。待機を中断するのはreset時だけ。

START/DATA/STOPそれぞれのseedで選んだ位置と、APB待機中で非同期resetをアサートし、進行フレームを破棄して復帰後に再送する。
続いて128回の制約付きランダム操作（有効書込み、不正アクセス、STATUS読取り、無操作、idle gap）を実行する。
全送信をdrainしてから、受理数＝復号完了数＋reset中断数、余計なSTARTがないことを確認する。

合格時のみ `stress_coverage.json` を保存し、必須シナリオの集合とフレーム数・待機数などを記録する。
これは**シナリオcoverage**であり、RTL line/branch/toggle coverageでも全入力の網羅でもない。
中央サンプルの復号だけではbit内の短いglitchを全て検出できないため、既存の全クロック参照試験を併用する。

推奨する固定実行組合せは、2つのRTL候補×Icarus/Verilator×D=1/3/10×seed=1/20261028。
D=3は1MHz/400000 baudの丸め上げを含む。stressではD=434を重ねず、既存のRTL既定値試験に任せる。
PC上のsimulation検証であり、FPGA実機・アナログ信号品質・実クロック誤差の証明にはならない。
