# 出典・採用した慣習

確認日: 2026-10-28（JST）。以下は実際に参照した一次資料。Context7 はこのセッションの利用可能ツールに存在しなかったため、公式資料を直接確認した。

## インターフェースと検証

- [Arm AMBA APB Protocol Specification IHI 0024C、APB v2.0](https://documentation-service.arm.com/static/64257f64314e245d086bc8b7?token=): §3.1 の待機時信号保持、§3.2 の byte strobe と read 時の全 `PSTRB=0`、§3.4 の完了時 `PSLVERR` を仕様確認に使用。エラー時に状態を変更しないことは本IPの仕様であり、APB一般の保証ではない。PDF・図・本文は同梱していない。
- [cocotb 2.0 Makefile flow](https://docs.cocotb.org/en/v2.0.0/building.html): simulator選択、ソース指定、xUnit結果ファイル、毎回実行する `sim` の扱いを確認。実行依存の固定版は 2.0.1。
- [cocotb 2.0 timing model](https://docs.cocotb.org/en/v2.0.0/timing_model.html): clock edge直後とRTL更新後の観測を区別。`ReadOnly` 後の同一時刻では書き込まない。

## リポジトリの実例

- [alexforencich/verilog-uart README](https://github.com/alexforencich/verilog-uart): `rtl/` と `tb/` を分離し、接続条件と試験方法を説明している。[tox設定](https://raw.githubusercontent.com/alexforencich/verilog-uart/master/tox.ini) は依存版を固定し、[回帰CI](https://raw.githubusercontent.com/alexforencich/verilog-uart/master/.github/workflows/regression-tests.yml) は push/PR を契機に Icarus と tox で実行する。READMEに後継 taxi への移行と保守終了の記載あり。慣習と代替手段の参照であり、RTL・テストのコード流用はない。
- [cocotb/cocotb](https://github.com/cocotb/cocotb): READMEから導入資料・例・issueへ接続し、[CONTRIBUTING](https://github.com/cocotb/cocotb/blob/master/CONTRIBUTING.md) から開発ガイドへ案内する。[リリースページ](https://github.com/cocotb/cocotb/releases) でタグ・リリースノート・PyPI版を対応づけている。

今回採用する範囲は、RTL/テストの分離、Python依存の版固定、短い仕様と再実行コマンド、xUnit結果・波形の保存、同じローカルコマンドを呼ぶCI定義。GitHub上のCI実行は未実施で、定義の準備をCI合格とは記録しない。リリース運用や大きな共通テンプレートは導入していない。

## ライセンス・帰属の確認範囲

- この作業で再利用したユーザーの既存UART RTL・テストには、取り込み元直下の `LICENSE` / `COPYING` が見つからなかった。ローカル成果物の公開ライセンスは `unknown`。由来と原本SHA-256は [PROVENANCE.md](PROVENANCE.md) に記録。
- cocotb 2.0.1: [BSD-3-Clauseの原文](https://raw.githubusercontent.com/cocotb/cocotb/v2.0.1/LICENSE)。cocotb contributors、Potential Ventures Ltd、SolarFlare Communications Inc の表示あり。実行依存で、ソースや配布バイナリは成果物に同梱しない。
- find_libpython 0.5.1: [版固定PyPI](https://pypi.org/project/find-libpython/0.5.1/) と [v0.5.1 LICENSE](https://raw.githubusercontent.com/ktbarrett/find_libpython/v0.5.1/LICENSE) で MIT を確認。Takafumi Arakaki、Kaleb Barrett の表示あり。実行依存として導入し、配布物を同梱しない。
- Icarus Verilog 13.0: [v13_0 main.ccの許諾表示](https://raw.githubusercontent.com/steveicarus/iverilog/v13_0/main.cc) で GPL-2.0-or-later を確認。外部実行ツールとして使用し、ツール本体を同梱しない。
- Yosys: [公式COPYING](https://raw.githubusercontent.com/YosysHQ/yosys/main/COPYING) で ISC を確認。Claire Xenia Wolf の表示あり。外部合成ツールとして使用し、ツール本体・バンドル依存を同梱しない。
- 参照した verilog-uart は [MIT COPYING](https://github.com/alexforencich/verilog-uart/blob/master/COPYING)。コードを取り込んでいないため、本成果物のUARTを同ライセンス由来とは扱わない。Arm仕様書は独自ライセンスであり、本成果物のライセンスではない。

この一覧は今回使用・参照した範囲の記録で、公開ライセンスの決定や全ツールバンドルの配布監査を意味しない。

## 検証強化で参照した一次資料

- [Cocotb 2.0.1 simulator support](https://docs.cocotb.org/en/v2.0.1/simulator_support.html)：Icarus／Verilatorの互換条件。
- [Cocotb Python runner](https://docs.cocotb.org/en/v2.0.1/runner.html)：シミュレータ別のbuild/run、波形生成。
- [Verilatorのコマンド資料](https://verilator.org/guide/latest/exe_verilator.html)：lint、coverage、パラメータ指定。
- [Yosys SAT](https://yosyshq.readthedocs.io/projects/yosys/en/v0.51/cmd/sat.html)と
  [async2sync](https://yosyshq.readthedocs.io/projects/yosys/en/v0.54/cmd/async2sync.html)：有界SATとreset変換。
  実際に使った版の`yosys -p 'help sat'`も確認した。仮定と深さは[形式検証仕様](../formal/README.md)。
- [Microsoft VS Code Tasks](https://code.visualstudio.com/docs/debugtest/tasks)と
  [Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers)：同じコマンドをエディタ・Linux環境から実行する設定。
- [Surfer公式VS Code拡張](https://marketplace.visualstudio.com/items?itemName=surfer-project.surfer)：VCDをVS Code内で開く手順。
  拡張の推薦設定と手順を同梱し、拡張自体は配布物に同梱しない。
- [Verilator v5.036の公式タグ](https://github.com/verilator/verilator/releases/tag/v5.036)：コンテナのソース版を固定。
  Dockerのベースdigest、ソースarchive SHA256、apt／Pythonの実際の版は[環境の記録](CONTAINER.md)で区別する。

外部リポジトリのRTL・テストは取り込んでいない。独立受信モデルと形式検証ハーネスはこの作業で作成した。
サブエージェントのコードレビューは同一モデル設定による内部レビューで、外部の第三者による独立評価ではない。

Verilator v5.036の取得済み公式archiveには[LGPLv3のLICENSE](https://github.com/verilator/verilator/blob/v5.036/LICENSE)と
[Artistic License 2.0](https://github.com/verilator/verilator/blob/v5.036/Artistic)が含まれることを確認した。
今回のZIPにはツール本体やライブラリを同梱せず、Dockerfileによる環境構築と版の記録を提供する。
