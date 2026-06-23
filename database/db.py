import asyncpg
import asyncio
import os
from datetime import datetime, timedelta
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv, find_dotenv

# .env файлын жүктеу
load_dotenv(find_dotenv())
DATABASE_URL = os.getenv("DATABASE_URL")


async def get_db_connection():
    """PostgreSQL бұлттық базасына қосылу нүктесін ашу"""
    return await asyncpg.connect(DATABASE_URL)


async def init_db():
    """Деректер базасын және қажетті кестелерді құру функциясы (PostgreSQL нұсқасы)"""
    conn = await get_db_connection()
    try:
        # 1. Пайдаланушылар кестесі (Telegram ID үлкен болғандықтан BIGINT қолданамыз)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                full_name VARCHAR(255) NOT NULL,
                phone_number VARCHAR(50) NOT NULL,
                is_client INT DEFAULT 0,
                is_driver INT DEFAULT 0,
                current_mode VARCHAR(50) DEFAULT 'client',
                registration_date VARCHAR(50)
            );
        """)

        # 2. Таксистердің қосымша мәліметтер кестесі
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS drivers (
                telegram_id BIGINT PRIMARY KEY,
                car_model VARCHAR(255) NOT NULL,
                car_number VARCHAR(50) NOT NULL,
                subscription_start VARCHAR(50),
                subscription_end VARCHAR(50),
                is_online INT DEFAULT 0,
                registration_date VARCHAR(50),
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id) ON DELETE CASCADE
            );
        """)

        # 3. Заказдар кестесі (PostgreSQL-де AUTOINCREMENT орнына SERIAL қолданылады)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id SERIAL PRIMARY KEY,
                client_id BIGINT NOT NULL,
                driver_id BIGINT,
                from_address TEXT NOT NULL,
                to_address TEXT NOT NULL,
                price INT NOT NULL,
                status VARCHAR(50) DEFAULT 'waiting',
                order_type VARCHAR(50) DEFAULT 'local',
                created_at VARCHAR(50) NOT NULL,
                accepted_at VARCHAR(50),
                rating INT DEFAULT 0,
                review TEXT,
                FOREIGN KEY (client_id) REFERENCES users (telegram_id),
                FOREIGN KEY (driver_id) REFERENCES drivers (telegram_id)
            );
        """)
        print("🚀 PostgreSQL кестелері сәтті тексерілді және құрылды!")
    finally:
        await conn.close()


# --- КӨМЕКШІ ФУНКЦИЯЛАР ---

async def register_user(telegram_id: int, full_name: str, phone_number: str, role_to_add: str):
    """Жаңа қолданушыны тіркеу немесе бар қолданушыға жаңа рөл (статус) қосу"""
    conn = await get_db_connection()
    try:
        reg_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        # PostgreSQL-дегі UPSERT (ON CONFLICT) форматы
        await conn.execute("""
            INSERT INTO users (telegram_id, full_name, phone_number, is_client, is_driver, current_mode, registration_date) 
            VALUES ($1, $2, $3, 0, 0, 'client', $4)
            ON CONFLICT(telegram_id) DO UPDATE SET 
            full_name = EXCLUDED.full_name,
            phone_number = EXCLUDED.phone_number;
        """, telegram_id, full_name, phone_number, reg_date)

        if role_to_add == 'client':
            await conn.execute("UPDATE users SET is_client = 1, current_mode = 'client' WHERE telegram_id = $1",
                               telegram_id)
        elif role_to_add == 'driver':
            await conn.execute("UPDATE users SET is_driver = 1, current_mode = 'driver' WHERE telegram_id = $1",
                               telegram_id)
    finally:
        await conn.close()


# async def register_driver(telegram_id: int, car_model: str, car_number: str):
#     """Жаңа таксисті көлік мәліметтерімен және тіркелген күнімен базаға сақтау"""
#     conn = await get_db_connection()
#     try:
#         reg_date = datetime.now().strftime("%Y-%m-%d %H:%M")
#         await conn.execute("""
#             INSERT INTO drivers (telegram_id, car_model, car_number, subscription_end, is_online, registration_date)
#             VALUES ($1, $2, $3, NULL, 0, $4)
#             ON CONFLICT (telegram_id) DO UPDATE SET
#             car_model = EXCLUDED.car_model,
#             car_number = EXCLUDED.car_number;
#         """, telegram_id, car_model, car_number, reg_date)
#     finally:
#         await conn.close()


async def register_driver_complete(telegram_id: int, car_model: str, car_number: str, full_name: str, phone_number: str,
                                   reg_date: str):
    """Жүргізушіні drivers кестесіне қосу және users кестесіндегі статусын толық жаңарту (PostgreSQL)"""
    conn = await get_db_connection()
    try:
        # 1. ЕҢ БІРІНШІ: Пайдаланушының users кестесінде бар-жоғын тексереміз немесе тіркейміз
        user_exists = await conn.fetchrow("SELECT telegram_id FROM users WHERE telegram_id = $1", telegram_id)

        if user_exists:
            # Клиент базада бар болса, тек таксист статусын беріп, режимді ауыстырамыз
            await conn.execute("""
                UPDATE users 
                SET is_driver = 1, current_mode = 'driver' 
                WHERE telegram_id = $1;
            """, telegram_id)
        else:
            # Мүлдем жаңа адам болса (клиент болып тіркелмеген):
            await conn.execute("""
                INSERT INTO users (telegram_id, full_name, phone_number, is_client, is_driver, current_mode, registration_date) 
                VALUES ($1, $2, $3, 0, 1, 'driver', $4);
            """, telegram_id, full_name, phone_number, reg_date)

        # 2. ЕКІНШІ: Пайдаланушы users кестесіне нақты жазылғаннан кейін ғана drivers-қа қосамыз
        await conn.execute("""
            INSERT INTO drivers (telegram_id, car_model, car_number, subscription_end, is_online, registration_date) 
            VALUES ($1, $2, $3, NULL, 0, $4)
            ON CONFLICT (telegram_id) DO UPDATE SET
            car_model = EXCLUDED.car_model,
            car_number = EXCLUDED.car_number,
            registration_date = EXCLUDED.registration_date;
        """, telegram_id, car_model, car_number, reg_date)

    finally:
        await conn.close()


async def get_user(telegram_id: int):
    """Қолданушының базада бар-жоғын және ролін тексеру"""
    conn = await get_db_connection()
    try:
        return await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
    finally:
        await conn.close()


async def get_driver(telegram_id: int):
    """Таксист туралы толық мәлімет алу (Жазылымын тексеру үшін керек)"""
    conn = await get_db_connection()
    try:
        return await conn.fetchrow("SELECT * FROM drivers WHERE telegram_id = $1", telegram_id)
    finally:
        await conn.close()


async def update_driver_subscription(telegram_id: int, days: int):
    """Таксистке берілген күн сасын қосу (Жазылымды жаңарту)"""
    conn = await get_db_connection()
    try:
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        await conn.execute(
            "UPDATE drivers SET subscription_start = $1, subscription_end = $2 WHERE telegram_id = $3",
            start_date, end_date, telegram_id
        )
    finally:
        await conn.close()


async def check_driver_subscription(telegram_id: int) -> bool:
    """Таксистің белсенді жазылымы бар-жоғын тексеру (True/False)"""
    conn = await get_db_connection()
    try:
        row = await conn.fetchrow("SELECT subscription_end FROM drivers WHERE telegram_id = $1", telegram_id)
        if row and row[0]:
            end_date = datetime.strptime(row[0], "%Y-%m-%d").date()
            return end_date >= datetime.now().date()
        return False
    finally:
        await conn.close()


async def update_order_status(order_id: int, status: str):
    """Заказдың статусын жаңарту (мысалы: 'completed')"""
    conn = await get_db_connection()
    try:
        await conn.execute("UPDATE orders SET status = $1 WHERE order_id = $2", status, order_id)
    finally:
        await conn.close()


async def set_driver_online_status(telegram_id: int, is_online: int):
    """Таксисті линияға шығару (1) немесе түсіру (0)"""
    conn = await get_db_connection()
    try:
        await conn.execute("UPDATE drivers SET is_online = $1 WHERE telegram_id = $2", is_online, telegram_id)
    finally:
        await conn.close()


async def create_order(client_id: int, from_address: str, to_address: str, price: int,
                       order_type: str = 'local') -> int:
    """Жаңа заказды базаға сақтап, оның order_id нөмірін қайтарады"""
    conn = await get_db_connection()
    try:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # PostgreSQL-де жаңа құрылған ID-ді RETURNING арқылы бірден оқып аламыз
        order_id = await conn.fetchval("""
            INSERT INTO orders (client_id, from_address, to_address, price, order_type, created_at) 
            VALUES ($1, $2, $3, $4, $5, $6) 
            RETURNING order_id;
        """, client_id, from_address, to_address, price, order_type, created_at)
        return order_id
    finally:
        await conn.close()


async def get_online_drivers() -> list:
    """Қазір линияда тұрған таксистердің ID тізімін алу"""
    conn = await get_db_connection()
    try:
        rows = await conn.fetch("SELECT telegram_id FROM drivers WHERE is_online = 1")
        return [row[0] for row in rows]
    finally:
        await conn.close()


async def get_available_drivers() -> list:
    """Онлайн тұрған, бірақ қазір активті заказы ЖОҚ (бос) таксистерді алу"""
    conn = await get_db_connection()
    try:
        rows = await conn.fetch("""
            SELECT d.telegram_id 
            FROM drivers d
            WHERE d.is_online = 1 
              AND d.telegram_id NOT IN (
                  SELECT driver_id FROM orders 
                  WHERE status IN ('accepted', 'arrived', 'in_progress', 'payment_pending')
                  AND driver_id IS NOT NULL
              );
        """)
        return [row[0] for row in rows]
    finally:
        await conn.close()


async def assign_order_to_driver(order_id: int, driver_id: int, final_price: int) -> tuple:
    """Заказды таксистке бекіту және қабылданған уақытты жазу"""
    conn = await get_db_connection()
    try:
        accepted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_str = await conn.execute("""
            UPDATE orders 
            SET driver_id = $1, price = $2, status = 'accepted', accepted_at = $3 
            WHERE order_id = $4 AND status = 'waiting';
        """, driver_id, final_price, accepted_at, order_id)

        # asyncpg-де өзгерген жолдар санын тексеру тәсілі
        rows_affected = int(status_str.split()[-1])
        return rows_affected > 0, accepted_at
    finally:
        await conn.close()


async def get_order_details(order_id: int):
    """Заказ бен оған қатысты клиенттің толық мәліметін алу"""
    conn = await get_db_connection()
    try:
        return await conn.fetchrow("""
            SELECT o.from_address, o.to_address, o.price, u.full_name, u.phone_number, o.client_id, o.order_type 
            FROM orders o
            JOIN users u ON o.client_id = u.telegram_id
            WHERE o.order_id = $1;
        """, order_id)
    finally:
        await conn.close()


async def get_general_statistics():
    """Бастыққа арналған жалпы статистиканы алу"""
    conn = await get_db_connection()
    try:
        clients_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_client = 1")
        drivers_count = await conn.fetchval("SELECT COUNT(*) FROM drivers")

        today = datetime.now().strftime("%Y-%m-%d")
        orders_today = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE created_at LIKE $1", f"{today}%")

        return clients_count, drivers_count, orders_today
    finally:
        await conn.close()


async def get_recent_orders(limit: int = 5):
    """Соңғы бірнеше заказдың тізімін алу"""
    conn = await get_db_connection()
    try:
        return await conn.fetch(
            "SELECT order_id, from_address, to_address, price, status FROM orders ORDER BY order_id DESC LIMIT $1",
            limit
        )
    finally:
        await conn.close()


async def get_waiting_orders():
    conn = await get_db_connection()
    try:
        # 🌟 SQL сұраныстың ішіне o.order_type бағанын қосамыз
        rows = await conn.fetch("""
            SELECT o.order_id, o.from_addr, o.to_addr, o.price, u.full_name, u.phone_number, o.order_type 
            FROM orders o
            JOIN users u ON o.client_id = u.telegram_id
            WHERE o.status = 'waiting'
            ORDER BY o.created_at DESC
        """)
        return rows
    finally:
        await conn.close()


async def cancel_order_by_client(order_id: int) -> bool:
    """Клиент тапсырысты жойғанда қолданылады"""
    conn = await get_db_connection()
    try:
        status_str = await conn.execute(
            "UPDATE orders SET status = 'cancelled' WHERE order_id = $1 AND status = 'waiting'",
            order_id
        )
        rows_affected = int(status_str.split()[-1])
        return rows_affected > 0
    finally:
        await conn.close()


async def get_all_drivers_admin() -> list:
    """Админ үшін барлық таксистердің деректерін алу (PostgreSQL талаптарына сай икемделді)"""
    conn = await get_db_connection()
    try:
        return await conn.fetch("""
            SELECT 
                u.full_name, 
                u.phone_number, 
                d.car_model, 
                d.car_number, 
                COALESCE(d.registration_date, 'Белгісіз') as registration_date, 
                COALESCE(d.subscription_start, 'Жоқ') as sub_start_date, 
                COALESCE(d.subscription_end, 'Жоқ') as sub_end_date, 
                COUNT(CASE WHEN o.status LIKE '%completed%' THEN 1 END) as completed_orders, 
                d.is_online 
            FROM users u
            JOIN drivers d ON u.telegram_id = d.telegram_id
            LEFT JOIN orders o ON o.driver_id = u.telegram_id
            WHERE u.is_driver = 1
            GROUP BY u.telegram_id, u.full_name, u.phone_number, d.car_model, d.car_number, d.registration_date, d.subscription_start, d.subscription_end, d.is_online;
        """)
    finally:
        await conn.close()


async def get_all_clients_admin() -> list:
    """Админ үшін барлық клиенттердің деректерін алу"""
    conn = await get_db_connection()
    try:
        return await conn.fetch("""
            SELECT 
                u.full_name, 
                u.phone_number, 
                COALESCE(u.registration_date, 'Жоқ') as registration_date, 
                COUNT(CASE WHEN o.status LIKE '%completed%' THEN 1 END) as completed_orders 
            FROM users u
            LEFT JOIN orders o ON o.client_id = u.telegram_id
            WHERE u.is_client = 1
            GROUP BY u.telegram_id, u.full_name, u.phone_number, u.registration_date;
        """)
    finally:
        await conn.close()


async def get_all_orders_admin() -> list:
    """Админ үшін барлық заказдарды алу"""
    conn = await get_db_connection()
    try:
        return await conn.fetch("""
            SELECT 
                o.order_id, 
                COALESCE(c.full_name, 'Өшірілген қолданушы') as client_name, 
                COALESCE(d.full_name, 'Ізделуде...') as driver_name,
                o.from_address, 
                o.to_address, 
                o.price, 
                o.status,
                COALESCE(o.rating, 0) as rating,   
                COALESCE(o.review, '') as review   
            FROM orders o
            LEFT JOIN users c ON o.client_id = c.telegram_id
            LEFT JOIN users d ON o.driver_id = d.telegram_id
            ORDER BY o.order_id DESC LIMIT 50;
        """)
    finally:
        await conn.close()


async def auto_cancel_waiting_order(order_id: int, bot: Bot, timeout_seconds: int = 1800):
    """
    1-ФУНКЦИЯ: Клиент заказ бергеннен кейін маңайда такси табылмаса,
    белгілі бір уақыттан кейін (мысалы, 30 минут) заказды автоматты түрде жою.
    """
    await asyncio.sleep(timeout_seconds)

    conn = await get_db_connection()
    try:
        row = await conn.fetchrow("SELECT status, client_id FROM orders WHERE order_id = $1", order_id)

        # Егер 30 минуттан кейін де заказды ешқандай таксист алмаса (статус әлі 'waiting')
        if row and row['status'] == 'waiting':
            await conn.execute("UPDATE orders SET status = 'timeout_cancelled' WHERE order_id = $1", order_id)
            client_id = row['client_id']

            try:
                await bot.send_message(
                    chat_id=client_id,
                    text=f"⏱ <b>№{order_id} Тапсырыс уақыты өтті.</b>\n"
                         f"Кешіріңіз, қазіргі уақытта маңайда бос такси табылмағандықтан, тапсырысыңыз автоматты түрде жойылды."
                )
            except Exception:
                pass
    finally:
        await conn.close()


async def auto_complete_order_after_timeout(order_id: int, bot: Bot, timeout_seconds: int = 600):
    """
    ФОНДЫҚ ФУНКЦИЯ: Таксист заказды қабылдағаннан кейін белгіленген уақыт (10 немесе 60 мин) өтсе,
    тапсырысты автоматты түрде ЖОЮ емес, АЯҚТАЛДЫ (completed) күйіне өткізу және таксисті линияға қайта қосу.
    """
    await asyncio.sleep(timeout_seconds)
    minutes = timeout_seconds // 60

    conn = await get_db_connection()
    try:
        row = await conn.fetchrow("SELECT status, client_id, driver_id FROM orders WHERE order_id = $1", order_id)

        # Егер уақыт өткенде статус әлі де 'accepted' болса (яғни таксист өздігінен жаппаған болса)
        if row and row['status'] == 'accepted':
            client_id = row['client_id']
            driver_id = row['driver_id']

            # 1. Тапсырысты базада 'completed' деп өзгертеміз
            await conn.execute("UPDATE orders SET status = 'completed' WHERE order_id = $1", order_id)

            # 2. МАНЫЗДЫ: Жүргізушіні базада қайтадан ЛИНЯҒА ҚОСАМЫЗ (белсенді қыламыз)
            await conn.execute("UPDATE drivers SET is_online = 1 WHERE telegram_id = $1", driver_id)

            # Клиентке арналған жұлдызшалар (бағалау клавиатурасы)
            stars_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="1 ⭐️", callback_data=f"rate_driver:{order_id}:1"),
                    InlineKeyboardButton(text="2 ⭐️", callback_data=f"rate_driver:{order_id}:2"),
                    InlineKeyboardButton(text="3 ⭐️", callback_data=f"rate_driver:{order_id}:3")
                ],
                [
                    InlineKeyboardButton(text="4 ⭐️", callback_data=f"rate_driver:{order_id}:4"),
                    InlineKeyboardButton(text="5 ⭐️", callback_data=f"rate_driver:{order_id}:5")
                ]
            ])

            try:
                # Клиентке хабарлама жіберу
                await bot.send_message(
                    chat_id=client_id,
                    text=f"⏱ <b>Сапардың максималды уақыты өтті ({minutes} минут).</b>\n\n"
                         f"Тапсырыс жүйеде автоматты түрде аяқталды деп белгіленді.\n"
                         f"Сапарыңыз қалай өтті? Жүргізушіні бағалай аласыз ба? 👇",
                    reply_markup=stars_kb,
                    parse_mode="HTML"
                )

                # Таксистке хабарлама жіберу
                await bot.send_message(
                    chat_id=driver_id,
                    text=f"⏱ <b>Сапардың максималды уақыты бітті ({minutes} минут)!</b>\n\n"
                         f"№{order_id} тапсырыс жүйе тарапынан автоматты түрде аяқталды.\n"
                         f"Сіз қайтадан линиядасыз (жаңа заказдар қабылдауға дайынсыз). 🚕",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Авто-аяқтау хабарламасын жіберуде қате: {e}")
    finally:
        await conn.close()


async def save_order_rating(order_id: int, rating: int):
    """Тапсырысқа қойылған жұлдызды (1-5) сақтау"""
    conn = await get_db_connection()
    try:
        await conn.execute("UPDATE orders SET rating = $1 WHERE order_id = $2", rating, order_id)
    finally:
        await conn.close()


async def save_order_review(order_id: int, review: str):
    """Тапсырысқа жазылған пікірді сақтау"""
    conn = await get_db_connection()
    try:
        await conn.execute("UPDATE orders SET review = $1 WHERE order_id = $2", review, order_id)
    finally:
        await conn.close()


async def change_user_mode(telegram_id: int, new_mode: str):
    """Қолданушының қазіргі режимін ауыстыру ('client' немесе 'driver')"""
    conn = await get_db_connection()
    try:
        await conn.execute("UPDATE users SET current_mode = $1 WHERE telegram_id = $2", new_mode, telegram_id)
    finally:
        await conn.close()