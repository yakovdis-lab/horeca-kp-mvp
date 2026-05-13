import io
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(page_title="MVP: Персональные КП", layout="wide")

CATEGORIES = [
    "фастфуд",
    "кафе",
    "бар",
    "ресторан",
    "кофейня",
    "ритейл",
    "туризм",
]


def read_table(uploaded_file: st.runtime.uploaded_file_manager.UploadedFile, label: str) -> pd.DataFrame:
    try:
        filename = (uploaded_file.name or "").lower()
        if filename.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        return pd.read_excel(uploaded_file)
    except Exception as exc:
        st.error(f"Не удалось прочитать {label}: {exc}")
        return pd.DataFrame()


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def ensure_columns(df: pd.DataFrame, required: list[str], name: str) -> bool:
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"В файле {name} не хватает колонок: {', '.join(missing)}")
        return False
    return True


def prepare_sku_set_from_categories(categories_df: pd.DataFrame, selected_categories: list[str]) -> set[str]:
    filtered = categories_df[categories_df["category"].isin(selected_categories)]
    return set(filtered["sku"].astype(str).str.strip())


def prepare_sku_set_from_menu(menu_df: pd.DataFrame, menu_map_df: pd.DataFrame) -> set[str]:
    menu_items = set(menu_df["menu_item"].astype(str).str.strip())
    mapped = menu_map_df[menu_map_df["menu_item"].astype(str).str.strip().isin(menu_items)]
    return set(mapped["sku"].astype(str).str.strip())


def build_offer(base_skus: set[str], stock_df: pd.DataFrame, price_df: pd.DataFrame, links_df: pd.DataFrame) -> pd.DataFrame:
    stock_map = stock_df.set_index("sku")["stock_qty"].to_dict()
    price_map = price_df.set_index("sku")["price"].to_dict()
    name_map = price_df.set_index("sku")["name"].to_dict()
    link_map = links_df.set_index("sku")["url"].to_dict()

    rows = []
    for sku in sorted(base_skus):
        stock_qty = stock_map.get(sku, 0)
        if pd.isna(stock_qty) or float(stock_qty) <= 0:
            continue
        rows.append(
            {
                "Наименование товара": name_map.get(sku, sku),
                "Цена товара": price_map.get(sku, ""),
                "Ссылка": link_map.get(sku, ""),
                "SKU": sku,
                "Остаток": stock_qty,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.sort_values(["Наименование товара", "SKU"]).reset_index(drop=True)
    return out[["Наименование товара", "Цена товара", "Ссылка"]]


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="КП")
        ws = writer.sheets["КП"]
        ws.set_column("A:A", 45)
        ws.set_column("B:B", 14)
        ws.set_column("C:C", 60)
    return output.getvalue()


st.title("MVP: Персонализированное коммерческое предложение")
st.caption("Сценарии: категория / меню / меню + история продаж")

with st.expander("Требуемые колонки в файлах", expanded=False):
    st.markdown(
        """
- `categories.xlsx`: `category`, `sku`
- `stock.xlsx`: `sku`, `stock_qty`
- `price.xlsx`: `sku`, `name`, `price`
- `sku_links.xlsx`: `sku`, `url`
- `menu.xlsx` (опционально): `menu_item`
- `menu_map.xlsx` (для сценариев с меню): `menu_item`, `sku`
- `sales_history.xlsx` (опционально): `sku`, `qty`
"""
    )

client_name = st.text_input("Название клиента")
selected_categories = st.multiselect("Категория клиента (можно несколько)", CATEGORIES)

col1, col2 = st.columns(2)
with col1:
    stock_file = st.file_uploader("Загрузка складских остатков (Excel/CSV)", type=["xlsx", "xls", "csv"])
    price_file = st.file_uploader("Загрузка прайс-листа (Excel/CSV)", type=["xlsx", "xls", "csv"])
    links_file = st.file_uploader("Загрузка ссылок SKU -> avistrade.by (Excel/CSV)", type=["xlsx", "xls", "csv"])

with col2:
    categories_file = st.file_uploader("Загрузка файла категорий (Excel/CSV)", type=["xlsx", "xls", "csv"])
    menu_file = st.file_uploader("Загрузка меню (Excel/CSV для MVP)", type=["xlsx", "xls", "csv"])
    menu_map_file = st.file_uploader("Загрузка словаря меню -> SKU (Excel/CSV)", type=["xlsx", "xls", "csv"])
    sales_history_file = st.file_uploader("Загрузка истории продаж (Excel/CSV, опционально)", type=["xlsx", "xls", "csv"])

scenario = st.radio(
    "Сценарий",
    [
        "1) Только категория",
        "2) Есть меню",
        "3) Есть меню + история продаж",
    ],
)

if st.button("Сформировать коммерческое предложение", type="primary"):
    if not client_name.strip():
        st.error("Введите название клиента")
        st.stop()

    required_files = {
        "stock.xlsx": stock_file,
        "price.xlsx": price_file,
        "sku_links.xlsx": links_file,
    }
    for name, f in required_files.items():
        if f is None:
            st.error(f"Загрузите {name}")
            st.stop()

    stock_df = normalize_cols(read_table(stock_file, "stock.xlsx/csv"))
    price_df = normalize_cols(read_table(price_file, "price.xlsx/csv"))
    links_df = normalize_cols(read_table(links_file, "sku_links.xlsx/csv"))

    if not all(
        [
            ensure_columns(stock_df, ["sku", "stock_qty"], "stock.xlsx"),
            ensure_columns(price_df, ["sku", "name", "price"], "price.xlsx"),
            ensure_columns(links_df, ["sku", "url"], "sku_links.xlsx"),
        ]
    ):
        st.stop()

    stock_df["sku"] = stock_df["sku"].astype(str).str.strip()
    price_df["sku"] = price_df["sku"].astype(str).str.strip()
    links_df["sku"] = links_df["sku"].astype(str).str.strip()

    base_skus: set[str] = set()

    if scenario.startswith("1"):
        if categories_file is None:
            st.error("Для сценария 1 загрузите categories.xlsx")
            st.stop()
        if not selected_categories:
            st.error("Выберите минимум 1 категорию")
            st.stop()

        categories_df = normalize_cols(read_table(categories_file, "categories.xlsx/csv"))
        if not ensure_columns(categories_df, ["category", "sku"], "categories.xlsx"):
            st.stop()
        categories_df["category"] = categories_df["category"].astype(str).str.strip().str.lower()
        categories_df["sku"] = categories_df["sku"].astype(str).str.strip()

        selected_normalized = [c.strip().lower() for c in selected_categories]
        base_skus = prepare_sku_set_from_categories(categories_df, selected_normalized)

    elif scenario.startswith("2"):
        if menu_file is None or menu_map_file is None:
            st.error("Для сценария 2 загрузите menu.xlsx и menu_map.xlsx")
            st.stop()

        menu_df = normalize_cols(read_table(menu_file, "menu.xlsx/csv"))
        menu_map_df = normalize_cols(read_table(menu_map_file, "menu_map.xlsx/csv"))
        if not all(
            [
                ensure_columns(menu_df, ["menu_item"], "menu.xlsx"),
                ensure_columns(menu_map_df, ["menu_item", "sku"], "menu_map.xlsx"),
            ]
        ):
            st.stop()

        base_skus = prepare_sku_set_from_menu(menu_df, menu_map_df)

    else:
        if menu_file is None or menu_map_file is None or sales_history_file is None:
            st.error("Для сценария 3 загрузите menu.xlsx, menu_map.xlsx и sales_history.xlsx")
            st.stop()

        menu_df = normalize_cols(read_table(menu_file, "menu.xlsx/csv"))
        menu_map_df = normalize_cols(read_table(menu_map_file, "menu_map.xlsx/csv"))
        sales_df = normalize_cols(read_table(sales_history_file, "sales_history.xlsx/csv"))

        if not all(
            [
                ensure_columns(menu_df, ["menu_item"], "menu.xlsx"),
                ensure_columns(menu_map_df, ["menu_item", "sku"], "menu_map.xlsx"),
                ensure_columns(sales_df, ["sku", "qty"], "sales_history.xlsx"),
            ]
        ):
            st.stop()

        base_skus = prepare_sku_set_from_menu(menu_df, menu_map_df)
        bought_skus = set(sales_df["sku"].astype(str).str.strip())
        base_skus = base_skus - bought_skus

    offer_df = build_offer(base_skus, stock_df, price_df, links_df)

    if offer_df.empty:
        st.warning("Подходящих позиций не найдено. Проверьте входные файлы и остатки.")
        st.stop()

    st.success(f"КП сформировано: {len(offer_df)} позиций")
    st.dataframe(offer_df, use_container_width=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"KP_{client_name.strip().replace(' ', '_')}_{stamp}.xlsx"
    st.download_button(
        label="Скачать Excel",
        data=to_excel_bytes(offer_df),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
