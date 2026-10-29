# FPGAなしでUARTをシミュレーションする

RTLは回路の動きを書いたコードです。このプロジェクトでは、APBのレジスタへ1 byteを書き、
UARTの`tx`端子に正しい順序・長さのbitが出ることをPCで確認します。FPGAボードやGPUは不要です。

Pythonの`.venv`はテスト用ライブラリを分離する環境です。回路を動かすのはIcarus VerilogまたはVerilatorで、
波形を見るのはSurferです。DockerはこれらのLinux版をまとめる環境で、必須の実機ではありません。

## 自分のPCで最初に動かす

VS Codeで「File → Open Folder」を選び、cloneしたリポジトリのフォルダを開きます。下の`/workspace`は例です。各自が保存したフォルダに読み替えてください。

```text
/workspace
```

「Terminal → New Terminal」を開き、実行します。初回は[Dev Container](CONTAINER.md)、または後述のPython環境とIcarusを準備してください。

```sh
make demo
```

最後に`passed`と波形のパスが出れば成功です。現在のデモはAとZを送信します。
短い回帰試験も実行できます。

```sh
make test
```

`make`だけでも短い試験です。**全検証は必ず`make verify`**を指定してください。
失敗したときは終了コードが非0になり、表示された結果フォルダに詳細ログが残ります。

## 波形をVS Codeで見る

1. Extensionsで **Surfer** を検索し、発行元`surfer-project`、ID`surfer-project.surfer`の拡張を入れます。
   作成者の環境では、実際にVCDを開き、`clk`・`rst_n`・`tx`を表示できることを確認しています。
2. `make demo`の後、Explorerで`reports/demo/dump.vcd`を開きます。
3. `uart_tx_apb`スコープを選び、Variablesの名前を1回クリックして、次の信号を波形へ追加します。
   フィルタ欄へ信号名を入れると探しやすくなります。重複した行は右クリック→Removeで取り除けます。

```text
clk rst_n psel penable pwrite paddr pwdata pstrb pready pslverr tx
```

4. `tx`の最初の下降エッジ付近を拡大します。デモの設定は1 MHz／100000 baudです。

クロック1周期は1µs、UARTの1 bitは10µs、1フレームは100µsです。
`paddr=0, pwrite=1, pstrb[0]=1`の書込みが`psel && penable && pready`で成立するとSTARTが始まります。
`pwdata`は16進表示にすると`41`と`5a`を見つけやすくなります。

```text
A (0x41) : START=0 | 1 0 0 0 0 0 1 0 | STOP=1
Z (0x5a) : START=0 | 0 1 0 1 1 0 1 0 | STOP=1
```

データは下位bitから出ます。途中の同じ値が連続する部分も、各bitの長さは10µsです。
`reports/demo/verification.json`には、その波形を作った元の実行フォルダとソースのハッシュがあります。
この固定パスには最後に成功したデモをコピーします。個々の履歴は`reports/runs/`に残ります。

拡張が自動で開かないときは、VCDを右クリックして「Open With」でSurferを選びます。
他の波形拡張との競合は[Surfer公式の既知事項](https://marketplace.visualstudio.com/items?itemName=surfer-project.surfer)です。

## コマンドを入力せずタスクから実行する

`.vscode/tasks.json`を同梱しています。「Terminal → Run Task」から次を選べます。

- `UART: Demo (A/Z waveform)`：A/Zの波形を生成。
- `UART: Quick tests`：短い回帰。
- `UART: Full qualification`：両シミュレータ、追加試験、mutation、有界形式検証まで。
- `UART: Bounded formal checks`：有界形式検証だけ。
- `UART: Mutation tests`：故障を見つけられるかだけを確認。

macOSのCmd+Shift+Bでは既定のDemoタスクが動きます。タスクは同じ`make`コマンドを呼びます。
VS Codeのタスク設定と実行方法は[Microsoft公式資料](https://code.visualstudio.com/docs/debugtest/tasks)に基づいています。

## 自分で送信データを変えてみる

まず`tests/demo_uart_tx.py`を開き、`(0x41, 0x5A)`の2値を`(0x55, 0xAA)`に置き換えます。
再度`make demo`を実行し、`01010101`に対応する交互の波形を確認します。
元へ戻すときは2値を`(0x41, 0x5A)`に戻します。

この例は2 byteのまま値を変えます。byte数も変える場合は、同じファイルの期待送信件数`2`も合わせて変更してください。
テストに変えた値を書けば、参照モデルもそのbyteを期待します。RTLの内部状態を読む必要はありません。
これは自分の学習用変更なので、保存済みの公開候補とハッシュが変わることに注意してください。

## 別のPCやWindowsから追試する

環境差を減らすには、Docker DesktopとVS CodeのDev Containers拡張を使います。
リポジトリを開いた後、コマンドパレットから **Dev Containers: Reopen in Container** を実行します。
初回はLinux環境とVerilatorをビルドするため、ダウンロードとコンパイルに時間がかかります。
2回目以降はDockerのキャッシュを使えます。通常の試験にネットワークAPIは不要です。

コンテナ内のターミナルでは、同じコマンドを使います。

```sh
make demo
make test
make verify
```

VS Codeを使わずコンテナだけで実行する場合は、ホスト側から実行します。

```sh
make container-build
make container-test
```

Windowsの標準PowerShellでPOSIXツールを直接動かす経路は今回の対象外です。
Dev ContainerまたはWSL2のLinuxターミナルを使用してください。
[Dev Containers公式説明](https://code.visualstudio.com/docs/devcontainers/containers)と[環境の詳細](CONTAINER.md)も参照できます。

## Python環境を自分で用意する場合

Python 3.11以降、Icarus 11以降、Makeがあればデモ・短い試験を実行できます。
全検証にはCocotb 2と互換性のあるVerilator 5.036以降、C++コンパイラ、Yosys、`ps`も必要です。
OSの古いパッケージを組み合わせるより、同梱コンテナで揃える方法を推奨します。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make demo
```

依存を導入していないPythonや別のvenvが使われているときは、明示できます。

```sh
make demo PYTHON=/absolute/path/to/venv/bin/python
```

このプロジェクトではPython依存を固定しています。対応シミュレータの条件は
[Cocotb 2.0.1公式資料](https://docs.cocotb.org/en/v2.0.1/simulator_support.html)で確認しています。

## 合格結果の読み方

`reports/latest-qualification.json`の`status`と`profile`を見ます。
`profile=quick`は短い試験、`profile=full`が全ローカル検証です。
各実行のJSON、XML、波形、seed、機能coverage、ソースと実行系のハッシュは`reports/runs/`に保存します。
ファイルを試験中に変更した場合も、ハッシュの差を検出して全体を不合格にします。

全検証の過程と条件は[VERIFICATION.md](VERIFICATION.md)、故障試験は[MUTATIONS.md](MUTATIONS.md)、
独立受信試験は[STRESS_SPEC.md](STRESS_SPEC.md)、形式検証の仮定は[formal/README.md](../formal/README.md)です。

確認するのはデジタル論理と定めた条件の動作です。実物の配線・電圧・電源投入・発振器誤差・メタスタビリティは含みません。
有界形式検証も、指定した分周比とクロック数の範囲です。「テストが通ったから全てのバグがない」とは扱いません。
