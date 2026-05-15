import io
import re
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st

st.set_page_config(page_title="MVP: Персональные КП", layout="wide")

CATEGORIES = [
    "фастфуд", "кафе", "бар", "ресторан", "кофейня", "ритейл", "туризм",
]

CATEGORY_FILE_MAP = {
    "фастфуд": "fastfood.csv",
    "кафе": "cafe.csv",
    "бар": "bar.csv",
    "ресторан": "restaurant.csv",
    "кофейня": "coffeehouse.csv",
    "ритейл": "retail.csv",
    "туризм": "tourism.csv",
}

CATEGORY_DIR = Path("data") / "category_assortment"
MENU_RULES_FILE = Path("data") / "menu_ingredient_rules.csv"
AVISTRADE_SEARCH_URL = "https://avistrade.by/search/?q="


def read_table(uploaded_file, label: str) -> pd.DataFrame:
    try:
        filename = (uploaded_file.name or "").lower()
        if filename.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        return pd.read_excel(uploaded_file)
    except Exception as exc:
        st.error(f"Не удалось прочитать {label}: {exc}")
        return pd.DataFrame()


def read_local_table(path: Path, label: str) -> pd.DataFrame:
    try:
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        return pd.read_excel(path)
    except Exception as exc:
        st.error(f"Не удалось прочитать {label}: {exc}")
        return pd.DataFrame()


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def normalize_text(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def ensure_columns(df: pd.DataFrame, required: list[str], name: str) -> bool:
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"В файле {name} не хватает колонок: {', '.join(missing)}")
        return False
    return True


def load_category_catalog(selected_categories: list[str]) -> pd.DataFrame:
    chunks = []
    for category in selected_categories:
        file_name = CATEGORY_FILE_MAP.get(category)
        if not file_name:
            st.error(f"Для категории '{category}' не настроен файл ассортимента")
            st.stop()

        path = CATEGORY_DIR / file_name
        if not path.exists():
            st.error(f"Не найден файл ассортимента: {path}")
            st.stop()

        part = normalize_cols(read_local_table(path, str(path)))
        if not ensure_columns(part, ["name"], str(path)):
            st.stop()

        part["name"] = part["name"].astype(str).str.strip()
        part["category"] = category
        chunks.append(part[["category", "name"]])

    if not chunks:
        return pd.DataFrame(columns=["category", "name"])

    return pd.concat(chunks, ignore_index=True)


def prepare_sku_set_from_categories(categories_df, selected_categories, price_df) -> set[str]:
    filtered = categories_df[categories_df["category"].isin(selected_categories)].copy()
    filtered["name_norm"] = filtered["name"].map(normalize_text)

    price_lookup = price_df[["sku", "name"]].copy()
    price_lookup["name_norm"] = price_lookup["name"].map(normalize_text)

    merged = filtered.merge(price_lookup[["name_norm", "sku"]], how="left", on="name_norm")
    missing = merged[merged["sku"].isna()]["name"].dropna().unique().tolist()
    if missing:
        st.warning("Не найдены в прайсе некоторые позиции категорий: " + ", ".join(missing[:10]))

    return set(merged["sku"].dropna().astype(str).str.strip())


def load_menu_rules() -> pd.DataFrame:
    if not MENU_RULES_FILE.exists():
        st.error(f"Не найден файл правил меню: {MENU_RULES_FILE}")
        st.stop()
    rules_df = normalize_cols(read_local_table(MENU_RULES_FILE, str(MENU_RULES_FILE)))
    if not ensure_columns(rules_df, ["dish_keyword", "ingredient_name"], str(MENU_RULES_FILE)):
        st.stop()
    rules_df["dish_keyword"] = rules_df["dish_keyword"].astype(str).map(normalize_text)
    rules_df["ingredient_name"] = rules_df["ingredient_name"].astype(str).str.strip()
    return rules_df


def infer_ingredient_names_from_menu(menu_df, rules_df):
    if not ensure_columns(menu_df, ["menu_item"], "menu.xlsx"):
        st.stop()

    menu_items = menu_df["menu_item"].dropna().astype(str).map(normalize_text).tolist()
    inferred = set()
    unmatched = []

    grouped_rules = rules_df.groupby("dish_keyword")["ingredient_name"].apply(list).to_dict()

    for item in menu_items:
        matched = False
        for keyword, ingredients in grouped_rules.items():
            if keyword and keyword in item:
                inferred.update(ingredients)
                matched = True
        if not matched:
            unmatched.append(item)

    return inferred, unmatched


def map_ingredient_names_to_sku(ingredient_names: set[str], price_df):
    ing_df = pd.DataFrame({"name": sorted(ingredient_names)})
    ing_df["name_norm"] = ing_df["name"].map(normalize_text)

    price_lookup = price_df[["sku", "name"]].copy()
    price_lookup["name_norm"] = price_lookup["name"].map(normalize_text)

    merged = ing_df.merge(price_lookup[["name_norm", "sku"]], how="left", on="name_norm")
    missing = merged[merged["sku"].isna()]["name"].dropna().unique().tolist()
    skus = set(merged["sku"].dropna().astype(str).str.strip())
    return skus, missing


@st.cache_data(show_spinner=False)
def find_avistrade_link(product_name: str) -> str:
    query = quote_plus(product_name)
    fallback = f"{AVISTRADE_SEARCH_URL}{query}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        req = Request(url=fallback, headers=headers)
        with urlopen(req, timeout=8) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return fallback

    for href in re.findall(r'href=["\']([^"\']+)["\']', html):
        link = unescape(href.strip())
        if "/catalog/" not in link:
            continue
        if link in ("/catalog/", "https://avistrade.by/catalog/"):
            continue
        if link.startswith("/"):
            return f"https://avistrade.by{link}"
        if link.startswith("https://avistrade.by"):
            return link

    return fallback


def build_offer(base_skus, stock_df, price_df):
    stock_map = stock_df.set_index("sku")["stock_qty"].to_dict()
    price_map = price_df.set_index("sku")["price"].to_dict()
    name_map = price_df.set_index("sku")["name"].to_dict()

    rows = []
    for sku in sorted(base_skus):
        stock_qty = stock_map.get(sku, 0)
        if pd.isna(stock_qty) or float(stock_qty) <= 0:
            continue
        product_name = name_map.get(sku, sku)
        rows.append({
            "Наименование товара": product_name,
            "Цена товара": price_map.get(sku, ""),
            "Ссылка": find_avistrade_link(product_name),
        })

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["Наименование товара"]).reset_index(drop=True)


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="КП")
    return output.getvalue()


st.title("MVP: Персонализированное коммерческое предложение")
client_name = st.text_input("Название клиента")
selected_categories = st.multiselect("Категория клиента (можно несколько)", CATEGORIES)

col1, col2 = st.columns(2)
with col1:
    stock_file = st.file_uploader("Загрузка складских остатков (Excel/CSV)", type=["xlsx", "xls", "csv"])
    price_file = st.file_uploader("Загрузка прайс-листа (Excel/CSV)", type=["xlsx", "xls", "csv"])
with col2:
    menu_file = st.file_uploader("Загрузка меню (Excel/CSV для MVP)", type=["xlsx", "xls", "csv"])
    sales_history_file = st.file_uploader("Загрузка истории продаж (Excel/CSV, опционально)", type=["xlsx", "xls", "csv"])

scenario = st.radio("Сценарий", ["1) Только категория", "2) Есть меню", "3) Есть меню + история продаж"])

if st.button("Сформировать коммерческое предложение", type="primary"):
    if not client_name.strip():
        st.error("Введите название клиента")
        st.stop()

    if stock_file is None or price_file is None:
        st.error("Загрузите stock.xlsx и price.xlsx")
        st.stop()

    stock_df = normalize_cols(read_table(stock_file, "stock"))
    price_df = normalize_cols(read_table(price_file, "price"))

    if not all([
        ensure_columns(stock_df, ["sku", "stock_qty"], "stock.xlsx"),
        ensure_columns(price_df, ["sku", "name", "price"], "price.xlsx"),
    ]):
        st.stop()

    stock_df["sku"] = stock_df["sku"].astype(str).str.strip()
    price_df["sku"] = price_df["sku"].astype(str).str.strip()
    price_df["name"] = price_df["name"].astype(str).str.strip()

    base_skus = set()

    if scenario.startswith("1"):
        if not selected_categories:
            st.error("Выберите минимум 1 категорию")
            st.stop()
        categories_df = load_category_catalog(selected_categories)
        base_skus = prepare_sku_set_from_categories(categories_df, [c.lower() for c in selected_categories], price_df)

    elif scenario.startswith("2"):
        if menu_file is None:
            st.error("Для сценария 2 загрузите menu.xlsx")
            st.stop()
        menu_df = normalize_cols(read_table(menu_file, "menu"))
        rules_df = load_menu_rules()
        ingredient_names, _ = infer_ingredient_names_from_menu(menu_df, rules_df)
        base_skus, _ = map_ingredient_names_to_sku(ingredient_names, price_df)

    else:
        if menu_file is None or sales_history_file is None:
            st.error("Для сценария 3 загрузите menu.xlsx и sales_history.xlsx")
            st.stop()
        menu_df = normalize_cols(read_table(menu_file, "menu"))
        sales_df = normalize_cols(read_table(sales_history_file, "sales_history"))
        if not ensure_columns(sales_df, ["sku", "qty"], "sales_history.xlsx"):
            st.stop()
        rules_df = load_menu_rules()
        ingredient_names, _ = infer_ingredient_names_from_menu(menu_df, rules_df)
        base_skus, _ = map_ingredient_names_to_sku(ingredient_names, price_df)
        base_skus -= set(sales_df["sku"].astype(str).str.strip())

    offer_df = build_offer(base_skus, stock_df, price_df)
    if offer_df.empty:
        st.warning("Подходящих позиций не найдено.")
        st.stop()

    st.dataframe(offer_df, use_container_width=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"KP_{client_name.strip().replace(' ', '_')}_{stamp}.xlsx"
    st.download_button("Скачать Excel", to_excel_bytes(offer_df), filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

