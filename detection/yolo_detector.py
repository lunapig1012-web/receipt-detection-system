"""deploy_config.json を読み込み、YOLO11n の検出設定を共通化するモジュール。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from PIL import Image
from ultralytics import YOLO

DetectionResult = Dict[str, Any]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEPLOY_CONFIG_PATH = PROJECT_ROOT / "deploy_config.json"
DEFAULT_MODEL_PATH_FALLBACK = PROJECT_ROOT / "models" / "best.pt"
DEFAULT_IMGSZ_FALLBACK = 1024
DEFAULT_CONF_THRESHOLD_FALLBACK = 0.5
DEFAULT_CLASS_NAMES_FALLBACK = {0: "date", 1: "phone", 2: "total"}


def _resolve_path(value: Union[str, Path], base_dir: Path) -> Path:
    # 相対パスは project root 基準で解決する
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _normalize_class_names(names: Any) -> Dict[int, str]:
    # model.names や deploy_config.json の classes を共通形式にそろえる
    if isinstance(names, dict):
        normalized: Dict[int, str] = {}
        for key, value in names.items():
            try:
                normalized[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        return normalized

    if isinstance(names, list):
        return {index: str(name) for index, name in enumerate(names)}

    return {}


def _validate_conf_threshold(value: Any, fallback: float) -> float:
    # confidence threshold を 0.0 - 1.0 の範囲に制限する
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        return fallback

    if not 0.0 <= threshold <= 1.0:
        return fallback
    return threshold


def _validate_imgsz(value: Any, fallback: int) -> int:
    # 推論サイズは正の整数のみ受け付ける
    try:
        imgsz = int(value)
    except (TypeError, ValueError):
        return fallback

    if imgsz <= 0:
        return fallback
    return imgsz


def load_deploy_config(config_path: Union[str, Path, None] = None) -> Dict[str, Any]:
    # deploy_config.json を読み込み、使いやすい形式に整える
    config_file = Path(config_path) if config_path is not None else DEFAULT_DEPLOY_CONFIG_PATH
    base_config: Dict[str, Any] = {
        "config_path": config_file,
        "model_path": DEFAULT_MODEL_PATH_FALLBACK,
        "imgsz": DEFAULT_IMGSZ_FALLBACK,
        "conf_threshold": DEFAULT_CONF_THRESHOLD_FALLBACK,
        "classes": dict(DEFAULT_CLASS_NAMES_FALLBACK),
    }

    if not config_file.exists():
        return base_config

    try:
        raw_data = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base_config

    if not isinstance(raw_data, dict):
        return base_config

    config_dir = config_file.parent

    model_path_value = raw_data.get("model_path", base_config["model_path"])
    if model_path_value is not None:
        base_config["model_path"] = _resolve_path(model_path_value, config_dir)

    base_config["imgsz"] = _validate_imgsz(raw_data.get("imgsz"), DEFAULT_IMGSZ_FALLBACK)
    base_config["conf_threshold"] = _validate_conf_threshold(
        raw_data.get("conf_threshold"),
        DEFAULT_CONF_THRESHOLD_FALLBACK,
    )

    classes = _normalize_class_names(raw_data.get("classes"))
    if classes:
        base_config["classes"] = classes

    return base_config


DEPLOY_CONFIG = load_deploy_config()
DEFAULT_MODEL_PATH = Path(DEPLOY_CONFIG["model_path"])
DEFAULT_IMGSZ = int(DEPLOY_CONFIG["imgsz"])
DEFAULT_CONF_THRESHOLD = float(DEPLOY_CONFIG["conf_threshold"])
DEFAULT_CLASS_NAMES = dict(DEPLOY_CONFIG["classes"])


class YOLODetector:
    """レシート画像から date / phone / total を検出する。"""

    def __init__(
        self,
        model_path: Union[str, Path] = DEFAULT_MODEL_PATH,
        conf_threshold: float = DEFAULT_CONF_THRESHOLD,
        imgsz: int = DEFAULT_IMGSZ,
    ) -> None:
        # モデルの存在を確認してから読み込む
        self.model_path = _resolve_path(model_path, PROJECT_ROOT)
        if not self.model_path.exists():
            raise FileNotFoundError(f"YOLO model file not found: {self.model_path}")

        self.conf_threshold = self._validate_conf_threshold(conf_threshold)
        self.default_imgsz = self._validate_imgsz(imgsz)
        self.model = YOLO(str(self.model_path))

        # deploy_config.json の class 定義を優先し、なければモデル側定義を使う
        self.class_names = self._normalize_class_names(DEFAULT_CLASS_NAMES or self.model.names)

    @staticmethod
    def _validate_conf_threshold(conf_threshold: float) -> float:
        # confidence threshold は 0.0 から 1.0 の範囲に制限する
        if not 0.0 <= float(conf_threshold) <= 1.0:
            raise ValueError("conf_threshold must be between 0.0 and 1.0")
        return float(conf_threshold)

    @staticmethod
    def _validate_imgsz(imgsz: int) -> int:
        # 推論サイズは正の整数に限定する
        value = int(imgsz)
        if value <= 0:
            raise ValueError("imgsz must be a positive integer")
        return value

    @staticmethod
    def _normalize_class_names(names: Any) -> Dict[int, str]:
        # class 名を辞書形式にそろえる
        if isinstance(names, dict):
            normalized: Dict[int, str] = {}
            for key, value in names.items():
                try:
                    normalized[int(key)] = str(value)
                except (TypeError, ValueError):
                    continue
            return normalized

        if isinstance(names, list):
            return {index: str(name) for index, name in enumerate(names)}

        return {}

    def _resolve_class_name(self, class_id: int) -> str:
        # class ID から class 名へ変換する
        return self.class_names.get(class_id, f"class_{class_id}")

    @staticmethod
    def _build_annotated_image_path(
        image_path: Path,
        annotated_image_path: Optional[Union[str, Path]],
    ) -> Path:
        # 保存先が未指定なら入力画像名から検出画像の保存先を作る
        if annotated_image_path is not None:
            output_path = Path(annotated_image_path)
            if not output_path.suffix:
                output_path = output_path.with_suffix(".jpg")
            return output_path

        suffix = image_path.suffix if image_path.suffix else ".jpg"
        return image_path.with_name(f"{image_path.stem}_annotated{suffix}")

    def detect(
        self,
        image_path: Union[str, Path],
        save_annotated: bool = False,
        annotated_image_path: Optional[Union[str, Path]] = None,
        imgsz: Optional[int] = None,
    ) -> List[DetectionResult]:
        # 画像を読み込み、YOLO11n 推論を実行する
        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"Image file not found: {image_file}")

        inference_imgsz = self.default_imgsz if imgsz is None else self._validate_imgsz(imgsz)

        results = self.model.predict(
            source=str(image_file),
            imgsz=inference_imgsz,
            conf=self.conf_threshold,
            verbose=False,
        )

        if not results:
            return []

        result = results[0]
        detections: List[DetectionResult] = []

        boxes = getattr(result, "boxes", None)
        if boxes is not None and len(boxes) > 0:
            # YOLO の出力を扱いやすい辞書形式へ変換する
            for row in boxes.data.cpu().tolist():
                if len(row) < 6:
                    continue

                x1, y1, x2, y2, confidence, class_id = row[:6]
                if confidence < self.conf_threshold:
                    continue

                detections.append(
                    {
                        "class_name": self._resolve_class_name(int(class_id)),
                        "confidence": float(confidence),
                        "bbox": [float(x1), float(y1), float(x2), float(y2)],
                    }
                )

        if save_annotated:
            # 可視化用の画像を保存する
            output_path = self._build_annotated_image_path(image_file, annotated_image_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            annotated_image = result.plot()
            Image.fromarray(annotated_image[:, :, ::-1]).save(output_path)

        return detections

    def predict(
        self,
        image_path: Union[str, Path],
        save_annotated: bool = False,
        annotated_image_path: Optional[Union[str, Path]] = None,
        imgsz: Optional[int] = None,
    ) -> List[DetectionResult]:
        # detect() の別名として扱う
        return self.detect(
            image_path=image_path,
            save_annotated=save_annotated,
            annotated_image_path=annotated_image_path,
            imgsz=imgsz,
        )

    def get_class_names(self) -> List[str]:
        # モデルに登録されている class 名を順番に返す
        return [self.class_names[index] for index in sorted(self.class_names.keys())]


def detect_receipt_fields(
    image_path: Union[str, Path],
    model_path: Union[str, Path] = DEFAULT_MODEL_PATH,
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
    save_annotated: bool = False,
    annotated_image_path: Optional[Union[str, Path]] = None,
    imgsz: int = DEFAULT_IMGSZ,
) -> List[DetectionResult]:
    # 1 回だけ使う場合の簡易ヘルパー
    detector = YOLODetector(
        model_path=model_path,
        conf_threshold=conf_threshold,
        imgsz=imgsz,
    )
    return detector.detect(
        image_path=image_path,
        save_annotated=save_annotated,
        annotated_image_path=annotated_image_path,
        imgsz=imgsz,
    )
