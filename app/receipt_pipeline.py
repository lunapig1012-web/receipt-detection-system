"""YOLO の検出結果ごとに ROI を切り出し、EasyOCR で各項目を抽出する。"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from PIL import Image, ImageEnhance, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # プロジェクト直下のモジュールを参照できるようにする
    sys.path.insert(0, str(PROJECT_ROOT))

from detection.yolo_detector import (  # noqa: E402
    DEFAULT_CONF_THRESHOLD,
    DEFAULT_IMGSZ,
    DEFAULT_MODEL_PATH,
    YOLODetector,
)
from extraction.amount_parser import extract_amount
from ocr.easyocr_service import EasyOCRService

PipelineResult = Dict[str, Any]
EXPECTED_FIELDS = ("date", "phone", "total")
ROI_PADDING_RATIO_DEFAULT = 0.05
TOTAL_WIDE_PADDING_RATIO = 0.25
DETECTION_OUTPUT_DIR = PROJECT_ROOT / "output" / "detection"
TOTAL_GRAY_ALLOWLIST = None
TOTAL_DIGIT_ALLOWLIST = "0123456789,."
OCR_CONFUSION_TRANSLATION = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "Q": "0",
        "I": "1",
        "l": "1",
        "L": "1",
        "|": "1",
        "!": "1",
        "S": "5",
        "s": "5",
        "B": "8",
        "b": "8",
        "G": "6",
        "g": "6",
        "Z": "2",
        "z": "2",
        "T": "7",
        "t": "7",
        "一": "-",
        "ー": "-",
        "－": "-",
        "―": "-",
        "−": "-",
        "—": "-",
    }
)


@lru_cache(maxsize=8)
def get_yolo_detector(model_path: str, conf_threshold: float, imgsz: int) -> YOLODetector:
    # 同じ設定の YOLO 検出器を再利用する
    return YOLODetector(model_path=model_path, conf_threshold=conf_threshold, imgsz=imgsz)


@lru_cache(maxsize=1)
def get_easyocr_service() -> EasyOCRService:
    # EasyOCR サービスを 1 回だけ初期化する
    return EasyOCRService()


def _normalize_bbox(bbox: Any) -> List[int]:
    # YOLO の bbox を [x1, y1, x2, y2] に統一する
    if hasattr(bbox, "tolist"):
        bbox = bbox.tolist()

    if isinstance(bbox, dict):
        bbox = list(bbox.values())

    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        raise ValueError(f"Invalid bbox format: {bbox}")

    x1, y1, x2, y2 = bbox[:4]
    return [
        int(round(min(float(x1), float(x2)))),
        int(round(min(float(y1), float(y2)))),
        int(round(max(float(x1), float(x2)))),
        int(round(max(float(y1), float(y2)))),
    ]


def _expand_bbox(
    bbox: Sequence[int],
    image_size: Tuple[int, int],
    padding_ratio: float,
) -> List[int]:
    # bbox のサイズに応じて相対パディングを加える
    image_width, image_height = image_size
    x1, y1, x2, y2 = [int(value) for value in bbox[:4]]

    bbox_width = max(x2 - x1, 1)
    bbox_height = max(y2 - y1, 1)

    pad_x = max(int(round(bbox_width * padding_ratio)), 2)
    pad_y = max(int(round(bbox_height * padding_ratio)), 2)

    crop_x1 = max(0, x1 - pad_x)
    crop_y1 = max(0, y1 - pad_y)
    crop_x2 = min(image_width, x2 + pad_x)
    crop_y2 = min(image_height, y2 + pad_y)

    if crop_x2 <= crop_x1:
        crop_x2 = min(image_width, crop_x1 + 1)
    if crop_y2 <= crop_y1:
        crop_y2 = min(image_height, crop_y1 + 1)

    return [crop_x1, crop_y1, crop_x2, crop_y2]


def _get_detection_confidence(detection: Mapping[str, Any]) -> float:
    # confidence を安全に取り出す
    try:
        return float(detection.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _select_best_detection(
    yolo_results: Sequence[Mapping[str, Any]],
    field_name: str,
) -> Optional[Mapping[str, Any]]:
    # 同じクラスが複数ある場合は最も信頼度が高いものを採用する
    candidates = [d for d in yolo_results if str(d.get("class_name")) == field_name]
    if not candidates:
        return None
    return max(candidates, key=_get_detection_confidence)


def _sort_ocr_results(results: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    # OCR の読み順に近い形へ並べる
    def sort_key(item: Mapping[str, Any]) -> Tuple[float, float]:
        bbox = item.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            try:
                return float(bbox[1]), float(bbox[0])
            except (TypeError, ValueError):
                pass
        return float("inf"), float("inf")

    return sorted([item for item in results if isinstance(item, Mapping)], key=sort_key)


def _join_ocr_texts(results: Sequence[Mapping[str, Any]]) -> str:
    # ROI 内の OCR テキストをひとつの文字列にまとめる
    texts = []
    for item in _sort_ocr_results(results):
        text_value = str(item.get("text", "")).strip()
        if text_value:
            texts.append(text_value)
    return " ".join(texts)


def _max_ocr_confidence(results: Sequence[Mapping[str, Any]]) -> float:
    # ROI 内の OCR 信頼度の最大値を使う
    confidences: List[float] = []
    for item in results:
        try:
            confidences.append(float(item.get("confidence", 0.0)))
        except (TypeError, ValueError):
            continue
    return max(confidences) if confidences else 0.0


def _normalize_text(text: Any) -> str:
    # 全角記号や余分な空白を整える
    if text is None:
        return ""

    normalized_text = unicodedata.normalize("NFKC", str(text))
    normalized_text = normalized_text.replace("\u3000", " ")
    normalized_text = re.sub(r"\s+", " ", normalized_text)
    return normalized_text.strip()


def _normalize_ocr_text(text: Any) -> str:
    # OCR のよくある誤認識を数字寄りに寄せる
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return ""
    return normalized_text.translate(OCR_CONFUSION_TRANSLATION)


def _parse_date_text(text: str) -> str:
    # OCR テキストから日付だけを取り出す
    normalized_text = _normalize_ocr_text(text)
    if not normalized_text:
        return ""

    compact_text = normalized_text.replace(" ", "")
    patterns = [
        r"(?P<year>\d{4})[./\-年](?P<month>\d{1,2})[./\-月](?P<day>\d{1,2})",
        r"(?P<year>\d{4})[./\-](?P<month>\d{1,2})[./\-](?P<day>\d{1,2})",
        r"(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, compact_text)
        if match:
            year = int(match.group("year"))
            month = int(match.group("month"))
            day = int(match.group("day"))
            return f"{year}年{month}月{day}日"

    fallback_match = re.search(r"(\d{4}).{0,3}?(\d{1,2}).{0,3}?(\d{1,2})", compact_text)
    if fallback_match:
        year, month, day = fallback_match.groups()
        return f"{int(year)}年{int(month)}月{int(day)}日"

    return normalized_text


def _parse_phone_text(text: str) -> str:
    # OCR テキストから電話番号だけを取り出す
    normalized_text = _normalize_ocr_text(text)
    if not normalized_text:
        return ""

    compact_text = normalized_text.replace(" ", "")
    phone_pattern = re.search(r"(0\d{1,4})[-]?(\d{1,4})[-]?(\d{3,4})", compact_text)
    if phone_pattern:
        groups = [group for group in phone_pattern.groups() if group]
        if len(groups) >= 3:
            return "-".join(groups[:3])

    digits = re.sub(r"\D", "", compact_text)
    if len(digits) == 11:
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"

    if len(digits) == 10:
        if digits.startswith(("03", "06")):
            return f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"

    return normalized_text


def _build_annotated_image_path(image_file: Path) -> Path:
    # 検出画像の保存先を決める
    return DETECTION_OUTPUT_DIR / f"{image_file.stem}_detected.jpg"


def _prepare_total_image(crop_image: Image.Image, preprocess: str) -> Image.Image:
    # total 用の軽量前処理を行う
    image = crop_image

    if preprocess == "gray":
        image = ImageOps.autocontrast(ImageOps.grayscale(image))
    elif preprocess == "contrast":
        image = ImageEnhance.Contrast(ImageOps.grayscale(image)).enhance(1.4)
        image = ImageOps.autocontrast(image)
    elif preprocess == "sharpen":
        image = ImageOps.autocontrast(ImageOps.grayscale(image))
        image = ImageEnhance.Sharpness(image).enhance(1.8)
    elif preprocess == "threshold":
        image = ImageOps.grayscale(image)
        image = image.point(lambda pixel: 255 if pixel > 170 else 0)
        image = ImageOps.autocontrast(image)

    resized_width = max(image.width * 3, image.width)
    resized_height = max(image.height * 3, image.height)
    return image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)


def _run_total_ocr_attempt(
    *,
    mode: str,
    preprocess: str,
    crop_image: Image.Image,
    ocr_service: EasyOCRService,
    allowlist: Optional[str],
) -> Dict[str, Any]:
    # total ROI に対して 1 回の OCR を実行する
    prepared_image = _prepare_total_image(crop_image, preprocess)
    ocr_results = ocr_service.ocr_image(prepared_image, allowlist=allowlist)
    raw_text = _join_ocr_texts(ocr_results)
    confidence = _max_ocr_confidence(ocr_results)

    return {
        "mode": mode,
        "preprocess": preprocess,
        "ocr_text": raw_text,
        "confidence": confidence,
        "texts": ocr_results,
        "width": prepared_image.width,
        "height": prepared_image.height,
        "allowlist": allowlist or "",
    }


def _build_total_attempts(
    *,
    yolo_bbox: Sequence[int],
    receipt_image: Image.Image,
    ocr_service: EasyOCRService,
    crop_padding_ratio: float,
) -> Tuple[List[Dict[str, Any]], List[int], List[int]]:
    # total 用の OCR 候補を複数作る
    base_crop_bbox = _expand_bbox(yolo_bbox, receipt_image.size, crop_padding_ratio)
    wide_crop_bbox = _expand_bbox(yolo_bbox, receipt_image.size, max(crop_padding_ratio, TOTAL_WIDE_PADDING_RATIO))

    base_crop_image = receipt_image.crop(tuple(base_crop_bbox))
    wide_crop_image = receipt_image.crop(tuple(wide_crop_bbox))

    attempts = [
        _run_total_ocr_attempt(
            mode="base",
            preprocess="gray",
            crop_image=base_crop_image,
            ocr_service=ocr_service,
            allowlist=TOTAL_GRAY_ALLOWLIST,
        ),
        _run_total_ocr_attempt(
            mode="wide",
            preprocess="gray",
            crop_image=wide_crop_image,
            ocr_service=ocr_service,
            allowlist=TOTAL_GRAY_ALLOWLIST,
        ),
        _run_total_ocr_attempt(
            mode="wide",
            preprocess="gray",
            crop_image=wide_crop_image,
            ocr_service=ocr_service,
            allowlist=TOTAL_DIGIT_ALLOWLIST,
        ),
    ]

    return attempts, base_crop_bbox, wide_crop_bbox


def _process_field_roi(
    field_name: str,
    detection: Mapping[str, Any],
    receipt_image: Image.Image,
    ocr_service: EasyOCRService,
    crop_padding_ratio: float,
    errors: List[str],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], Any]:
    # 1 つの検出領域を切り出して OCR と解析を行う
    yolo_bbox = _normalize_bbox(detection.get("bbox", []))
    crop_bbox = _expand_bbox(yolo_bbox, receipt_image.size, crop_padding_ratio)
    crop_image = receipt_image.crop(tuple(crop_bbox))

    try:
        ocr_results = ocr_service.ocr_image(crop_image)
    except Exception as exc:
        ocr_results = []
        errors.append(f"{field_name} OCR failed: {exc}")

    raw_text = _join_ocr_texts(ocr_results)
    confidence = _max_ocr_confidence(ocr_results)
    parsed_value: Any = None

    if field_name == "date":
        parsed_value = _parse_date_text(raw_text)
    elif field_name == "phone":
        parsed_value = _parse_phone_text(raw_text)

    field_entry = {
        "field": field_name,
        "yolo_bbox": yolo_bbox,
        "crop_bbox": crop_bbox,
        "texts": ocr_results,
    }
    debug_entry = {
        "field": field_name,
        "yolo_bbox": yolo_bbox,
        "crop_bbox": crop_bbox,
        "ocr_text": raw_text,
        "confidence": confidence,
        "parsed_value": parsed_value,
        "attempts": [],
        "selected_candidate": None,
        "amount_value": None,
        "amount_display": "",
    }
    flat_ocr_results = [
        {
            "field": field_name,
            "yolo_bbox": yolo_bbox,
            "crop_bbox": crop_bbox,
            "text": item.get("text", ""),
            "confidence": item.get("confidence", 0.0),
            "bbox": item.get("bbox", []),
        }
        for item in ocr_results
        if isinstance(item, Mapping)
    ]

    return field_entry, debug_entry, flat_ocr_results, parsed_value


def _process_total_field(
    detection: Mapping[str, Any],
    receipt_image: Image.Image,
    ocr_service: EasyOCRService,
    crop_padding_ratio: float,
    errors: List[str],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], Any]:
    # total フィールドは複数の OCR 候補から最終金額を決める
    yolo_bbox = _normalize_bbox(detection.get("bbox", []))
    attempts, base_crop_bbox, wide_crop_bbox = _build_total_attempts(
        yolo_bbox=yolo_bbox,
        receipt_image=receipt_image,
        ocr_service=ocr_service,
        crop_padding_ratio=crop_padding_ratio,
    )

    try:
        amount_result = extract_amount({"field": "total", "attempts": attempts})
    except Exception as exc:
        errors.append(f"Amount extraction failed: {exc}")
        amount_result = {
            "amount": None,
            "amount_value": None,
            "amount_display": "",
            "selected_candidate": None,
            "candidates": [],
        }

    selected_candidate = amount_result.get("selected_candidate") or {}
    selected_mode = str(selected_candidate.get("mode", ""))
    selected_preprocess = str(selected_candidate.get("preprocess", ""))
    selected_text = str(selected_candidate.get("text", ""))
    selected_confidence = float(selected_candidate.get("confidence", 0.0) or 0.0)
    amount_value = amount_result.get("amount_value")
    amount_display = str(amount_result.get("amount_display", ""))

    selected_attempt: Optional[Dict[str, Any]] = None
    for attempt in attempts:
        if (
            str(attempt.get("mode", "")) == selected_mode
            and str(attempt.get("preprocess", "")) == selected_preprocess
            and selected_text
            and selected_text in str(attempt.get("ocr_text", ""))
        ):
            selected_attempt = attempt
            break

    if selected_attempt is None and attempts:
        selected_attempt = attempts[0]

    selected_ocr_results = []
    selected_ocr_text = ""
    selected_ocr_confidence = 0.0
    if selected_attempt is not None:
        selected_ocr_results = [
            item for item in selected_attempt.get("texts", []) if isinstance(item, Mapping)
        ]
        selected_ocr_text = str(selected_attempt.get("ocr_text", ""))
        selected_ocr_confidence = float(selected_attempt.get("confidence", 0.0) or 0.0)

    field_entry = {
        "field": "total",
        "yolo_bbox": yolo_bbox,
        "crop_bbox": wide_crop_bbox,
        "texts": selected_ocr_results,
        "attempts": attempts,
    }
    debug_entry = {
        "field": "total",
        "yolo_bbox": yolo_bbox,
        "crop_bbox": wide_crop_bbox,
        "base_crop_bbox": base_crop_bbox,
        "attempts": attempts,
        "ocr_text": selected_ocr_text,
        "confidence": selected_ocr_confidence,
        "selected_candidate": selected_candidate,
        "amount_value": amount_value,
        "amount_display": amount_display,
        "parsed_value": amount_value,
        "fallback_used": bool(selected_mode and selected_mode != "base"),
        "fallback_mode": selected_mode,
        "fallback_ocr_text": selected_ocr_text,
        "fallback_confidence": selected_ocr_confidence,
        "candidates": amount_result.get("candidates", []),
    }
    flat_ocr_results = [
        {
            "field": "total",
            "yolo_bbox": yolo_bbox,
            "crop_bbox": wide_crop_bbox,
            "text": item.get("text", ""),
            "confidence": item.get("confidence", 0.0),
            "bbox": item.get("bbox", []),
        }
        for item in selected_ocr_results
    ]

    return field_entry, debug_entry, flat_ocr_results, amount_result


def process_receipt_image(
    image_path: Union[str, Path],
    model_path: Union[str, Path] = DEFAULT_MODEL_PATH,
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
    imgsz: int = DEFAULT_IMGSZ,
    crop_padding_ratio: float = ROI_PADDING_RATIO_DEFAULT,
    match_margin_ratio: float = 0.0,
) -> PipelineResult:
    # 画像 1 枚に対して YOLO -> ROI OCR -> 解析 を順番に実行する
    image_file = Path(image_path)
    if not image_file.exists():
        raise FileNotFoundError(f"Image file not found: {image_file}")

    detector = get_yolo_detector(str(Path(model_path)), float(conf_threshold), int(imgsz))
    ocr_service = get_easyocr_service()
    annotated_image_path = _build_annotated_image_path(image_file)

    yolo_results = detector.detect(
        image_file,
        save_annotated=True,
        annotated_image_path=annotated_image_path,
        imgsz=imgsz,
    )

    errors: List[str] = []
    matched_fields: List[Dict[str, Any]] = []
    ocr_debug: List[Dict[str, Any]] = []
    ocr_results: List[Dict[str, Any]] = []
    field_values: Dict[str, Any] = {}
    amount_result: Dict[str, Any] = {}

    with Image.open(image_file) as image:
        receipt_image = image.convert("RGB")

    for field_name in EXPECTED_FIELDS:
        detection = _select_best_detection(yolo_results, field_name)
        if detection is None:
            errors.append(f"YOLO detection missing for {field_name}.")
            empty_field = {
                "field": field_name,
                "yolo_bbox": [],
                "crop_bbox": [],
                "texts": [],
            }
            matched_fields.append(empty_field)
            ocr_debug.append(
                {
                    "field": field_name,
                    "yolo_bbox": [],
                    "crop_bbox": [],
                    "ocr_text": "",
                    "confidence": 0.0,
                    "parsed_value": None,
                }
            )
            field_values[field_name] = None
            continue

        if field_name == "total":
            field_entry, debug_entry, flat_items, amount_result = _process_total_field(
                detection=detection,
                receipt_image=receipt_image,
                ocr_service=ocr_service,
                crop_padding_ratio=crop_padding_ratio,
                errors=errors,
            )
            matched_fields.append(field_entry)
            ocr_debug.append(debug_entry)
            ocr_results.extend(flat_items)
            field_values[field_name] = amount_result.get("amount_value")
            continue

        field_entry, debug_entry, flat_items, parsed_value = _process_field_roi(
            field_name=field_name,
            detection=detection,
            receipt_image=receipt_image,
            ocr_service=ocr_service,
            crop_padding_ratio=crop_padding_ratio,
            errors=errors,
        )
        matched_fields.append(field_entry)
        ocr_debug.append(debug_entry)
        ocr_results.extend(flat_items)
        field_values[field_name] = parsed_value

    date_value = str(field_values.get("date") or "").strip()
    phone_value = str(field_values.get("phone") or "").strip()
    amount_value = field_values.get("total")
    amount_display = str(amount_result.get("amount_display", "")) if amount_result else ""

    result: PipelineResult = {
        "date": date_value,
        "phone": phone_value,
        "amount": amount_value,
        "amount_value": amount_value,
        "amount_display": amount_display,
        "annotated_image_path": str(annotated_image_path) if annotated_image_path.exists() else "",
        "yolo_results": yolo_results,
        "matched_fields": matched_fields,
        "ocr_results": ocr_results,
        "ocr_debug": ocr_debug,
        "error": " | ".join(errors),
    }
    return result


if __name__ == "__main__":
    # 動作確認用に JSON で結果を表示する
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    sample_image_path = PROJECT_ROOT / "data" / "receipts" / "test_receipt.jpg"
    pipeline_result = process_receipt_image(sample_image_path)
    print(json.dumps(pipeline_result, ensure_ascii=False, indent=2))
