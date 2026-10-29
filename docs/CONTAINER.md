# Docker / VS Codeで同じLinuxシミュレーション環境を使う

FPGAは使いません。Docker内のIcarus、Verilator、Yosys、Python/CocotbがデジタルRTLを処理します。
回路を実機に書き込む環境や、UARTの電圧・配線・クロック精度を測る装置ではありません。

## VS Codeから使う

Dockerを起動し、VS Codeの[Dev Containers拡張](https://code.visualstudio.com/docs/devcontainers/containers)を用意します。
このプロジェクトのフォルダを開き、コマンドパレットから **Dev Containers: Reopen in Container** を実行してください。
初回はDockerfileからコンパイラとシミュレータを構築するため、ネットワーク接続と数分以上の時間が必要です。
`.devcontainer/devcontainer.json`がPythonとSurferのVS Code拡張を推奨します。

コンテナ内のターミナルで次を実行します。

```sh
make demo PYTHON=/opt/venv/bin/python
make verify PYTHON=/opt/venv/bin/python
```

`demo`はA/Zの短い試験、`verify`は2シミュレータ、ストレス、故障注入、境界付き形式検証、カバレッジ、lint、合成を含む強化検証です。
従来のIcarus固定回帰だけを実行する場合は`make regression PYTHON=/opt/venv/bin/python`を使用します。各ゲートの合否と制限はREADMEを参照してください。
結果はホストと共有する`reports/`以下へ残ります。VCDファイルをVS Codeで開き、Surferを表示先に選ぶと波形を確認できます。
まず`clk`, `rst_n`, `psel`, `penable`, `pready`, `paddr`, `pwdata`, `pstrb`, `tx`を表示すると、
APB書込み成立からSTART・データ・STOPまで追えます。1 bitが仕様の分周比Dクロック続くことを確認してください。

## Dockerだけで実行する

プロジェクトのルートで実行します。イメージをレジストリに公開する操作はありません。

```sh
docker build -t uart-tx-verify:local .
docker run --rm --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/workspace" \
  uart-tx-verify:local make demo PYTHON=/opt/venv/bin/python
```

ホストのPython仮想環境はコンテナに流用しません。Python実行環境は`/opt/venv`です。
build contextから`.venv`, `.git`, `reports`, `dist`, `.env`類と鍵ファイルを除外しています。
Dockerソケット・SSH鍵・クラウド認証情報をマウントする設定はありません。
共有フォルダはソースと実行結果のために書込み可能で、上の`--user`指定はLinuxホストでroot所有の結果を作らないためのものです。

## 固定したものと記録するもの

- 公式Python 3.11 slim-bookwormイメージのindex digestをDockerfileで固定。
- Cocotb 2.0.1、find_libpython 0.5.1はrequirements.txtで固定。
- Verilatorは公式タグv5.036のソースアーカイブをSHA-256照合後に構築。コンパイルは最大4ジョブ。
- ソース構築で必要な`FlexLexer.h`を`libfl-dev`で用意。コンパイル途中のファイルにはBuildKitの専用キャッシュを使う。
- Icarus・Yosys・C++コンパイラ等はDebian bookwormのパッケージ。取得時の版は`/opt/uart-toolchain/apt-packages.tsv`に記録。
- Python依存と主要ツール版も`/opt/uart-toolchain/`に記録。

Debianパッケージ配信時点まで固定したビット単位の再構築ではありません。ベースdigestとソース・Python依存は固定し、
aptの解決結果と各試験の実行ツール版を残して条件の違いを追えるようにします。
ローカルのLinuxコンテナで試験したことと、GitHub Actionsが実行済みであることは区別します。

## 実行確認

Linux arm64で全`make verify`が合格した。実際の版はPython3.11.18、Icarus11.0、Verilator5.036、Yosys0.23。
macOS arm64の同一ソースでも全検証が合格し、manifestの一致を確認した。
詳細は[保存した結果](../reports/cycle_002/SUMMARY.md)と[コンテナ識別子](../reports/cycle_002/container-environment.json)。
Windows native／amd64／GitHub Actionsでの実行はこの確認に含めていない。

出典：[公式Pythonイメージ](https://hub.docker.com/_/python)、[Verilator v5.036](https://github.com/verilator/verilator/releases/tag/v5.036)、
[Verilatorの構築手順](https://verilator.org/guide/latest/install.html)。
