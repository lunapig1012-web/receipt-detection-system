# AI Receipt Expense Data Extraction System (Japan)

## Training Design Revision Based on YOLO Training Reference

## 1. Training Strategy Decision

This project uses YOLO11n for field region detection only.

YOLO responsibilities:

-   Detect date region
-   Detect phone region
-   Detect total payment region

YOLO is not responsible for OCR or text recognition.

The detection result is passed to EasyOCR for text extraction.

The system architecture remains:

YOLO11n → Region localization → EasyOCR → Rule-based extraction →
Streamlit confirmation → Excel export

------------------------------------------------------------------------

## 2. Dataset Constraint

Current dataset:

-   125 self-collected Japanese receipt images
-   One receipt per image
-   Roboflow export: 1024 × 1024, aspect ratio preserved with padding
-   Receipt categories:
    -   Restaurant
    -   Supermarket
    -   Drugstore
    -   100-yen shop
    -   Retail

The dataset size cannot be increased in the current project stage.

Therefore, training optimization focuses on:

-   Better transfer learning
-   Suitable augmentation
-   Stable hyperparameters
-   Correct validation strategy

------------------------------------------------------------------------

## 3. Model Selection

Model:

-   YOLO11n

Reason:

YOLO11n provides:

-   Lightweight architecture
-   Fast training
-   Fast inference
-   Suitable capacity for small datasets

The project does not increase model size because the dataset is limited.

------------------------------------------------------------------------

## 4. Transfer Learning Strategy

Training should start from pretrained weights.

Reason:

125 images are insufficient for training a detector from zero.

The pretrained model provides general visual features and reduces
overfitting risk.

------------------------------------------------------------------------

## 5. Image Resolution

Current official training image size:

    imgsz = 1024

Reason:

Receipt fields such as:

-   date
-   phone number
-   total amount

are small text regions.

Higher resolution preserves more information for field localization.

------------------------------------------------------------------------

## 6. Training Epochs

Current official training configuration:

    epochs = 300
    patience = 80
    seed = 42

The requested epoch count is 300. Training stopped at epoch 245;
the best epoch was 165. The official model is `models/best.pt`.

Reason:

The dataset is small.

More epochs allow the model to repeatedly learn receipt layouts.

Early stopping was enabled with patience 80.

------------------------------------------------------------------------

## 7. Batch Size

Current official batch size:

    batch size = 8

Reason:

Higher image resolution requires more GPU memory.

A smaller batch limits GPU memory use during training.

------------------------------------------------------------------------

## 8. Data Augmentation Policy

Because receipt images have fixed orientation, aggressive augmentation
should be avoided.

Recommended:

Enabled:

-   mosaic: low probability
-   scale: moderate
-   translation: small

Disabled:

-   vertical flip
-   horizontal flip
-   strong perspective transformation

Reason:

Receipt fields have positional meaning.

Excessive transformation may damage field layout information.

------------------------------------------------------------------------

## 9. Annotation Rules

The annotation strategy remains unchanged.

Classes:

-   date
-   phone
-   total

Total field:

Annotate only the final payment field:

Examples:

-   合計
-   税込金額
-   支払金額
-   お買上金額

Do not annotate:

-   小計
-   消費税

The annotation format must be consistent.

The bounding box should always represent the complete semantic field.

------------------------------------------------------------------------

## 10. Validation Strategy

Because the dataset is small:

Dataset split:

-   Train: 100 images (80%)
-   Validation: 12 images (9.6%)
-   Test: 13 images (10.4%)

Evaluation focuses on:

-   total detection accuracy
-   date detection accuracy
-   phone detection accuracy

The most important metric is total field detection because it directly
affects expense amount extraction.

### Current Training Validation Results

Validation split: 12 images / 36 instances, imgsz=1024.
These are validation metrics, not independent test benchmark metrics.

| Metric | Value |
|---|---:|
| Precision | 0.993 |
| Recall | 1.000 |
| mAP50 | 0.995 |
| mAP50-95 | 0.731 |

### Formal Independent Test Benchmark

Test split: 13 images / 38 instances, imgsz=1024.
The benchmark uses the Ultralytics validation default confidence setting.

| Metric | Value |
|---|---:|
| Precision | 0.9411 |
| Recall | 0.9496 |
| mAP50 | 0.9686 |
| mAP50-95 | 0.6240 |

Application deployment separately uses `models/best.pt`, imgsz=1024,
and conf_threshold=0.5. This deployment filter is not the benchmark
confidence setting.

------------------------------------------------------------------------

## 11. Training Optimization Priority

Under the fixed condition of 125 images and three classes, optimization
priority:

1.  Annotation consistency
2.  Transfer learning
3.  Higher image resolution
4.  Suitable augmentation
5.  Longer stable training
6.  Hyperparameter adjustment

Increasing model complexity is not the priority.

------------------------------------------------------------------------

## 12. Expected System Behavior

The final system should not attempt full automatic accounting.

The workflow remains:

1.  Upload receipt image
2.  YOLO11n detects important fields
3.  EasyOCR recognizes text
4.  Amount extraction obtains payment amount
5.  User confirms or edits result
6.  Export expense record

Human confirmation remains part of the system design.
