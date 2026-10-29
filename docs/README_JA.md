# APB4 UART Tx — PC simulation and verification

APBレジスタに書いた1 byteを、8-N-1のUART波形として出す小さな送信IPです。
FPGAボードなしで、ソース・仕様・試験・波形を第三者が追試できることを目指します。
既存の個人制作RTLを再利用し、加算／減算カウンタの2案を同じ仕様で検証します。

## 最初に動かす

初回はPython仮想環境とIcarus、またはDev Containerを準備してください。VS Codeでフォルダを開き、ターミナルから実行します。

```sh
make demo
```

A/Zを送信し、`reports/demo/dump.vcd`へ最後に成功した波形をコピーします。
VS CodeのSurfer拡張で開けます。導入・信号の選び方・bitの読み方・送信値の変え方は
[日本語のシミュレーション手順](SIMULATION_JA.md)にまとめました。

```sh
make test       # 短い回帰（makeだけでも同じ）
make verify     # 全ローカル検証。GitHub CIもこのコマンド
make formal     # 有界形式検証だけ
make mutations  # 12種類の故障検出だけ
make unit       # 結果判定とプロセス後処理の単体試験
```

別PCでは[Dev Container](CONTAINER.md)でLinux環境を揃えられます。
ホストにPython 3.11以降・Icarus 11以降・Make・psを用意する場合は、初回だけ次を実行します。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make demo
```

全検証にはVerilator 5.036以降、C++コンパイラ、Yosysも必要です。
`make verify`は必要なツールがなければ失敗し、省略したゲートを合格扱いしません。
追加の有料APIやクラウドサービスは不要です。

## 入出力と固定仕様

`uart_tx_apb`は単一クロックです。`clk`をPCLKとして使い、`rst_n`は非同期Lowリセットです。
入力は`paddr[31:0]`, `psel`, `penable`, `pwrite`, `pwdata[31:0]`, `pstrb[3:0]`, `pprot[2:0]`。
出力は`prdata[31:0]`, `pready`, `pslverr`, `tx`です。
アドレスは32-bitのローカルなbyteオフセットで、ベースアドレスのデコードは上流で行います。

- `0x00 DATA`：書込み専用。`PSTRB[0]=1`の成立エッジで下位8 bitを取り込みます。
- `0x04 STATUS`：読取り専用。bit 0がBUSY、上位bitは0です。
- 送信中の有効DATA書込みは`PREADY=0`で待機。FIFOはなく、待機はほぼ1フレームに及びます。
- `PSTRB[0]=0`のDATA書込みは無操作で即完了。上位ストローブとデータは送信内容に影響しません。
- DATA読取り、STATUS書込み、未定義・非整列アドレスはエラー完了し、送信に副作用を与えません。
- アドレス全32 bitを照合し、上位アドレスによる別名を許しません。
- `PPROT`は全組合せを許可し、アクセス制限は上流の責務です。
- リセット・未選択・SETUPでは応答は0、書込みを受理しません。APB SETUPは通常1クロックです。
- readではマスターが全`PSTRB`を0にします。wait中はマスターがアドレス・データ・制御を保持します。

UARTはSTART=0、8 data bitsをLSB first、STOP=1、idle=1です。
パラメータは正の32-bit符号付き整数`CLK_FREQ_HZ`と`BAUD_RATE`、かつ`BAUD_RATE <= CLK_FREQ_HZ`。
整数分周比`D = (CLK_FREQ_HZ + BAUD_RATE // 2) // BAUD_RATE`とし、各bitは正確にDクロック、BUSYは10Dクロックです。
次フレームの受理はIDLEに戻った次の立ち上がり以降で、待機していた書込みにも最低1クロックのidleがあります。

```text
A = 0x41: 0 | 1 0 0 0 0 0 1 0 | 1
Z = 0x5a: 0 | 0 1 0 1 1 0 1 0 | 1
```

リセットは進行中フレームを中断します。マスターも未完了転送を破棄し、解除は統合側でクロックに同期させます。
受信、FIFO、割込み、実行時のbaud変更、セキュリティ制御は対象外です。

## 検証過程

[試験仕様・結果・限界](VERIFICATION.md)に、各段階と保存した証拠を記録します。

- IcarusとVerilatorで同じ公開端子の参照試験を実行。通常の分周境界・丸め・RTL既定値・32-bit上限を含みます。
- [独立した受信モデル](STRESS_SPEC.md)でTXのbit中心を復号し、受理したAPB書込み列と照合。
  seed固定の通信、全16ストローブ、全8保護属性、異常アクセス、待機とリセットを含みます。
- [Mutation試験](MUTATIONS.md)では12種類の単一故障を実際に入れ、名前付き試験のAssertionErrorで検出を確認。
- [有界形式検証](../formal/README.md)はD=1/2/3の両案を32/52/72クロックまで確認。
  フレーム完了・待機・エラーへ到達する証跡と、誤実装に対する反例も必要です。
- VerilatorのHDL行coverage、明示した警告除外つきlint、Yosysのgeneric synthesisを別々に記録。
- テスト0件・skip・欠落・破損・名前違い・タイムアウトを成功扱いしない検証と、子孫プロセスの後処理を試験。

各実行は新規の`reports/runs/<時刻>/`へ保存します。直近の全体状態は`reports/latest-qualification.json`です。
`profile=quick`は短い試験、`profile=full`が全検証です。ソースと実行系のハッシュを実行前後で照合します。
`make regression`はサイクル001のIcarus中心の回帰手順を継続するためのコマンドで、全検証ではありません。

`control`は`rtl/uart_tx_apb.v`、`focused`は`candidates/focused/uart_tx_apb.v`です。
比較因子は分周カウンタの方向のみです。RTL本体はサイクル001から変更せず、今回は検証を強化しています。

## 確認できる範囲

これはデジタル論理のシミュレーションと、記録したインスタンス・深さに限る形式検証です。
全パラメータ・無限長の形式証明、FPGA実機、ASIC実装、STA、CDC/RDC、DFT、外部の第三者による追試、顧客受入は別の段階です。
実クロックの誤差・UART相手の許容baud誤差・電源投入・電圧・配線も含みません。
psに表せない半周期は整数psへ切り捨てるため、試験は主にシミュレーション内のクロック数を基準とします。

Generic synthesisのセル数を、特定FPGA/ASICの面積・電力・Fmaxとは呼びません。
行coverageが高いことや故障を検出したことも、全てのバグがない証明ではありません。

## 出典・公開状態

[仕様とコミュニティ実例・依存ライセンス](SOURCES.md)、[取り込み元と原本ハッシュ](PROVENANCE.md)、
[初回サイクル記録](CYCLE_001.md)、[候補生成記録](candidates.json)を保存しています。
公開ライセンスは`unknown`です。元の個人制作コードにLICENSEがなかったため、配布許諾を仮定していません。
技術検証の結果と公開ライセンスの決定は別です。外部push・公開・投稿・顧客連絡・課金は未実施です。
