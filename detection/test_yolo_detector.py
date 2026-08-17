"""YOLO 検出器のローカル検証スクリプト。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

# プロジェクト直下からモジュールを読み込めるようにする
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from yolo_detector import (  # noqa: E402
    DEFAULT_CLASS_NAMES,
    DEFAULT_CONF_THRESHOLD,
    DEFAULT_DEPLOY_CONFIG_PATH,
    DEFAULT_IMGSZ,
    DEFAULT_MODEL_PATH,
    DetectionResult,
    YOLODetector,
)

DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "detection" / "test_receipt_detected.jpg"
EXPECTED_CLASSES = tuple(DEFAULT_CLASS_NAMES.values())


def _check_path(path: Path, label: str) -> None:
    # 入力ファイルの存在を確認する
    if not path.exists():
        print(f"[ERROR] {label} が見つかりません: {path}", file=sys.stderr)
        sys.exit(2)


def _group_by_class(detections: List[DetectionResult]) -> Dict[str, List[DetectionResult]]:
    # class ごとに検出結果をまとめる
    groups: Dict[str, List[DetectionResult]] = {name: [] for name in EXPECTED_CLASSES}
    for detection in detections:
        class_name = str(detection.get("class_name", "unknown"))
        groups.setdefault(class_name, []).append(detection)
    return groups


def _print_summary(detections: List[DetectionResult], elapsed_ms: float, conf_threshold: float, imgsz: int) -> bool:
    # 検出結果を見やすく表示する
    groups = _group_by_class(detections)

    print(f"\n[INFO] deploy_config: {DEFAULT_DEPLOY_CONFIG_PATH}")
    print(f"[INFO] 推論時間: {elapsed_ms:.1f} ms")
    print(f"[INFO] conf_threshold: {conf_threshold:.2f}")
    print(f"[INFO] imgsz: {imgsz}")
    print("[INFO] 検出サマリー:")

    all_found = True
    for class_name in EXPECTED_CLASSES:
        items = groups.get(class_name, [])
        if items:
            conf_values = ", ".join(f"{float(item['confidence']):.3f}" for item in items)
            print(f"  - {class_name}: {len(items)} 件 / confidence = {conf_values}")
        else:
            print(f"  - {class_name}: 0 件")
            all_found = False

    return all_found


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YOLO 検出器のローカル検証")
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL_PATH,
        help="YOLO weights のパス",
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=PROJECT_ROOT / "data" / "receipts" / "test_receipt.jpg",
        help="検証対象の画像パス",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="注釈付き画像の保存先",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=DEFAULT_CONF_THRESHOLD,
        help="confidence threshold",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        choices=[640, 1024, 1280],
        default=DEFAULT_IMGSZ,
        help="推論時の画像サイズ",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="注釈付き画像を保存しない",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    _check_path(args.model, "モデルファイル")
    _check_path(args.image, "テスト画像")

    print(f"[INFO] モデル: {args.model}")
    print(f"[INFO] 画像: {args.image}")

    detector = YOLODetector(model_path=args.model, conf_threshold=args.conf, imgsz=args.imgsz)
    loaded_classes = detector.get_class_names()
    print(f"[INFO] class_names: {loaded_classes}")

    save_annotated = not args.no_save
    annotated_path: Path | None = args.output if save_annotated else None
    if save_annotated:
        args.output.parent.mkdir(parents=True, exist_ok=True)

    start_time = time.perf_counter()
    detections = detector.detect(
        image_path=args.image,
        save_annotated=save_annotated,
        annotated_image_path=annotated_path,
        imgsz=args.imgsz,
    )
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    all_found = _print_summary(detections, elapsed_ms, args.conf, args.imgsz)

    print("\n[INFO] 検出結果 JSON:")
    print(json.dumps(detections, ensure_ascii=False, indent=2))

    if save_annotated and annotated_path is not None:
        if annotated_path.exists():
            print(f"\n[INFO] 注釈付き画像を保存しました: {annotated_path}")
        else:
            print(f"\n[WARN] 注釈付き画像が見つかりません: {annotated_path}", file=sys.stderr)

    sys.exit(0 if all_found else 1)


if __name__ == "__main__":
    main()
