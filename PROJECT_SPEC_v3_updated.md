# PROJECT_SPEC_v3

# AI Receipt Expense Data Extraction System (Japan)

## 1. Project Goal

### Purpose

Develop an AI-assisted system that converts Japanese receipts (レシート)
and expense-related receipts (領収書) into structured expense records.

### Target Users

Small businesses in Japan.

### Main Users

Accounting staff responsible for processing employee expense receipts.

### Business Value

Reduce manual data entry during expense reimbursement and provide a
lightweight AI-assisted expense digitization workflow.

------------------------------------------------------------------------

## 2. User Flow

1.  Upload receipt images.
2.  YOLO11n detects important field regions.
3.  EasyOCR recognizes text from the receipt image or detected regions.
4.  Amount extraction obtains the final payment amount.
5.  User reviews and edits results in Streamlit.
6.  User enters tax rate when required.
7.  System calculates tax amount.
8.  Export to Excel.

------------------------------------------------------------------------

## 3. AI Architecture

-   YOLO11n: Detect date / phone / total field regions.
-   EasyOCR: Recognize receipt text.
-   Amount extraction: Extract final payment amount from OCR results
    matched with YOLO total region.
-   Streamlit: User confirmation and manual input.
-   Excel: Final export.

YOLO is used for field localization, not text recognition.

OCR is used mainly for extracting text from detected business fields,
especially the final payment amount.

Phone, date and total have relatively stable layouts, so they are
detected by YOLO.

Merchant: - Manual confirmation in Streamlit MVP.

Tax: - User inputs tax rate in Streamlit. - System calculates tax based
on total amount.

------------------------------------------------------------------------

## 4. Object Detection

Model: YOLO11n

Classes: - date - phone - total

------------------------------------------------------------------------

## 5. Annotation Rules

Annotate complete semantic fields.

Phone: - TEL + phone number

Date: - Label + date

Total: - Final payment field only.

Examples: - 合計 - 税込金額 - 支払金額 - お買上金額

Do not annotate: - 小計 - 消費税

------------------------------------------------------------------------

## 6. Dataset

-   125 self-collected Japanese receipts
-   One receipt per image

Receipt types: - Restaurant - Supermarket - Drugstore - 100-yen shop -
Retail

Split: - Train 80% - Validation 10% - Test 10%

------------------------------------------------------------------------

## 7. OCR Design

OCR Engine: EasyOCR

YOLO detected regions: - phone - date - total

OCR purpose: - Extract text from detected regions. - Extract final
payment amount.

Merchant and tax are not automatically extracted in the MVP.

------------------------------------------------------------------------

## 8. Amount Extraction

1.  YOLO detects the final payment amount region.
2.  EasyOCR recognizes text.
3.  OCR text boxes are matched with the YOLO total-region bounding box.
4.  The final payment amount is parsed from matched OCR text.

Priority: - 合計 - 税込 - 支払

Fallback: - Largest numeric value.

------------------------------------------------------------------------

## 9. Streamlit

-   Image upload
-   AI processing
-   YOLO visualization
-   Display extracted amount
-   Manual merchant input
-   Tax rate selection
-   User confirmation
-   Excel export

------------------------------------------------------------------------

## 10. Excel

Columns: - ID - Date - Phone - Merchant - Amount - Tax - Image_Path

------------------------------------------------------------------------

## 11. Environment

-   Windows
-   VSCode
-   Python
-   Google Colab
-   Ultralytics YOLO11n
-   EasyOCR

------------------------------------------------------------------------

## 12. Future Improvements

-   More receipt templates
-   Better preprocessing
-   Automatic merchant extraction
-   Automatic tax extraction
-   Automatic category classification
-   Database integration
-   LLM-assisted extraction
