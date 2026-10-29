# Candidate generation v1 — 2026-10-28 JST

固定課題：READMEのAPB4→8-N-1 UART仕様と既存の公開端子テスト。
controlは既存個人制作RTLの完全コピー。元の生成プロンプトとsampling設定はunavailable。

focusedへ与えた指示：

> 既存RTLを読み、分周カウンタだけをupcounterからdowncounterへ変更する。
> tickをzero検出、reset/IDLE/tickをLAST_COUNTの再ロード、activeを減算にする。
> インターフェース、APB動作、フレーム長、bit順、リセット、全パラメータ条件を保つ。
> 他の機能を追加しない。性能優位を仮定しない。同じ固定テストで検証する。

親と作業エージェントは同じモデル設定を継承。システムが示すモデル族はGPT-6。
正確な実行モデルID、モデル生成seed、temperature/top_p等、セッション配賦費用はunavailableまたはunknown。
追加の有料モデルAPI呼出しは行っていない。CocotbのPRNG seed=0はテスト実行用であり、モデル生成seedではない。
wildcard軸の抽選は実施していない。
