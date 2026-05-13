import pandas as pd

categories = pd.DataFrame(
    [
        {"category": "ресторан", "sku": "SKU001"},
        {"category": "кафе", "sku": "SKU002"},
        {"category": "фастфуд", "sku": "SKU003"},
        {"category": "кофейня", "sku": "SKU004"},
    ]
)

stock = pd.DataFrame(
    [
        {"sku": "SKU001", "stock_qty": 20},
        {"sku": "SKU002", "stock_qty": 15},
        {"sku": "SKU003", "stock_qty": 0},
        {"sku": "SKU004", "stock_qty": 8},
    ]
)

price = pd.DataFrame(
    [
        {"sku": "SKU001", "name": "Томаты резаные 2.5кг", "price": 12.5},
        {"sku": "SKU002", "name": "Сыр моцарелла 1кг", "price": 25.0},
        {"sku": "SKU003", "name": "Булочка бургерная", "price": 1.2},
        {"sku": "SKU004", "name": "Сироп ванильный 1л", "price": 9.8},
    ]
)

links = pd.DataFrame(
    [
        {"sku": "SKU001", "url": "https://avistrade.by/catalog/sku001"},
        {"sku": "SKU002", "url": "https://avistrade.by/catalog/sku002"},
        {"sku": "SKU003", "url": "https://avistrade.by/catalog/sku003"},
        {"sku": "SKU004", "url": "https://avistrade.by/catalog/sku004"},
    ]
)

menu = pd.DataFrame(
    [
        {"menu_item": "Пицца Маргарита"},
        {"menu_item": "Капучино"},
    ]
)

menu_map = pd.DataFrame(
    [
        {"menu_item": "Пицца Маргарита", "sku": "SKU001"},
        {"menu_item": "Пицца Маргарита", "sku": "SKU002"},
        {"menu_item": "Капучино", "sku": "SKU004"},
    ]
)

sales_history = pd.DataFrame(
    [
        {"sku": "SKU001", "qty": 10},
    ]
)

categories.to_excel("templates/categories.xlsx", index=False)
stock.to_excel("templates/stock.xlsx", index=False)
price.to_excel("templates/price.xlsx", index=False)
links.to_excel("templates/sku_links.xlsx", index=False)
menu.to_excel("templates/menu.xlsx", index=False)
menu_map.to_excel("templates/menu_map.xlsx", index=False)
sales_history.to_excel("templates/sales_history.xlsx", index=False)

print("Templates created in ./templates")
