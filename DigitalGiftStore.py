import os
import sqlite3
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ======================
# 🔐 TOKEN (через переменную окружения)
# ======================
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN не найден. Добавьте переменную окружения TOKEN в Render")

# ======================
# 🗄 DATABASE
# ======================
conn = sqlite3.connect("db.sqlite3", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    category TEXT,
    buy_price REAL,
    sell_price REAL,
    status TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS balance (
    id INTEGER PRIMARY KEY,
    amount REAL
)
""")

cursor.execute("INSERT OR IGNORE INTO balance (id, amount) VALUES (1, 0)")
conn.commit()

# ======================
# 💰 COMMISSIONS
# ======================
SELL_COMMISSION = 0.10
WITHDRAW_COMMISSION = 0.06


def get_balance():
    cursor.execute("SELECT amount FROM balance WHERE id=1")
    return cursor.fetchone()[0]


def update_balance(value: float):
    cursor.execute(
        "UPDATE balance SET amount = amount + ? WHERE id=1",
        (value,)
    )
    conn.commit()


# ======================
# 🎛 UI
# ======================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Каталог", callback_data="catalog")],
        [InlineKeyboardButton("➕ Добавить", callback_data="add")],
        [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("📊 Аналитика", callback_data="analytics")],
        [InlineKeyboardButton("💸 Вывод", callback_data="withdraw")],
    ])


# ======================
# 🚀 START
# ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Панель управления:",
        reply_markup=main_menu()
    )


# ======================
# ➕ ADD ITEM FLOW
# ======================
async def add_item(update, context):
    await update.callback_query.answer()
    context.user_data["step"] = "name"
    await update.callback_query.message.reply_text("Введите название товара")


async def handle_text(update, context):
    step = context.user_data.get("step")

    if step == "name":
        context.user_data["name"] = update.message.text
        context.user_data["step"] = "category"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎮 Аккаунт", callback_data="cat_account")],
            [InlineKeyboardButton("🔑 Ключ", callback_data="cat_key")],
            [InlineKeyboardButton("🎁 Гифт", callback_data="cat_gift")],
        ])

        await update.message.reply_text("Выберите категорию:", reply_markup=keyboard)

    elif step == "buy_price":
        name = context.user_data["name"]
        category = context.user_data["category"]
        price = float(update.message.text)

        cursor.execute(
            "INSERT INTO items (name, category, buy_price, status) VALUES (?, ?, ?, ?)",
            (name, category, price, "active")
        )
        conn.commit()

        update_balance(-price)
        context.user_data.clear()

        await update.message.reply_text("✅ Товар добавлен")

    elif step == "sell_price":
        item_id = context.user_data["item_id"]
        sell_price = float(update.message.text)

        cursor.execute("SELECT buy_price FROM items WHERE id=?", (item_id,))
        buy_price = cursor.fetchone()[0]

        fee = sell_price * SELL_COMMISSION
        profit = sell_price - buy_price - fee

        cursor.execute("""
            UPDATE items
            SET sell_price=?, status='sold'
            WHERE id=?
        """, (sell_price, item_id))

        conn.commit()

        update_balance(sell_price - fee)
        context.user_data.clear()

        await update.message.reply_text(
            f"💰 Продано\n"
            f"Комиссия: {fee:.2f}\n"
            f"Прибыль: {profit:.2f}\n"
            f"Баланс: {get_balance():.2f}"
        )

    elif step == "withdraw":
        amount = float(update.message.text)
        fee = amount * WITHDRAW_COMMISSION
        total = amount + fee

        if total > get_balance():
            await update.message.reply_text("❌ Недостаточно средств")
            return

        update_balance(-total)
        context.user_data.clear()

        await update.message.reply_text(
            f"💸 Вывод\n"
            f"Комиссия: {fee:.2f}\n"
            f"Списано: {total:.2f}\n"
            f"Баланс: {get_balance():.2f}"
        )


# ======================
# 📦 CATEGORY
# ======================
async def set_category(update, context):
    query = update.callback_query
    await query.answer()

    category = query.data.split("_")[1]
    context.user_data["category"] = category
    context.user_data["step"] = "buy_price"

    await query.message.reply_text("Введите цену покупки")


# ======================
# 📂 CATALOG
# ======================
async def catalog(update, context):
    await update.callback_query.answer()

    cursor.execute("SELECT * FROM items WHERE status='active'")
    items = cursor.fetchall()

    if not items:
        await update.callback_query.message.reply_text("Каталог пуст")
        return

    for item in items:
        text = f"{item[1]} | {item[2]}\n💰 Закуп: {item[3]}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💸 Продать", callback_data=f"sell_{item[0]}")]
        ])

        await update.callback_query.message.reply_text(text, reply_markup=keyboard)


# ======================
# 💰 SELL
# ======================
async def sell_item(update, context):
    query = update.callback_query
    await query.answer()

    item_id = int(query.data.split("_")[1])
    context.user_data["item_id"] = item_id
    context.user_data["step"] = "sell_price"

    await query.message.reply_text("Введите цену продажи")


# ======================
# 💰 BALANCE
# ======================
async def balance(update, context):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        f"💰 Баланс: {get_balance():.2f}"
    )


# ======================
# 📊 ANALYTICS
# ======================
async def analytics(update, context):
    await update.callback_query.answer()

    cursor.execute("SELECT COUNT(*) FROM items WHERE status='sold'")
    count = cursor.fetchone()[0]

    await update.callback_query.message.reply_text(
        f"📊 Продано товаров: {count}"
    )


# ======================
# 💸 WITHDRAW
# ======================
async def withdraw(update, context):
    await update.callback_query.answer()
    context.user_data["step"] = "withdraw"
    await update.callback_query.message.reply_text("Введите сумму вывода")


# ======================
# ▶️ RUN BOT
# ======================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(add_item, pattern="add"))
    app.add_handler(CallbackQueryHandler(set_category, pattern="cat_"))
    app.add_handler(CallbackQueryHandler(catalog, pattern="catalog"))
    app.add_handler(CallbackQueryHandler(sell_item, pattern="sell_"))
    app.add_handler(CallbackQueryHandler(balance, pattern="balance"))
    app.add_handler(CallbackQueryHandler(analytics, pattern="analytics"))
    app.add_handler(CallbackQueryHandler(withdraw, pattern="withdraw"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🤖 Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()