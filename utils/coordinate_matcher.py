# YOLO検出領域とOCRテキスト領域を座標ベースで対応付けるモジュール
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

BBox = List[int]
YOLODetection = Mapping[str, Any]
OCRResult = Mapping[str, Any]
MatchedText = Dict[str, Any]
MatchedField = Dict[str, Any]


class CoordinateMatcher:
    # OCRテキストの中心点がYOLO領域内に入るものを対応付ける

    def __init__(
        self,
        match_margin_ratio: float = 0.0,
        include_empty_fields: bool = True,
    ) -> None:
        # マッチ判定を少し広げたい場合に備えて、領域の外側へ余白を付ける
        self.match_margin_ratio = self._validate_match_margin_ratio(match_margin_ratio)
        self.include_empty_fields = bool(include_empty_fields)

    @staticmethod
    def _validate_match_margin_ratio(match_margin_ratio: float) -> float:
        # 余白比率は0以上のみ許可する
        if match_margin_ratio < 0.0:
            raise ValueError("match_margin_ratio must be greater than or equal to 0.0")
        return float(match_margin_ratio)

    @staticmethod
    def _normalize_bbox(bbox: Any) -> BBox:
        # どの入力形式でも [x1, y1, x2, y2] に整える
        if bbox is None:
            raise ValueError("bbox is required")

        if hasattr(bbox, "tolist"):
            bbox = bbox.tolist()

        if isinstance(bbox, dict):
            bbox = list(bbox.values())

        if not isinstance(bbox, list):
            bbox = list(bbox)

        if len(bbox) == 4 and all(isinstance(value, (int, float)) for value in bbox):
            x1, y1, x2, y2 = bbox
            left = min(float(x1), float(x2))
            top = min(float(y1), float(y2))
            right = max(float(x1), float(x2))
            bottom = max(float(y1), float(y2))
            return [
                int(round(left)),
                int(round(top)),
                int(round(right)),
                int(round(bottom)),
            ]

        points: List[Tuple[float, float]] = []
        for point in bbox:
            if hasattr(point, "tolist"):
                point = point.tolist()

            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append((float(point[0]), float(point[1])))

        if not points:
            raise ValueError("Invalid bbox format")

        x_values = [point[0] for point in points]
        y_values = [point[1] for point in points]
        return [
            int(round(min(x_values))),
            int(round(min(y_values))),
            int(round(max(x_values))),
            int(round(max(y_values))),
        ]

    @staticmethod
    def _get_bbox_center(bbox: Sequence[int]) -> Tuple[float, float]:
        # bboxの中心点を求める
        x1, y1, x2, y2 = bbox
        center_x = (float(x1) + float(x2)) / 2.0
        center_y = (float(y1) + float(y2)) / 2.0
        return center_x, center_y

    def _expand_bbox(self, bbox: Sequence[int]) -> Tuple[float, float, float, float]:
        # 必要に応じてYOLO領域を少し広げる
        x1, y1, x2, y2 = [float(value) for value in bbox]
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        margin_x = width * self.match_margin_ratio
        margin_y = height * self.match_margin_ratio
        return x1 - margin_x, y1 - margin_y, x2 + margin_x, y2 + margin_y

    @staticmethod
    def _point_inside_bbox(point: Tuple[float, float], bbox: Sequence[float]) -> bool:
        # 中心点がbboxの内側または境界上にあるかを判定する
        x, y = point
        x1, y1, x2, y2 = bbox
        return x1 <= x <= x2 and y1 <= y <= y2

    def _normalize_ocr_item(self, ocr_item: OCRResult) -> Optional[MatchedText]:
        # OCR結果を後続処理で使いやすい形に整える
        if not isinstance(ocr_item, Mapping):
            return None

        bbox = ocr_item.get("bbox")
        if bbox is None:
            return None

        try:
            normalized_bbox = self._normalize_bbox(bbox)
        except (TypeError, ValueError):
            return None

        text = ocr_item.get("text")
        confidence = ocr_item.get("confidence")

        return {
            "text": "" if text is None else str(text),
            "confidence": float(confidence) if confidence is not None else 0.0,
            "bbox": normalized_bbox,
        }

    def match(
        self,
        yolo_detections: Sequence[YOLODetection],
        ocr_results: Sequence[OCRResult],
    ) -> List[MatchedField]:
        # YOLO検出領域ごとにOCR文字列をまとめる
        normalized_ocr_results: List[MatchedText] = []
        for ocr_item in ocr_results:
            normalized_item = self._normalize_ocr_item(ocr_item)
            if normalized_item is not None:
                normalized_ocr_results.append(normalized_item)

        matched_fields: List[MatchedField] = []

        for detection in yolo_detections:
            if not isinstance(detection, Mapping):
                continue

            class_name = detection.get("class_name")
            bbox = detection.get("bbox")
            if class_name is None or bbox is None:
                continue

            try:
                normalized_bbox = self._normalize_bbox(bbox)
            except (TypeError, ValueError):
                continue

            expanded_bbox = self._expand_bbox(normalized_bbox)
            matched_texts: List[MatchedText] = []

            for ocr_item in normalized_ocr_results:
                center_point = self._get_bbox_center(ocr_item["bbox"])
                if self._point_inside_bbox(center_point, expanded_bbox):
                    matched_texts.append(dict(ocr_item))

            if matched_texts or self.include_empty_fields:
                matched_fields.append(
                    {
                        "field": str(class_name),
                        "texts": matched_texts,
                    }
                )

        return matched_fields

    def match_one(
        self,
        yolo_detection: YOLODetection,
        ocr_results: Sequence[OCRResult],
    ) -> MatchedField:
        # 単一のYOLO検出領域だけを確認したい場合の補助メソッド
        matched_fields = self.match([yolo_detection], ocr_results)
        if matched_fields:
            return matched_fields[0]
        return {"field": "", "texts": []}


def match_yolo_and_ocr(
    yolo_detections: Sequence[YOLODetection],
    ocr_results: Sequence[OCRResult],
    match_margin_ratio: float = 0.0,
    include_empty_fields: bool = True,
) -> List[MatchedField]:
    # 短く呼び出したい場合の便利関数
    matcher = CoordinateMatcher(
        match_margin_ratio=match_margin_ratio,
        include_empty_fields=include_empty_fields,
    )
    return matcher.match(yolo_detections, ocr_results)
