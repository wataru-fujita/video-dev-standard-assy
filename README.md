<!--
Copyright 2026 wataru_fujita
SPDX-License-Identifier: Apache-2.0
-->

# 動画開発標準Assy

Microsoft 365 Copilot Chat(Microsoft 365 のライセンスに含まれ、追加のライセンスが要らないもの)では、MP4 は、出力の対象になっていません。
この標準は、コードインタープリターを使って、**MP4 の説明動画を書き出させる方法**を、3 つのファイルにまとめたものです。

## 使い方

1. Releases から `video-dev-standard-assy.zip` をダウンロードして、展開する
2. Copilot Chat のモードを、メニューの **GPT の Think Deeper** にする(選ぶと、左上の表示は「GPT-5.6 Sol 考える」になります)
3. `01_procedure.md` `02_reference.md` `03_plan_and_progress.md` を、1 回のメッセージに添付して、「この資料に従って、始めてください」と送る
4. 質問に答えて、構成案に OK を出すと、動画ができる
5. 作れなかったときは、次のメッセージに `00_make_video.py` を添付して、「続けてください」と送る

## 注意

- 「自動」「クイック応答」など、GPT の Think Deeper 以外では、動画を作る前に止まります
- お使いの環境で同じように動くとは限りません。手順書の環境確認が、開発環境との差分を表示します
- うまくいかなかったときは、Issue で教えてください(機密情報や個人情報は、書かないでください)

## License

Apache License 2.0(`LICENSE` を参照)。 Copyright 2026 wataru_fujita
作者個人の成果物で、無保証です。
