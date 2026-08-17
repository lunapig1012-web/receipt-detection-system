"""YOLO検出結果とOCR結果の対応を確認する簡易テスト。"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def configure_stdout() -> None:
    # Windows環境で日本語をそのまま表示できるようにする
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    # テスト用の画像とモデルを準備する
    configure_stdout()

    project_root = Path(__file__).resolve().parents[1]
    image_path = project_root / "data" / "receipts" / "test_receipt.jpg"
    model_path = project_root / "models" / "best.pt"

    if not image_path.exists():
        raise FileNotFoundError(f"Test image not found: {image_path}")

    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    # プロジェクト直下のモジュールを直接参照できるようにする
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from detection.yolo_detector import YOLODetector
    from ocr.easyocr_service import EasyOCRService
    from utils.coordinate_matcher import match_yolo_and_ocr

    print(f"Image path: {image_path}")

    detector = YOLODetector(model_path=model_path, conf_threshold=0.25)
    ocr_service = EasyOCRService()

    print("Running YOLO detection...")
    yolo_results = detector.detect(image_path=image_path)
    print(f"YOLO detections: {len(yolo_results)}")
    print(json.dumps(yolo_results, ensure_ascii=False, indent=2))

    print("Running OCR...")
    ocr_results = ocr_service.ocr_image(image_path=image_path)
    print(f"OCR results: {len(ocr_results)}")
    print(json.dumps(ocr_results, ensure_ascii=False, indent=2))

    print("Running coordinate matching...")
    matched_results = match_yolo_and_ocr(yolo_results, ocr_results)
    print(f"Matched fields: {len(matched_results)}")
    print(json.dumps(matched_results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
