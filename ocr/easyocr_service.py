"""EasyOCR を共通インターフェースで扱うサービス。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EASYOCR_CACHE_DIR = PROJECT_ROOT / ".cache" / "easyocr"
EASYOCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

try:
    from easyocr import Reader
except ImportError as import_error:  # pragma: no cover - import guard
    Reader = None
    EASYOCR_IMPORT_ERROR = import_error

OCRResult = Dict[str, Any]
ImageInput = Union[str, Path, Image.Image, np.ndarray]

__all__ = ["EasyOCRService"]


class EasyOCRService:
    # 日本語と英語を同時に読む
    def __init__(
        self,
        lang: Union[str, Sequence[str]] = ("ja", "en"),
        gpu: bool = False,
        model_storage_directory: Optional[Union[str, Path]] = None,
    ) -> None:
        # Windows では CPU 実行を既定にする
        if Reader is None:
            raise ImportError(
                "easyocr is not installed. Install `easyocr` before running the OCR pipeline."
            ) from EASYOCR_IMPORT_ERROR

        if isinstance(lang, str):
            self.languages = [lang]
        else:
            self.languages = [str(item) for item in lang if str(item).strip()]

        if not self.languages:
            self.languages = ["ja", "en"]

        self.gpu = gpu
        self.model_storage_directory = (
            Path(model_storage_directory) if model_storage_directory else EASYOCR_CACHE_DIR
        )
        self.model_storage_directory.mkdir(parents=True, exist_ok=True)
        self._reader = self._create_reader()

    def _create_reader(self) -> Any:
        # モデルはローカルキャッシュを再利用する
        return Reader(
            self.languages,
            gpu=self.gpu,
            model_storage_directory=str(self.model_storage_directory),
            download_enabled=True,
        )

    @staticmethod
    def _load_image_array(image_input: ImageInput) -> np.ndarray:
        # 入力を numpy 配列に統一する
        if isinstance(image_input, np.ndarray):
            image_array = np.asarray(image_input)
        elif isinstance(image_input, (str, Path)):
            with Image.open(image_input) as image:
                image_array = np.array(image.convert("RGB"))
        elif isinstance(image_input, Image.Image):
            image_array = np.array(image_input.convert("RGB"))
        else:
            raise TypeError("image_input must be a path, PIL image, or numpy array")

        if image_array.ndim == 2:
            return np.ascontiguousarray(image_array)

        if image_array.ndim == 3 and image_array.shape[2] >= 3:
            return np.ascontiguousarray(image_array[:, :, :3])

        raise ValueError("Invalid image input shape.")

    @staticmethod
    def _normalize_bbox(box: Any) -> List[int]:
        # OCR の座標を [x1, y1, x2, y2] に統一する
        if hasattr(box, "tolist"):
            box = box.tolist()

        if isinstance(box, dict):
            box = list(box.values())

        if not isinstance(box, list):
            box = list(box)

        if len(box) == 4 and all(isinstance(value, (int, float)) for value in box):
            x1, y1, x2, y2 = box
            return [
                int(round(min(float(x1), float(x2)))),
                int(round(min(float(y1), float(y2)))),
                int(round(max(float(x1), float(x2)))),
                int(round(max(float(y1), float(y2)))),
            ]

        points: List[tuple[float, float]] = []
        for point in box:
            if hasattr(point, "tolist"):
                point = point.tolist()

            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append((float(point[0]), float(point[1])))

        if not points:
            raise ValueError("Invalid OCR bounding box format.")

        x_values = [point[0] for point in points]
        y_values = [point[1] for point in points]
        return [
            int(round(min(x_values))),
            int(round(min(y_values))),
            int(round(max(x_values))),
            int(round(max(y_values))),
        ]

    def ocr_image(
        self,
        image_input: ImageInput,
        allowlist: Optional[str] = None,
        **readtext_kwargs: Any,
    ) -> List[OCRResult]:
        # 画像全体でも ROI でも同じ形式で OCR する
        image_array = self._load_image_array(image_input)
        options: Dict[str, Any] = {"detail": 1, "paragraph": False}
        if allowlist:
            options["allowlist"] = allowlist
        options.update(readtext_kwargs)

        prediction_results = self._reader.readtext(image_array, **options)
        if not prediction_results:
            return []

        return self._standardize_predictions(prediction_results)

    def _standardize_predictions(self, prediction_results: Any) -> List[OCRResult]:
        # EasyOCR の出力を共通フォーマットへ変換する
        results: List[OCRResult] = []
        for prediction in prediction_results:
            if not isinstance(prediction, (list, tuple)) or len(prediction) < 3:
                continue

            bbox, text, confidence = prediction[:3]
            text_value = "" if text is None else str(text).strip()
            if not text_value:
                continue

            try:
                confidence_value = float(confidence)
            except (TypeError, ValueError):
                confidence_value = 0.0

            results.append(
                {
                    "text": text_value,
                    "confidence": confidence_value,
                    "bbox": self._normalize_bbox(bbox),
                }
            )

        return results
