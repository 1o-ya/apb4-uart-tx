> Historical local verification record (2026-10-28). Publication occurred later; current GitHub CI status is recorded by Actions. Local paths were redacted for this public snapshot.

# サイクル002：FPGAなしの検証強化

**最終版：ZIP追試で見つかった後処理の競合を修正し、macOS・Linuxの全ゲートを同一ソースで再実行して合格した。**

[機械可読サマリ](SUMMARY.json)、[ホストの全結果](host/verification.json)、[Linuxの全結果](linux/verification.json)、
[コンテナ識別子と構築条件](container-environment.json)を保存した。
GitHub Actions上の実行と、外部の第三者による追試は未実施。

## 1. 今回の課題

既存APB4 UART Txを、FPGAなしで第三者が検証・学習できる形へ強化した。
UARTの新機能追加、CRC/QEC等の別IP、共通プラットフォーム化は選ばなかった。
RTL2案のバイト列と外部仕様は初回サイクルから変更していない。

## 2. 事実・推論・unknown

- 事実：異なるOS・ツール版で、同じソースの全検証が通った。実際のソース／実行系／仕様のハッシュを各JSONに記録。
- 推論：別シミュレータ、別の受信モデル、意図的な故障、有界SATを組み合わせたことで、単一のテストだけより見落としを探しやすくなった。
- unknown：未試験の条件での不具合、実機特性、ASIC品質、外部第三者による再現、販売需要。

## 3. 入出力と自分で動かす方法

APB DATAレジスタへの1 byte書込み→UART 8-N-1、LSB first。
[仕様](../../README.md)、[VS Codeでの日本語手順](../../docs/SIMULATION_JA.md)、
[Linux環境](../../docs/CONTAINER.md)を参照。

```sh
make demo     # A/Z波形。reports/demo/dump.vcdをSurferで開く
make test     # 短い試験
make verify   # 全ローカル検証
```

## 4. 実施した試験と限界

以下は**各環境それぞれ**の実行結果。異なる条件の件数を足して網羅性の指標にしない。

- 通常回帰288件：両RTL×両シミュレータ×9設定×8試験。
- 独立受信モデルを使う通信24ケース：両RTL×両シミュレータ×D=1/3/10×2 seed。
- HDL行coverageを有効にした18試験、短いA/Zデモ2試験。
- 不正パラメータ10組の拒否。
- 12種類の故障を12/12検出。無変更の基準RTLの合格も別途必要。
- 有界SAT証明6件、非自明な動作への到達証跡6件、誤実装の反例。
- 合否判定・空テスト拒否・プロセス後処理の単体試験29件。期待IDと実行IDが一致。
- lint、Yosys generic synthesis、試験前後のソース不変確認。

ホストはPython3.11.15／Icarus13.0／Verilator5.052／Yosys0.70+post。
LinuxはPython3.11.18／Icarus11.0／Verilator5.036／Yosys0.23。
HDL行coverageはホスト77/82行、Linux76/81行。未到達は両者とも127–131行のdefault状態回復部分。
分母はツール版の計測結果であり、全機能・全条件のcoverageとは扱わない。未到達行を率のために除外していない。

未実施：FPGA/ASIC実機、STA、CDC/RDC、DFT、配置配線、全パラメータ・無限長の形式証明、
Windows native／amd64での実行、外部第三者の追試、顧客受入。
形式検証はD=1/2/3と32/52/72クロックの範囲で、非同期resetのサブクロック挙動やアナログは証明しない。

## 5. 2案の比較と失敗から追加した回帰

比較因子は加算／減算カウンタの方向だけ。新しいガチャ候補は増やしていない。
ホストのgenericセル数はcontrol170／focused158、Linuxはcontrol166／focused168。
**異なる実行環境・ツール版では大小関係が逆転した。** この数から面積・電力・Fmaxの優位を判断せず、基準RTLはcontrolを維持する。

空白パス、2-state初期reset、空の単体試験、raw CLIの終了コード、別セッションの子孫残留、CIのquick指定を修正。
[検証過程](../../docs/VERIFICATION.md)に、修正内容と対応する試験を記録した。
開発途中のソース変更による全体不合格は[保存した失敗サマリ](../failures/cycle_002-development/verification.json)、
コンテナの開発用ヘッダ不足は[ビルド失敗抜粋](../failures/cycle_002-container-header.log)に残した。
初回ZIPを別フォルダへ展開した際のDarwin終了処理の競合も、[失敗ログと元ZIPの識別子](../failures/cycle_002-extracted-cleanup/)を保存した。
プロセスグループを先に終了する修正と回帰1件を追加し、修正版は別フォルダで3回のquick合格後に、両環境のfullを再実行した。
ソースを固定した最終実行とは区別する。12個の意図的な故障も本番候補の不具合数に混ぜない。

## 6. 実例から採った慣習

[一次資料とライセンス記録](../../docs/SOURCES.md)を参照。
同じコマンドをローカルとCIで呼ぶ、依存を固定する、ツール版・seed・hash・XML・波形・失敗を保存する、
第三者が読めるREADMEを用意する慣習を採用。GitHub標準という一枚岩の認定とは扱わない。
コンテナはベースdigestとVerilator source SHA256を固定し、aptの取得時点までは固定せず実際の版を記録した。

## 7. 需要・利用・収益

外部公開・顧客連絡・課金は未実施。需要・利用・売上・利益・外部再現はunknown。
追加の有料モデルAPIは呼び出していない。利用中セッション等の配賦費用はunknown。
公開ライセンスは未決。技術検証が通っても、自動的に配布許諾や量産保証が付くわけではない。

## 8. 次の行動

まずユーザー自身がVS Codeでmake demoを実行し、A/Zの波形を確認する。その後make test、make verifyへ進む。
制作側の検証強化はここで区切り、次は具体的な再現失敗や技術質問を受けて修正する。
公開を選ぶ場合はLICENSEを決め、外部の第三者にこの単位で追試してもらう段階へ進む。
本人の判断前のpush・公開・投稿は行っていない。
