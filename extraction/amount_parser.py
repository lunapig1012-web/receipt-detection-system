"""total フィールドから支払金額を抽出するモジュール。"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

AMOUNT_GROUP_PATTERN = re.compile(r"(?<!\d)(\d{1,3}(?:,\d{3})+)(?!\d)")
TOTAL_HINTS = ("合計", "税込", "支払", "お買上", "お買い上げ")
NEGATIVE_HINTS = ("小計", "消費税", "外税", "内税")
CURRENCY_MARKERS = ("¥", "￥", "円")

OCR_AMOUNT_TRANSLATION = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "Q": "0",
        "D": "0",
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
        "フ": "7",
        "ﾌ": "7",
        "ロ": "0",
        "ﾛ": "0",
        "キ": "",
        "ヶ": "",
        "ケ": "",
        "ー": "",
        "―": "",
        "−": "",
        "—": "",
        "‐": "",
        "‑": "",
    }
)


def _normalize_text(text: Any) -> str:
    # 文字列を比較しやすい形へ整える
    if text is None:
        return ""

    normalized_text = unicodedata.normalize("NFKC", str(text))
    normalized_text = normalized_text.replace("\u3000", " ")
    normalized_text = re.sub(r"\s+", " ", normalized_text)
    return normalized_text.strip()


def _normalize_amount_text(text: Any) -> str:
    # OCR の誤認識を金額向けに寄せる
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return ""
    return normalized_text.translate(OCR_AMOUNT_TRANSLATION)


def _normalize_text_list(values: Any) -> List[Any]:
    # 入力を扱いやすいリストへ揃える
    if values is None:
        return []
    if isinstance(values, list):
        return values
    if isinstance(values, tuple):
        return list(values)
    if hasattr(values, "tolist"):
        converted = values.tolist()
        if isinstance(converted, list):
            return converted
        return [converted]
    return [values]


def _extract_digits(text: str) -> str:
    # 数字だけを取り出す
    return re.sub(r"\D", "", text)


def _has_total_hint(text: str) -> bool:
    # 合計を示す語が含まれているか確認する
    return any(hint in text for hint in TOTAL_HINTS)


def _has_negative_hint(text: str) -> bool:
    # 小計などの補助項目を見分ける
    return any(hint in text for hint in NEGATIVE_HINTS)


def _has_currency_marker(text: str) -> bool:
    # 通貨記号が含まれているか確認する
    return any(marker in text for marker in CURRENCY_MARKERS)


def _looks_like_standard_amount(text: str) -> bool:
    # 1,234 のような標準的な表記か確認する
    return bool(AMOUNT_GROUP_PATTERN.search(text))


def _format_amount_display(amount_value: int) -> str:
    # 表示用の金額を正規化する
    return f"¥{amount_value}"


def _build_candidate(
    *,
    raw_text: str,
    normalized_text: str,
    amount_value: int,
    confidence: float,
    attempt_mode: str,
    preprocess: str,
    bbox: Sequence[Any],
    attempt_width: int,
    attempt_height: int,
    attempt_has_total_hint: bool,
    attempt_has_currency_marker: bool,
    attempt_has_negative_hint: bool,
) -> Dict[str, Any]:
    # 候補 1 件を整理する
    x1 = y1 = x2 = y2 = 0
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        try:
            x1 = float(bbox[0])
            y1 = float(bbox[1])
            x2 = float(bbox[2])
            y2 = float(bbox[3])
        except (TypeError, ValueError):
            x1 = y1 = x2 = y2 = 0.0

    width = max(int(attempt_width), 1)
    height = max(int(attempt_height), 1)
    x_center = ((x1 + x2) / 2.0) / width
    y_center = ((y1 + y2) / 2.0) / height
    digit_text = str(amount_value)
    digit_count = len(digit_text)

    score = 0.0
    score += float(confidence) * 4.0
    score += x_center * 1.4
    score += y_center * 0.8
    score += min(digit_count * 0.35, 1.6)

    if digit_count == 4:
        score += 2.0
    elif digit_count == 5:
        score += 1.2
    elif digit_count == 3:
        score += 0.8
    elif digit_count >= 6:
        score += 0.4

    if _looks_like_standard_amount(normalized_text):
        score += 2.0
    elif "," in normalized_text:
        score += 0.5

    if _has_currency_marker(raw_text) or _has_currency_marker(normalized_text):
        score += 2.2

    if attempt_has_total_hint:
        score += 4.0

    if attempt_has_currency_marker:
        score += 0.8

    if attempt_has_negative_hint:
        score -= 0.8

    if amount_value < 100 and attempt_has_total_hint:
        score -= 1.2

    if amount_value < 1000 and attempt_has_total_hint and digit_count < 4:
        score -= 1.0

    if amount_value >= 1000 and amount_value < 10000:
        score += 0.5

    return {
        "text": raw_text,
        "normalized_text": normalized_text,
        "amount_value": int(amount_value),
        "amount_display": _format_amount_display(int(amount_value)),
        "confidence": float(confidence),
        "score": float(score),
        "mode": attempt_mode,
        "preprocess": preprocess,
        "bbox": [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))],
        "x_center": float(x_center),
        "y_center": float(y_center),
        "digit_count": digit_count,
    }


def _collect_candidates_from_text(
    *,
    text: Any,
    confidence: float,
    attempt_mode: str,
    preprocess: str,
    bbox: Sequence[Any],
    attempt_width: int,
    attempt_height: int,
    attempt_has_total_hint: bool,
    attempt_has_currency_marker: bool,
    attempt_has_negative_hint: bool,
) -> List[Dict[str, Any]]:
    # 1 つの OCR テキストから金額候補を集める
    normalized_text = _normalize_amount_text(text)
    if not normalized_text:
        return []

    compact_text = normalized_text.replace(" ", "")
    candidates: List[Dict[str, Any]] = []

    if _looks_like_standard_amount(compact_text):
        for match in AMOUNT_GROUP_PATTERN.finditer(compact_text):
            candidate_text = match.group(1)
            digits_only = _extract_digits(candidate_text)
            if len(digits_only) >= 2:
                candidates.append(
                    _build_candidate(
                        raw_text=str(text).strip(),
                        normalized_text=candidate_text,
                        amount_value=int(digits_only),
                        confidence=confidence,
                        attempt_mode=attempt_mode,
                        preprocess=preprocess,
                        bbox=bbox,
                        attempt_width=attempt_width,
                        attempt_height=attempt_height,
                        attempt_has_total_hint=attempt_has_total_hint,
                        attempt_has_currency_marker=attempt_has_currency_marker,
                        attempt_has_negative_hint=attempt_has_negative_hint,
                    )
                )

    digit_only_text = _extract_digits(compact_text)
    if len(digit_only_text) >= 2:
        candidates.append(
            _build_candidate(
                raw_text=str(text).strip(),
                normalized_text=compact_text,
                amount_value=int(digit_only_text),
                confidence=confidence,
                attempt_mode=attempt_mode,
                preprocess=preprocess,
                bbox=bbox,
                attempt_width=attempt_width,
                attempt_height=attempt_height,
                attempt_has_total_hint=attempt_has_total_hint,
                attempt_has_currency_marker=attempt_has_currency_marker,
                attempt_has_negative_hint=attempt_has_negative_hint,
            )
        )

    return candidates


def _normalize_attempts(total_field: Mapping[str, Any]) -> List[Dict[str, Any]]:
    # 旧形式と新形式の入力を同じ形へ揃える
    attempts = total_field.get("attempts")
    if attempts:
        normalized_attempts: List[Dict[str, Any]] = []
        for index, attempt in enumerate(_normalize_text_list(attempts)):
            if not isinstance(attempt, Mapping):
                continue
            attempt_texts = attempt.get("texts", attempt.get("ocr_results"))
            normalized_attempts.append(
                {
                    "mode": str(attempt.get("mode", f"attempt_{index}")),
                    "preprocess": str(attempt.get("preprocess", "raw")),
                    "texts": _normalize_text_list(attempt_texts),
                    "ocr_text": _normalize_text(attempt.get("ocr_text", "")),
                    "confidence": float(attempt.get("confidence", 0.0) or 0.0),
                    "width": int(attempt.get("width", 0) or 0),
                    "height": int(attempt.get("height", 0) or 0),
                }
            )
        return normalized_attempts

    texts = _normalize_text_list(total_field.get("texts"))
    return [
        {
            "mode": str(total_field.get("mode", "single")),
            "preprocess": str(total_field.get("preprocess", "raw")),
            "texts": texts,
            "ocr_text": _normalize_text(total_field.get("ocr_text", "")),
            "confidence": float(total_field.get("confidence", 0.0) or 0.0),
            "width": int(total_field.get("width", 0) or 0),
            "height": int(total_field.get("height", 0) or 0),
        }
    ]


def extract_amount(total_field: Mapping[str, Any]) -> Dict[str, Any]:
    # total フィールド内の候補から支払金額を決める
    if not isinstance(total_field, Mapping):
        raise TypeError("total_field must be a mapping")

    attempts = _normalize_attempts(total_field)
    candidates: List[Dict[str, Any]] = []

    for attempt in attempts:
        attempt_texts = attempt.get("texts", [])
        attempt_mode = str(attempt.get("mode", "single"))
        preprocess = str(attempt.get("preprocess", "raw"))
        attempt_confidence = float(attempt.get("confidence", 0.0) or 0.0)
        attempt_width = int(attempt.get("width", 0) or 0)
        attempt_height = int(attempt.get("height", 0) or 0)

        joined_text = " ".join(
            _normalize_text(item.get("text"))
            for item in attempt_texts
            if isinstance(item, Mapping) and _normalize_text(item.get("text"))
        )
        attempt_has_total_hint = _has_total_hint(joined_text)
        attempt_has_currency_marker = _has_currency_marker(joined_text)
        attempt_has_negative_hint = _has_negative_hint(joined_text)

        for item in attempt_texts:
            if not isinstance(item, Mapping):
                continue

            item_text = _normalize_text(item.get("text"))
            if not item_text:
                continue

            item_confidence = item.get("confidence", attempt_confidence)
            try:
                item_confidence_value = float(item_confidence)
            except (TypeError, ValueError):
                item_confidence_value = attempt_confidence

            bbox = item.get("bbox", [0, 0, 0, 0])
            item_candidates = _collect_candidates_from_text(
                text=item_text,
                confidence=item_confidence_value,
                attempt_mode=attempt_mode,
                preprocess=preprocess,
                bbox=bbox,
                attempt_width=attempt_width,
                attempt_height=attempt_height,
                attempt_has_total_hint=attempt_has_total_hint,
                attempt_has_currency_marker=attempt_has_currency_marker,
                attempt_has_negative_hint=attempt_has_negative_hint,
            )
            candidates.extend(item_candidates)

        if joined_text:
            joined_item_candidates = _collect_candidates_from_text(
                text=joined_text,
                confidence=attempt_confidence,
                attempt_mode=attempt_mode,
                preprocess=preprocess,
                bbox=[0, 0, attempt_width, attempt_height],
                attempt_width=attempt_width,
                attempt_height=attempt_height,
                attempt_has_total_hint=attempt_has_total_hint,
                attempt_has_currency_marker=attempt_has_currency_marker,
                attempt_has_negative_hint=attempt_has_negative_hint,
            )
            candidates.extend(joined_item_candidates)

    if not candidates:
        raise ValueError("Amount could not be extracted from the total field.")

    deduped_candidates: Dict[Tuple[int, str, str, str], Dict[str, Any]] = {}
    for candidate in candidates:
        key = (
            int(candidate["amount_value"]),
            str(candidate["normalized_text"]),
            str(candidate["mode"]),
            str(candidate["preprocess"]),
        )
        current = deduped_candidates.get(key)
        if current is None or float(candidate["score"]) > float(current["score"]):
            deduped_candidates[key] = candidate

    ordered_candidates = sorted(
        deduped_candidates.values(),
        key=lambda item: (
            float(item["score"]),
            int(item["amount_value"]),
            float(item["confidence"]),
        ),
        reverse=True,
    )

    selected_candidate = ordered_candidates[0]
    amount_value = int(selected_candidate["amount_value"])
    amount_display = _format_amount_display(amount_value)

    return {
        "amount": amount_value,
        "amount_value": amount_value,
        "amount_display": amount_display,
        "selected_candidate": selected_candidate,
        "candidates": ordered_candidates,
    }


def parse_amount(total_field: Mapping[str, Any]) -> Dict[str, Any]:
    # extract_amount() の別名として提供する
    return extract_amount(total_field)


if __name__ == "__main__":
    # 動作確認用のサンプルを出力する
    sample_total_field = {
        "field": "total",
        "attempts": [
            {
                "mode": "wide",
                "preprocess": "gray",
                "confidence": 0.99,
                "texts": [
                    {"text": "合計", "confidence": 0.99, "bbox": [0, 0, 0, 0]},
                    {"text": "キ2,フロ6", "confidence": 0.05, "bbox": [100, 0, 200, 40]},
                ],
            }
        ],
    }

    print(json.dumps(extract_amount(sample_total_field), ensure_ascii=False, indent=2))
