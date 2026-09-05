"""抽出した領収書情報をExcelに出力するモジュール。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence, Union

from openpyxl import Workbook

DEFAULT_OUTPUT_FILENAME = "receipt_results.xlsx"
EXCEL_HEADERS = ["ID", "Date", "Phone", "Merchant", "Amount", "Tax", "Image_Path"]


def _normalize_amount_display(value: Any) -> str:
    # 金額を「¥2706」の表示形式へそろえる
    if value is None:
        return ""

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if text.startswith("¥"):
            return text
        text = text.replace(",", "").replace(" ", "")
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits:
            return f"¥{int(digits)}"
        return text

    try:
        return f"¥{int(value)}"
    except (TypeError, ValueError):
        return str(value)


def _normalize_output_path(output_path: Union[str, Path]) -> Path:
    # 出力先がフォルダでもファイルでも扱えるように正規化する
    output_file = Path(output_path)
    if output_file.exists() and output_file.is_dir():
        return output_file / DEFAULT_OUTPUT_FILENAME
    if output_file.suffix.lower() != ".xlsx":
        return output_file.with_suffix(".xlsx")
    return output_file


def _get_cell_value(receipt_data: Mapping[str, Any], key: str) -> Any:
    # 数値項目は整数、それ以外は文字列としてExcelへ出力する
    if key == "amount":
        amount_display = receipt_data.get("amount_display")
        if amount_display not in (None, ""):
            return _normalize_amount_display(amount_display)

        amount_value = receipt_data.get("amount_value", receipt_data.get("amount"))
        if amount_value in (None, ""):
            return ""
        return _normalize_amount_display(amount_value)

    value = receipt_data.get(key)
    if value is None:
        return ""

    if key == "tax":
        try:
            return int(value)
        except (TypeError, ValueError):
            return ""

    return str(value)


def _build_fallback_output_path(output_file: Path) -> Path:
    # 同名ファイルが開かれていて保存できない場合の退避先を作る
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fallback_path = output_file.with_name(f"{output_file.stem}_{timestamp}{output_file.suffix}")

    counter = 1
    while fallback_path.exists():
        fallback_path = output_file.with_name(
            f"{output_file.stem}_{timestamp}_{counter}{output_file.suffix}"
        )
        counter += 1

    return fallback_path


def _write_workbook(workbook: Workbook, output_file: Path) -> Path:
    # 保存先を順番に試し、固定ファイルが使えない時は別名で保存する
    try:
        workbook.save(output_file)
        return output_file
    except PermissionError:
        fallback_path = _build_fallback_output_path(output_file)
        workbook.save(fallback_path)
        return fallback_path


def export_to_excel(
    receipt_data: Union[Mapping[str, Any], Sequence[Mapping[str, Any]]],
    output_path: Union[str, Path],
) -> Path:
    # 領収書情報をExcelファイルとして保存する
    if isinstance(receipt_data, Mapping):
        records = [receipt_data]
    elif isinstance(receipt_data, Sequence) and not isinstance(receipt_data, (str, bytes)):
        records = list(receipt_data)
        if not all(isinstance(record, Mapping) for record in records):
            raise TypeError("receipt_data must contain mappings")
    else:
        raise TypeError("receipt_data must be a mapping or a sequence of mappings")

    output_file = _normalize_output_path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Receipt Results"

    worksheet.append(EXCEL_HEADERS)
    for record in records:
        worksheet.append(
            [
                _get_cell_value(record, "id"),
                _get_cell_value(record, "date"),
                _get_cell_value(record, "phone"),
                _get_cell_value(record, "merchant"),
                _get_cell_value(record, "amount"),
                _get_cell_value(record, "tax"),
                _get_cell_value(record, "image_path"),
            ]
        )

    return _write_workbook(workbook, output_file)


if __name__ == "__main__":
    # 動作確認用の簡単なサンプル
    sample_receipt_data = {
        "id": "sample-001",
        "date": "2024-08-10",
        "phone": "075-315-1801",
        "merchant": "（株）万代 五条西小路店",
        "amount": 300,
        "tax": 22,
        "image_path": "data/receipts/test_receipt.jpg",
    }

    saved_path = export_to_excel(
        sample_receipt_data,
        Path(__file__).resolve().parents[1] / "output" / "excel" / DEFAULT_OUTPUT_FILENAME,
    )
    print(json.dumps({"saved_path": str(saved_path)}, ensure_ascii=False, indent=2))
