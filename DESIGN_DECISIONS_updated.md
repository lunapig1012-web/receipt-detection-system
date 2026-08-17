# DESIGN_DECISIONS.md

# Design Decisions

## Project

AI Receipt Expense Data Extraction System (Japan)

This document records major architectural and technical decisions.

------------------------------------------------------------------------

# Decision 1 --- Project Position

## Decision

This project is positioned as an AI-assisted expense data extraction
system, not a complete accounting system.

Its purpose is to convert Japanese receipts into structured expense
records and reduce manual data entry.

## Reason

The project focuses on expense digitization, not accounting or
bookkeeping.

------------------------------------------------------------------------

# Decision 2 --- YOLO Responsibility

## Decision

YOLO11n is used only for detecting key business fields.

Current classes:

-   date
-   phone
-   total

YOLO is not responsible for text recognition.

## Reason

YOLO provides stable field localization.

It answers:

"Where is the important field?"

## Alternatives Considered

Detect every field with YOLO.

Rejected because:

-   More annotation work
-   Larger dataset required
-   Lower maintainability

------------------------------------------------------------------------

# Decision 3 --- OCR Engine

## Decision

Use EasyOCR.

## Reason

EasyOCR provides simple Python integration and is sufficient for MVP
receipt text recognition.

The current dataset is too small to train a custom OCR model.

## Alternatives Considered

 Alternative OCR engine.

Rejected for the current MVP because the project scope prioritizes a
lightweight implementation and simpler integration.

Custom OCR.

Rejected because the dataset size is insufficient.

## Future Improvement

Evaluate other OCR engines based on accuracy and speed.

------------------------------------------------------------------------

# Decision 4 --- Merchant Handling

## Decision

Merchant information is manually confirmed in Streamlit MVP.

## Reason

Merchant names, logos, fonts and layouts vary significantly between
stores.

Automatic extraction would require more receipt templates and larger
datasets.

Human confirmation improves reliability for expense workflows.

## Future Improvement

Add merchant extraction using OCR coordinates or a store database.

------------------------------------------------------------------------

# Decision 5 --- Tax Handling

## Decision

Tax is calculated from user-selected tax rate in Streamlit.

## Reason

Tax information appears in many different formats.

Examples:

-   消費税
-   外税
-   内税
-   8%
-   10%

Automatic extraction is not included in the MVP.

The user selects the applicable tax rate, and the system calculates tax
based on total amount.

## Future Improvement

Support automatic tax recognition.

------------------------------------------------------------------------

# Decision 6 --- Total Detection

## Decision

YOLO detects only the final payment amount.

Examples:

-   合計
-   税込金額
-   支払金額
-   お買上金額

Do not annotate:

-   小計
-   消費税

## Reason

The expense workflow requires the final payment amount.

------------------------------------------------------------------------

# Decision 7 --- Why Combine YOLO and OCR?

## Decision

The pipeline combines:

-   YOLO11n
-   EasyOCR
-   Rule-based extraction

## Reason

YOLO and OCR solve different problems.

YOLO answers:

"Where is the important business field?"

OCR answers:

"What text is written in that field?"

This architecture improves explainability and maintainability.

------------------------------------------------------------------------

# Decision 8 --- YOLO11n Selection

## Decision

Use YOLO11n.

## Reason

Current dataset:

-   125 images

YOLO11n provides:

-   Lightweight architecture
-   Fast training
-   Fast inference
-   Appropriate capacity for small datasets

------------------------------------------------------------------------

# Decision 9 --- Streamlit

## Decision

Use Streamlit as the application framework.

## Reason

The objective is to demonstrate a complete AI workflow:

-   Upload receipt
-   AI processing
-   User confirmation
-   Manual correction
-   Excel export

------------------------------------------------------------------------

# Decision 10 --- Human-in-the-loop

## Decision

Low-confidence predictions require user confirmation.

## Reason

Financial records require high reliability.

Manual confirmation reduces incorrect expense records.

------------------------------------------------------------------------

# Design Philosophy

This project prioritizes:

-   Simplicity
-   Maintainability
-   Explainability
-   Practical business value

The architecture is designed as a lightweight Document AI pipeline
suitable for Japanese small-business expense digitization.
