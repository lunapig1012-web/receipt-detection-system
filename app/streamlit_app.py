"""レシート画像をアップロードし、解析結果を確認して表計算ファイルへ出力する画面。"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    # プロジェクト直下のモジュールを参照できるようにする
    sys.path.insert(0, str(PROJECT_ROOT))

from app.receipt_pipeline import process_receipt_image
from utils.excel_export import DEFAULT_OUTPUT_FILENAME, export_to_excel

APP_TITLE = "レシートAI精算システム"
UPLOAD_TYPES = ["jpg", "jpeg", "png"]
TEMP_UPLOAD_DIR = Path(tempfile.gettempdir()) / "receipt_detection_system_uploads"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "excel" / DEFAULT_OUTPUT_FILENAME


def initialize_session_state() -> None:
    # 画面遷移と入力内容を保持する
    defaults = {
        "current_step": 1,
        "current_file_hash": "",
        "current_image_path": "",
        "analysis_result": {},
        "merchant_name": "",
        "tax_rate": 10,
        "last_export_path": "",
    }

    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def get_file_hash(uploaded_file: Any) -> str:
    # アップロード画像の重複判定に使う
    return hashlib.sha256(uploaded_file.getvalue()).hexdigest()


def save_uploaded_file(uploaded_file: Any, file_hash: str) -> Path:
    # 一時フォルダに画像を保存する
    TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    suffix = Path(uploaded_file.name).suffix.lower()
    if not suffix:
        suffix = ".jpg"

    target_path = TEMP_UPLOAD_DIR / f"{file_hash}{suffix}"
    if not target_path.exists():
        target_path.write_bytes(uploaded_file.getvalue())

    return target_path


@st.cache_data(show_spinner=False)
def run_ai_processing(image_path: str) -> Dict[str, Any]:
    # パイプラインの結果だけを返す
    return process_receipt_image(image_path)


def to_int_or_zero(value: Any) -> int:
    # 数値に変換できない場合は 0 を返す
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def format_yen_symbol(value: Any) -> str:
    # 金額を「¥1,000」の形式で表示する
    return f"¥{to_int_or_zero(value):,}"


def format_yen_suffix(value: Any) -> str:
    # 金額を「1,000円」の形式で表示する
    return f"{to_int_or_zero(value):,}円"


def format_tax_display(value: Any) -> str:
    # 税額を合計金額と同じ表示形式で表す
    return f"¥{to_int_or_zero(value)}"


def get_step_icon_svg(step_index: int) -> str:
    # ステッパー用のアイコンをSVGで返す
    icons = {
        1: """
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M7 17a4 4 0 0 1 .5-7.97A5.5 5.5 0 0 1 18.5 11H19a3 3 0 0 1 0 6H7z"></path>
                <path d="M12 15V8"></path>
                <path d="M8.8 11.2 12 8l3.2 3.2"></path>
            </svg>
        """,
        2: """
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M7 4h7l4 4v12H7z"></path>
                <path d="M14 4v5h5"></path>
                <path d="M9 13h6"></path>
                <path d="M9 16h6"></path>
            </svg>
        """,
        3: """
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M4 20l4.5-1 9.5-9.5-3.5-3.5L5 15.5z"></path>
                <path d="M14.5 6.5 18 10"></path>
                <path d="M12.5 8.5 16 12"></path>
            </svg>
        """,
        4: """
            <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <rect x="4" y="5" width="16" height="14" rx="2"></rect>
                <path d="M4 10h16"></path>
                <path d="M4 15h16"></path>
                <path d="M9 5v14"></path>
                <path d="M15 5v14"></path>
            </svg>
        """,
    }
    return " ".join(icons.get(step_index, "").split())


def get_amount_value(analysis_result: Dict[str, Any]) -> int:
    # 合計金額の内部数値を優先して取得する
    return to_int_or_zero(analysis_result.get("amount_value", analysis_result.get("amount")))


def get_amount_display(analysis_result: Dict[str, Any]) -> str:
    # 画面表示用の金額文字列を取得する
    amount_display = str(analysis_result.get("amount_display", "")).strip()
    if amount_display:
        return amount_display
    return format_yen_symbol(get_amount_value(analysis_result))


def normalize_display_text(value: Any) -> str:
    # 認識結果由来の余分な空白を取り除く
    return str(value or "").replace(" ", "").strip()


def calculate_tax_amount(total_amount: int, tax_rate: int) -> int:
    # 税込金額から消費税額を計算する
    if total_amount <= 0 or tax_rate <= 0:
        return 0
    return int(total_amount * tax_rate / (100 + tax_rate))


def apply_page_style() -> None:
    # 白基調のカード型レイアウトに整える
    st.markdown(
        """
        <style>
            .stApp {
                background: #ffffff;
                color: #111827;
                font-family: "Hiragino Sans", "Yu Gothic UI", "Yu Gothic", sans-serif;
            }

            .block-container {
                max-width: 1060px;
                padding-top: 0.45rem;
                padding-bottom: 1.0rem;
            }

            #MainMenu,
            footer,
            header {
                visibility: hidden;
            }

            .page-title {
                font-size: 1.14rem;
                font-weight: 700;
                color: #111827;
                line-height: 1.2;
                margin-bottom: 0.28rem;
            }

            .page-subtitle {
                display: none;
            }

            .stepper-card {
                margin-top: 0.15rem;
                padding: 0.8rem 0.95rem 0.95rem;
                border-radius: 18px;
                border: 1px solid #e5e7eb;
                background: #ffffff;
            }

            .stepper {
                display: flex;
                gap: 0;
                justify-content: space-between;
                align-items: flex-start;
                padding: 0.15rem 0 0.25rem;
            }

            .step-item {
                flex: 1;
                position: relative;
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
                min-height: 78px;
            }

            .step-item:not(:last-child)::after {
                content: "";
                position: absolute;
                top: 20px;
                left: calc(50% + 21px);
                right: calc(-50% + 21px);
                height: 1.5px;
                background: #d7dbe2;
                z-index: 0;
            }

            .step-item.done:not(:last-child)::after {
                background: #9db7ff;
            }

            .step-circle {
                width: 42px;
                height: 42px;
                border-radius: 999px;
                display: flex;
                align-items: center;
                justify-content: center;
                border: 1px solid #d1d5db;
                background: #ffffff;
                color: #6b7280;
                font-size: 0.98rem;
                position: relative;
                z-index: 1;
                box-shadow: none;
            }

            .step-circle svg {
                width: 18px;
                height: 18px;
                stroke: currentColor;
                stroke-width: 1.8;
                stroke-linecap: round;
                stroke-linejoin: round;
                fill: none;
            }

            .step-item.active .step-circle,
            .step-item.done .step-circle {
                background: linear-gradient(180deg, #8aa8f7 0%, #5f84e8 100%);
                border-color: #5f84e8;
                color: #ffffff;
            }

            .step-label {
                margin-top: 0.4rem;
                font-size: 0.72rem;
                font-weight: 700;
                color: #111827;
                line-height: 1.2;
            }

            .step-item.inactive .step-label {
                color: #6b7280;
            }

            .panel-title {
                font-size: 0.9rem;
                font-weight: 700;
                color: #111827;
                margin-bottom: 0.2rem;
            }

            .panel-text {
                color: #6b7280;
                font-size: 0.78rem;
                line-height: 1.5;
                margin-bottom: 0.6rem;
            }

            .upload-hint {
                padding: 0.7rem 0.85rem;
                border-radius: 12px;
                border: 1px solid #e8ebf0;
                background: #fafafa;
                color: #4b5563;
                font-size: 0.78rem;
                margin-bottom: 0.55rem;
                text-align: center;
            }

            .readonly-field {
                padding: 0.78rem 0;
                border-bottom: 1px solid #edf0f3;
            }

            .readonly-field:last-child {
                border-bottom: none;
            }

            .readonly-label {
                font-size: 0.78rem;
                color: #6b7280;
                margin-bottom: 0.25rem;
                letter-spacing: 0.01em;
            }

            .readonly-value {
                font-size: 1.1rem;
                font-weight: 800;
                color: #111827;
                line-height: 1.2;
            }

            .readonly-value.emphasis {
                font-size: 1.28rem;
                color: #0f172a;
            }

            .preview-box {
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 390px;
                background: #fbfbfc;
                border: 1px dashed #d6dbe3;
                border-radius: 18px;
                color: #6b7280;
                text-align: center;
                padding: 1rem;
            }

            .preview-box .preview-icon {
                font-size: 2.45rem;
                margin-bottom: 0.5rem;
            }

            .preview-box .preview-title {
                font-size: 0.92rem;
                font-weight: 700;
                color: #111827;
                margin-bottom: 0.25rem;
            }

            .preview-box .preview-subtitle {
                font-size: 0.8rem;
                color: #6b7280;
            }

            div[data-testid="stVerticalBlockBorderWrapper"] {
                border: 1px solid #e6e8ec;
                border-radius: 18px;
                background: #ffffff;
                box-shadow: none;
                padding: 0.95rem 0.95rem 0.9rem 0.95rem;
            }

            div[data-testid="stButton"] > button {
                border-radius: 12px;
                padding: 0.62rem 1.2rem;
                font-weight: 700;
                border: 1px solid #111827;
                background: #111827;
                color: #ffffff;
                transition: all 0.2s ease;
            }

            div[data-testid="stButton"] > button:hover {
                transform: translateY(-1px);
                box-shadow: 0 10px 24px rgba(17, 24, 39, 0.16);
                border-color: #000000;
            }

            div[data-testid="stButton"] > button[kind="secondary"] {
                background: #ffffff;
                color: #111827;
                border: 1px solid #d1d5db;
            }

            div[data-testid="stButton"] > button[kind="secondary"]:hover {
                background: #f9fafb;
                border-color: #cbd5e1;
            }

            div[data-testid="stFileUploader"] {
                border-radius: 16px;
            }

            div[data-testid="stFileUploaderDropzone"] {
                border: 1px dashed #d4d9e1;
                border-radius: 16px;
                background: #ffffff;
                padding: 0.85rem 0.9rem;
                min-height: 108px;
            }

            div[data-testid="stFileUploaderDropzone"] button {
                border-radius: 999px;
                padding: 0.58rem 1.1rem;
                font-weight: 700;
                border: 1px solid #111827;
                background: #111827;
                color: #ffffff;
            }

            div[data-testid="stFileUploaderDropzone"] button:hover {
                background: #0f172a;
                border-color: #0f172a;
            }

            .upload-hero {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 0.35rem;
                padding: 0.6rem 0 0.35rem;
                text-align: center;
            }

            .upload-hero-icon {
                width: 62px;
                height: 62px;
                border-radius: 18px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #5b7bdc;
                background: #f3f6ff;
                margin-bottom: 0.2rem;
            }

            .upload-hero-icon svg {
                width: 28px;
                height: 28px;
                stroke: currentColor;
                stroke-width: 1.8;
                stroke-linecap: round;
                stroke-linejoin: round;
                fill: none;
            }

            .upload-hero-title {
                font-size: 0.9rem;
                font-weight: 700;
                color: #111827;
                line-height: 1.45;
            }

            .upload-hero-copy {
                font-size: 0.76rem;
                color: #6b7280;
                line-height: 1.45;
            }

            .upload-hero-foot {
                font-size: 0.74rem;
                color: #6b7280;
                margin-top: 0.2rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_title_block() -> None:
    # 画面上部のタイトル領域を表示する
    st.markdown(f"<div class='page-title'>{APP_TITLE}</div>", unsafe_allow_html=True)


def render_stepper(current_step: int) -> None:
    # 現在の進行状況をステッパーで表示する
    steps = [
        {"index": 1, "label": "レシート\nアップロード"},
        {"index": 2, "label": "AI検出\n結果"},
        {"index": 3, "label": "入力\n情報"},
        {"index": 4, "label": "確認・Excel\n出力"},
    ]

    step_items = []
    for step in steps:
        if current_step > step["index"]:
            state_class = "done"
        elif current_step == step["index"]:
            state_class = "active"
        else:
            state_class = "inactive"

        label_html = step["label"].replace(chr(10), "<br>")
        step_items.append(
            f'<div class="step-item {state_class}">'
            f'<div class="step-circle">{get_step_icon_svg(step["index"])}</div>'
            f'<div class="step-label">{label_html}</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="stepper-card"><div class="stepper">{"".join(step_items)}</div></div>',
        unsafe_allow_html=True,
    )


def reset_workflow_for_new_file(file_hash: str, image_path: Path) -> None:
    # 新しい画像が選ばれたときに状態を初期化する
    st.session_state.current_file_hash = file_hash
    st.session_state.current_image_path = str(image_path)
    st.session_state.analysis_result = {}
    st.session_state.merchant_name = ""
    st.session_state.tax_rate = 10
    st.session_state.last_export_path = ""
    st.session_state.current_step = 1


def ensure_image_loaded(uploaded_file: Any) -> Path:
    # アップロード済み画像を保存して安定して参照できるようにする
    file_hash = get_file_hash(uploaded_file)
    image_path = save_uploaded_file(uploaded_file, file_hash)

    if st.session_state.current_file_hash != file_hash:
        reset_workflow_for_new_file(file_hash, image_path)

    return image_path


def render_preview_image(image_path: Path, caption: str) -> None:
    # プレビュー画像を表示する
    st.image(image_path, caption=caption, use_container_width=True)


def render_placeholder_preview() -> None:
    # 画像未選択時のプレースホルダーを表示する
    st.markdown(
        '<div class="preview-box"><div><div class="preview-icon">🧾</div>'
        '<div class="preview-title">レシート画像をアップロードしてください</div>'
        '<div class="preview-subtitle">アップロード後、ここにプレビューが表示されます。</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )


def render_readonly_field(label: str, value: str, emphasis: bool = False) -> None:
    # 編集不可の表示フィールドを描画する
    emphasis_class = " emphasis" if emphasis else ""
    st.markdown(
        f'<div class="readonly-field"><div class="readonly-label">{label}</div>'
        f'<div class="readonly-value{emphasis_class}">{value}</div></div>',
        unsafe_allow_html=True,
    )


def render_step_1() -> None:
    # 1段階目: レシート画像をアップロードする
    uploaded_file = None

    left_column, right_column = st.columns([1.0, 1.0], gap="large")

    with left_column:
        with st.container(border=True):
            st.markdown(
                f'<div class="upload-hero"><div class="upload-hero-icon">{get_step_icon_svg(1)}</div>'
                '<div class="upload-hero-title">レシート画像をアップロードしてください</div>'
                '<div class="upload-hero-copy">AIが自動で情報を抽出します。</div></div>',
                unsafe_allow_html=True,
            )
            uploaded_file = st.file_uploader(
                "画像をアップロード",
                type=UPLOAD_TYPES,
                accept_multiple_files=False,
                label_visibility="collapsed",
            )
            st.markdown("<div class='upload-hint'>またはドラッグ＆ドロップ</div>", unsafe_allow_html=True)

            analyze_disabled = uploaded_file is None
            if st.button("解析開始", type="primary", use_container_width=True, disabled=analyze_disabled):
                image_path = ensure_image_loaded(uploaded_file)
                with st.spinner("AIで解析しています..."):
                    st.session_state.analysis_result = run_ai_processing(str(image_path))
                st.session_state.current_step = 2
                st.rerun()

    with right_column:
        with st.container(border=True):
            st.markdown("<div class='panel-title'>アップロード画像</div>", unsafe_allow_html=True)

            if uploaded_file is not None:
                image_path = ensure_image_loaded(uploaded_file)
                render_preview_image(image_path, "アップロード画像")
            elif st.session_state.current_image_path:
                image_path = Path(st.session_state.current_image_path)
                if image_path.exists():
                    render_preview_image(image_path, "アップロード画像")
                else:
                    render_placeholder_preview()
            else:
                render_placeholder_preview()


def render_step_2() -> None:
    # 2段階目: 自動検出結果を表示する
    analysis_result = st.session_state.analysis_result

    if not analysis_result:
        st.info("先にレシート画像をアップロードして解析してください。")
        return

    left_column, right_column = st.columns([1.0, 1.0], gap="large")

    with left_column:
        with st.container(border=True):
            st.markdown("<div class='panel-title'>AI検出結果</div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='panel-text'>"
                "この段階では自動抽出結果を表示するだけで、編集はできません。"
                "</div>",
                unsafe_allow_html=True,
            )

            render_readonly_field("日付", normalize_display_text(analysis_result.get("date", "")))
            render_readonly_field("電話番号", normalize_display_text(analysis_result.get("phone", "")))
            render_readonly_field("合計金額", get_amount_display(analysis_result), emphasis=True)

            if st.button("次へ", type="primary", use_container_width=True):
                st.session_state.current_step = 3
                st.rerun()

    with right_column:
        with st.container(border=True):
            st.markdown("<div class='panel-title'>検出画像</div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='panel-text'>"
                "YOLOで検出した位置を可視化した画像を表示します。"
                "</div>",
                unsafe_allow_html=True,
            )

            annotated_path = str(analysis_result.get("annotated_image_path", "")).strip()
            if annotated_path and Path(annotated_path).exists():
                render_preview_image(Path(annotated_path), "検出画像")
            else:
                render_placeholder_preview()


def render_step_3() -> None:
    # 3段階目: 手入力情報を補完する
    analysis_result = st.session_state.analysis_result
    total_amount = get_amount_value(analysis_result)

    with st.container(border=True):
        st.markdown("<div class='panel-title'>入力情報</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='panel-text'>"
            "AIで取得できなかった情報を入力してください。"
            "</div>",
            unsafe_allow_html=True,
        )

        input_column, result_column = st.columns([1.15, 0.85], gap="large")

        with input_column:
            st.text_input(
                "店舗名",
                key="merchant_name",
                placeholder="店舗名を入力してください",
            )
            st.selectbox(
                "税率",
                options=[8, 10],
                key="tax_rate",
                format_func=lambda value: f"{value}%",
            )

        tax_amount = calculate_tax_amount(total_amount, int(st.session_state.tax_rate))

        with result_column:
            render_readonly_field("消費税額", format_tax_display(tax_amount), emphasis=True)
            st.markdown(
                "<div class='panel-text'>"
                "消費税額は合計金額から自動計算されます。"
                "</div>",
                unsafe_allow_html=True,
            )

        if st.button("次へ", type="primary", use_container_width=True):
            st.session_state.current_step = 4
            st.rerun()


def build_preview_dataframe(record: Dict[str, Any]) -> pd.DataFrame:
    # 出力直前の確認用テーブルを作成する
    amount_display = str(record.get("amount_display", "")).strip()
    if not amount_display:
        amount_display = format_yen_symbol(record.get("amount_value", record.get("amount")))

    preview_row = {
        "ID": record["id"],
        "日付": record["date"],
        "店舗名": record["merchant"],
        "電話番号": record["phone"],
        "合計金額": amount_display,
        "消費税額": str(record.get("tax_display", "")).strip() or format_tax_display(record["tax"]),
        "画像パス": record["image_path"],
    }
    return pd.DataFrame([preview_row])


def build_export_record() -> Dict[str, Any]:
    # 表計算ファイル出力用のデータをまとめる
    analysis_result = st.session_state.analysis_result
    total_amount = get_amount_value(analysis_result)
    amount_display = get_amount_display(analysis_result)
    tax_amount = calculate_tax_amount(total_amount, int(st.session_state.tax_rate))

    return {
        "id": 1,
        "date": normalize_display_text(analysis_result.get("date", "")),
        "phone": normalize_display_text(analysis_result.get("phone", "")),
        "merchant": str(st.session_state.merchant_name).strip(),
        "amount": total_amount,
        "amount_value": total_amount,
        "amount_display": amount_display,
        "tax": tax_amount,
        "tax_display": format_tax_display(tax_amount),
        "image_path": str(st.session_state.current_image_path),
    }


def render_step_4() -> None:
    # 4段階目: 内容を確認して表計算ファイルへ出力する
    analysis_result = st.session_state.analysis_result
    if not analysis_result:
        st.info("先にレシート画像をアップロードして解析してください。")
        return

    record = build_export_record()
    preview_df = build_preview_dataframe(record)

    with st.container(border=True):
        st.markdown("<div class='panel-title'>確認・Excel出力</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='panel-text'>"
            "内容を確認してからExcelに出力します。"
            "</div>",
            unsafe_allow_html=True,
        )

        st.dataframe(preview_df, use_container_width=True, hide_index=True)

        button_column_left, button_column_right = st.columns([1.0, 1.0], gap="medium")

        with button_column_left:
            if st.button("戻る", type="secondary", use_container_width=True):
                st.session_state.current_step = 3
                st.rerun()

        with button_column_right:
            if st.button("Excel出力", type="primary", use_container_width=True):
                try:
                    output_path = export_to_excel(record, DEFAULT_OUTPUT_PATH)
                    st.session_state.last_export_path = str(output_path)
                    st.success(f"Excelファイルを出力しました: {output_path}")
                except Exception as exc:
                    st.error(f"Excelファイルの出力に失敗しました: {exc}")

        if st.session_state.last_export_path:
            export_file = Path(st.session_state.last_export_path)
            if export_file.exists():
                st.download_button(
                    label="Excelをダウンロード",
                    data=export_file.read_bytes(),
                    file_name=export_file.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )


def render_current_step() -> None:
    # 現在のステップに応じて画面を切り替える
    current_step = int(st.session_state.current_step)

    if current_step <= 1:
        render_step_1()
    elif current_step == 2:
        render_step_2()
    elif current_step == 3:
        render_step_3()
    else:
        render_step_4()


def main() -> None:
    # 画面全体を組み立てる
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    initialize_session_state()
    apply_page_style()

    with st.container(border=True):
        render_title_block()
        render_stepper(int(st.session_state.current_step))
        render_current_step()


if __name__ == "__main__":
    main()
