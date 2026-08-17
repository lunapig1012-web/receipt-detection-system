# プロジェクト状況

最終更新日: 2026-08-16\
プロジェクト名: `receipt-detection-system`\
現在の段階: MVP 実装完了、プロジェクト凍結前の整合性確認中

## 1. プロジェクト概要

本プロジェクトは、日本の中小企業で経費精算を担当する会計スタッフを対象とした、
日本語レシートの経費データ化支援システムである。

完全な会計システムではなく、レシート画像から必要な情報を抽出し、ユーザー確認後に
Excel へ出力する軽量な AI 支援ワークフローを目的としている。

## 2. 正式な設計資料

現在の設計判断では、以下の資料を参照する。

-   `PROJECT_SPEC_v3_updated.md`
-   `DESIGN_DECISIONS_updated.md`
-   `PROJECT_SPEC_training_revision.md`
-   `deploy_config.json`

## 3. 現在のシステム構成

``` text
Receipt Image
    ↓
YOLO11n Detection
    ├── date
    ├── phone
    └── total
    ↓
ROI Crop
    ↓
EasyOCR
    ↓
Date / Phone normalization
Amount Parser
    ↓
Streamlit confirmation
    ↓
Merchant manual input
Tax-rate selection and tax calculation
    ↓
Excel Export
```

YOLO11n はフィールド位置の検出だけを担当し、文字認識は行わない。 EasyOCR
は YOLO が検出した ROI 内の文字認識を担当する。

## 4. デプロイ設定

現在の正式なローカル推論設定は `deploy_config.json` に集約されている。

``` json
{
  "model_path": "models/best.pt",
  "imgsz": 1024,
  "conf_threshold": 0.5,
  "classes": {
    "0": "date",
    "1": "phone",
    "2": "total"
  }
}
```

以下の実行経路は、この設定を既定値として共有している。

-   `detection/yolo_detector.py`
-   `detection/test_yolo_detector.py`
-   `app/receipt_pipeline.py`
-   `app/streamlit_app.py` から呼び出される Pipeline

Streamlit は YOLO の `imgsz` や confidence threshold を個別に指定せず、
`process_receipt_image()` の既定設定を使用する。

## 5. 実装状況

### 完了

-   YOLO11n 学習 notebook
-   `models/best.pt` の配置
-   YOLO ローカル検出モジュール
-   EasyOCR 共通サービス
-   YOLO bbox に基づく ROI OCR
-   date と phone の文字列正規化
-   total ROI の複数 OCR 試行
-   最終支払金額のルールベース抽出
-   `amount_value` と `amount_display` の分離
-   Streamlit 4 ステップ UI
-   店舗名の手入力
-   8% / 10% の税率選択
-   税込合計からの消費税額計算
-   Excel プレビュー、出力、ダウンロード
-   Excel ファイルが使用中の場合の別名保存

### 手動動作確認済み

`data/receipts/test_receipt.jpg` を使用した Streamlit
の手動確認では、以下の処理が完了している。

-   画像アップロード
-   YOLO による date / phone / total 検出
-   ROI OCR
-   date / phone / amount の表示
-   店舗名と税率の入力
-   税額計算
-   Excel 出力

## 6. 主要ファイルの責務

  --------------------------------------------------------------------------------------
  ファイル                            責務
  ----------------------------------- --------------------------------------------------
  `deploy_config.json`                モデルパス、推論サイズ、confidence
                                      threshold、クラス対応の管理

  `detection/yolo_detector.py`        YOLO11n
                                      モデルの読み込み、推論、検出結果と注釈画像の生成

  `ocr/easyocr_service.py`            EasyOCR の初期化と OCR 結果の共通形式への変換

  `extraction/amount_parser.py`       total ROI の OCR 候補から最終支払金額を抽出

  `app/receipt_pipeline.py`           YOLO、ROI crop、OCR、解析処理の統合

  `app/streamlit_app.py`              画像アップロード、結果表示、手入力、確認、Excel
                                      出力操作

  `utils/excel_export.py`             確認済みレシート情報の Excel 出力
  --------------------------------------------------------------------------------------

## 7. データセット

現在確認できるデータセット情報は以下のとおりである。

-   自己収集した日本語レシート: 125 枚
-   1 画像につき 1 レシート
-   YOLO クラス数: 3
-   クラス順序: `date`, `phone`, `total`
-   Train: 100 枚
-   Validation: 12 枚
-   Test: 13 枚
-   現在の Roboflow データセット: version 3
-   データセット内に記載されたライセンス: CC BY 4.0

対象レシートの種類:

-   飲食店
-   スーパーマーケット
-   ドラッグストア
-   100 円ショップ
-   小売店

## 8. YOLO 学習状況

学習エントリーポイント:

-   `docs/260810-receipts_detection_yolo11n_training.ipynb`

保存された notebook の学習コードで確認できる主な設定:

-   Base model: `yolo11n.pt`
-   Training image size: 640
-   Epochs: 300
-   Batch size: 8
-   Patience: 80
-   Mosaic: 0.2
-   Translation: 0.05
-   Scale: 0.2
-   Horizontal flip: 0.0
-   Vertical flip: 0.0
-   Seed: 42

保存された学習出力では、292 epoch で early stopping が実行され、best
epoch は 212 と記録されている。

notebook に保存されている validation split の全クラス指標:

  指標             値
  ----------- -------
  Precision     0.980
  Recall        0.957
  mAP50         0.991
  mAP50-95      0.703

これらは `imgsz=640` の validation split
指標であり、現在のデプロイ条件における test split 指標ではない。

ローカルの `models/best.pt` は、
`docs/training_results/phase1_yolo11n_training_artifacts.zip` 内の
`best.pt` と SHA-256 が一致している。

## 9. Test Split Evaluation の状況

正式な deployment configuration による test split evaluation
を実行済み。

評価条件:

-   状態: 完了
-   実行環境: Kaggle
-   `split=test`
-   `imgsz=1024`
-   `conf=0.5`
-   model: `models/best.pt`

Kaggle evaluation artifact:

``` text
test_1024_conf_0_5_evaluation_artifacts.zip
```

使用モデル SHA-256:

``` text
f8a443ac6654a9dfcff0863f3177139175a6bbefd0e9955c12220e9dd5cef369
```

### Deployment Evaluation Results

Overall metrics:

  指標             値
  ----------- -------
  Precision     0.953
  Recall        0.944
  mAP50         0.962
  mAP50-95      0.709

Per-class metrics:

  Class     Precision   Recall   mAP50   mAP50-95
  ------- ----------- -------- ------- ----------
  date          0.899    0.917   0.901      0.698
  phone         0.989    1.000   0.995      0.736
  total         0.973    0.917   0.989      0.693

## 10. OCR 処理

現在の OCR 設定:

-   Engine: EasyOCR
-   Languages: `ja`, `en`
-   Windows 既定: CPU
-   入力対応: 画像パス、PIL Image、NumPy array
-   OCR bbox: `[x1, y1, x2, y2]`

主処理ではレシート全体を OCR せず、YOLO bbox から切り出した ROI
を使用する。

通常フィールドの相対 padding ratio は 0.05 である。total
フィールドでは、文字切れや 小さい数字の認識を改善するため、base ROI と
wide ROI を使用し、画像を 3 倍に拡大して 複数回 OCR を実行する。

最終金額は次の 2 形式で保持する。

``` text
amount_value   = 2706
amount_display = "¥2706"
```

`amount_value` は税額計算に使用し、`amount_display` は UI と Excel
表示に使用する。

## 11. Streamlit

アプリケーション名:

``` text
レシートAI精算システム
```

現在の画面フロー:

1.  レシートアップロード
2.  AI 検出結果
3.  入力情報
4.  確認・Excel 出力

現在の UI は 1 回のワークフローで 1 枚の画像を処理する。

AI 検出結果として表示する項目:

-   日付
-   電話番号
-   合計金額

ユーザー入力項目:

-   店舗名
-   税率 8% / 10%

消費税額は、税込合計金額を前提として次の式で計算する。

``` text
tax = total_amount * tax_rate / (100 + tax_rate)
```

## 12. Excel 出力

出力列:

1.  ID
2.  Date
3.  Phone
4.  Merchant
5.  Amount
6.  Tax
7.  Image_Path

既定の出力先:

``` text
output/excel/receipt_results.xlsx
```

現在は 1 回の出力につき 1 件のレシート情報を持つ新しい workbook
を作成する。

## 13. 現在の制限

-   データセットは 125 枚に限定されている
-   未知の店舗やレシート形式に対する一般化性能は未確認
-   店舗名は自動抽出しない
-   税率と税額は OCR から自動抽出しない
-   Streamlit は一度に 1 枚のレシートを処理する
-   date / phone / amount は現在の UI では読み取り専用である
-   UI は低 confidence の検出結果を個別に警告しない
-   Python 依存パッケージのバージョンが `requirements.txt`
    で固定されていない
-   自動化された Streamlit end-to-end テストはない

## 14. 凍結前に確認が必要な項目

-   [x] `models/best.pt` を配置
-   [x] ローカル推論設定を `imgsz=1024`, `conf_threshold=0.5` に統一
-   [x] YOLO → ROI OCR → Amount Parser の主処理を実装
-   [x] Streamlit の手動機能確認
-   [x] Excel 出力の手動確認
-   [x] `imgsz=1024`, `conf_threshold=0.5` で test split evaluation
    を実行
-   [x] test split の Precision / Recall / mAP を保存
-   [ ] notebook のモデルパスと実行順序を整理
-   [ ] notebook の Colab / Kaggle 記述を統一
-   [ ] README を現在の ROI OCR フローに合わせて更新
-   [ ] 旧 coordinate matcher テストの扱いを決定
-   [ ] 不要な `__pycache__` と過去のバックアップを公開対象から除外
-   [ ] 必要に応じて依存パッケージのバージョンを固定

## 15. 今後の改善候補

正式な仕様書に記載されている改善候補:

-   レシートテンプレートの追加
-   画像前処理の改善
-   店舗名の自動抽出
-   税情報の自動抽出
-   経費カテゴリの自動分類
-   データベース連携
-   LLM を利用した情報抽出
-   OCR エンジンの精度と速度の比較
