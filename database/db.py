import aiosqlite
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot

# База файла жобаның ішінде "taxi_bot.db" деген атаумен автоматты түрде құрылады
DB_PATH = "database/taxi_bot.db"


async def init_db():
    """Деректер базасын және қажетті кестелерді құру функциясы"""
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Пайдаланушылар кестесі (Клиенттер мен Таксистердің ортақ базасы)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                is_client INTEGER DEFAULT 0,  -- Клиент ретінде тіркелген бе? (1=Иә, 0=Жоқ)
                is_driver INTEGER DEFAULT 0,  -- Таксист ретінде тіркелген бе? (1=Иә, 0=Жоқ)
                current_mode TEXT DEFAULT 'client', -- Қазіргі активті режимі ('client' немесе 'driver')
                registration_date TEXT
            )
        """)

        # 2. Таксистердің қосымша мәліметтер кестесі
        await db.execute("""
            CREATE TABLE IF NOT EXISTS drivers (
                telegram_id INTEGER PRIMARY KEY,
                car_model TEXT NOT NULL,     -- Көлік маркасы (Машинасы)
                car_number TEXT NOT NULL,    -- Көлік нөмірі
                subscription_start TEXT,
                subscription_end TEXT,       -- Абоненттік төлем бітетін күн (YYYY-MM-DD)
                is_online INTEGER DEFAULT 0,  -- Линияда ма? (0 = Жоқ, 1 = Иә)
                registration_date TEXT,
                FOREIGN KEY (telegram_id) REFERENCES users (telegram_id) ON DELETE CASCADE
            )
        """)

        # 3. Заказдар кестесі (🌟 order_type бағаны қосылды)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                driver_id INTEGER,           -- Басында бос болады, таксист алғанда толтырылады
                from_address TEXT NOT NULL,   -- Қай жерден
                to_address TEXT NOT NULL,     -- Қай жерге
                price INTEGER NOT NULL,       -- Заказ бағасы
                status TEXT NOT NULL DEFAULT 'waiting', -- Мәртебесі: waiting, accepted, completed, cancelled
                order_type TEXT DEFAULT 'local',        -- 🌟 ЖАҢА: 'local' (ауыл іші) немесе 'intercity' (қала)
                created_at TEXT NOT NULL,     -- Заказ берілген уақыт
                accepted_at TEXT,
                rating INTEGER DEFAULT 0,
                review TEXT,
                FOREIGN KEY (client_id) REFERENCES users (telegram_id),
                FOREIGN KEY (driver_id) REFERENCES drivers (telegram_id)
            )
        """)

        # Өзгерістерді сақтау
        await db.commit()


# --- КӨМЕКШІ ФУНКЦИЯЛАР ---

async def register_user(telegram_id: int, full_name: str, phone_number: str, role_to_add: str):
    """Жаңа қолданушыны тіркеу немесе бар қолданушыға жаңа рөл (статус) қосу"""
    async with aiosqlite.connect(DB_PATH) as db:
        reg_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        # UPSERT (ON CONFLICT) әдісі: адам базада бұрыннан болса, телефон мен атын жаңартып аламыз
        await db.execute("""
            INSERT INTO users (telegram_id, full_name, phone_number, is_client, is_driver, current_mode, registration_date) 
            VALUES (?, ?, ?, 0, 0, 'client', ?)
            ON CONFLICT(telegram_id) DO UPDATE SET 
            full_name = excluded.full_name,
            phone_number = excluded.phone_number
        """, (telegram_id, full_name, phone_number, reg_date))

        # Содан кейін рөліне қарай статусын жаңартамыз
        if role_to_add == 'client':
            await db.execute("UPDATE users SET is_client = 1, current_mode = 'client' WHERE telegram_id = ?", (telegram_id,))
        elif role_to_add == 'driver':
            await db.execute("UPDATE users SET is_driver = 1, current_mode = 'driver' WHERE telegram_id = ?", (telegram_id,))

        await db.commit()


async def register_driver(telegram_id: int, car_model: str, car_number: str):
    """Жаңа таксисті көлік мәліметтерімен және тіркелген күнімен базаға сақтау"""
    async with aiosqlite.connect(DB_PATH) as db:
        reg_date = datetime.now().strftime("%Y-%m-%d %H:%M")
        await db.execute(
            """INSERT OR REPLACE INTO drivers 
            (telegram_id, car_model, car_number, subscription_end, is_online, registration_date) 
            VALUES (?, ?, ?, NULL, 0, ?)""",
            (telegram_id, car_model, car_number, reg_date)
        )
        await db.commit()


async def get_user(telegram_id: int):
    """Қолданушының базада бар-жоғын және ролін тексеру"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            return await cursor.fetchone()


async def get_driver(telegram_id: int):
    """Таксист туралы толық мәлімет алу (Жазылымын тексеру үшін керек)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM drivers WHERE telegram_id = ?", (telegram_id,)) as cursor:
            return await cursor.fetchone()


async def update_driver_subscription(telegram_id: int, days: int):
    """Таксистке берілген күн санын қосу (Жазылымды жаңарту)"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Басталуы - қазіргі уақыт, бітуі - қазіргі уақыт + берілген күн
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

        # Кестедегі екі бағанды да жаңартамыз
        await db.execute(
            "UPDATE drivers SET subscription_start = ?, subscription_end = ? WHERE telegram_id = ?",
            (start_date, end_date, telegram_id)
        )
        await db.commit()


async def check_driver_subscription(telegram_id: int) -> bool:
    """Таксистің белсенді жазылымы бар-жоғын тексеру (True/False)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT subscription_end FROM drivers WHERE telegram_id = ?", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                end_date = datetime.strptime(row[0], "%Y-%m-%d").date()
                return end_date >= datetime.now().date()
    return False


async def update_order_status(order_id: int, status: str):
    """Заказдың статусын жаңарту (мысалы: 'completed')"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status = ? WHERE order_id = ?", (status, order_id))
        await db.commit()


async def set_driver_online_status(telegram_id: int, is_online: int):
    """Таксисті линияға шығару (1) немесе түсіру (0)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE drivers SET is_online = ? WHERE telegram_id = ?", (is_online, telegram_id))
        await db.commit()


# 🌟 ТҮЗЕТІЛДІ: order_type параметрі қосылды (әдепкі бойынша 'local')
async def create_order(client_id: int, from_address: str, to_address: str, price: int, order_type: str = 'local') -> int:
    """Жаңа заказды базаға сақтап, оның order_id нөмірін қайтарады"""
    async with aiosqlite.connect(DB_PATH) as db:
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = await db.execute(
            "INSERT INTO orders (client_id, from_address, to_address, price, order_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, from_address, to_address, price, order_type, created_at)
        )
        await db.commit()
        return cursor.lastrowid


async def get_online_drivers() -> list:
    """Қазір линияда тұрған таксистердің ID тізімін алу"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT telegram_id FROM drivers WHERE is_online = 1") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def get_available_drivers() -> list:
    """Онлайн тұрған, бірақ қазір активті заказы ЖОҚ (бос) таксистерді алу"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT d.telegram_id 
            FROM drivers d
            WHERE d.is_online = 1 
              AND d.telegram_id NOT IN (
                  SELECT driver_id FROM orders 
                  WHERE status IN ('accepted', 'arrived', 'in_progress', 'payment_pending')
                  AND driver_id IS NOT NULL
              )
        """) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def assign_order_to_driver(order_id: int, driver_id: int, final_price: int) -> tuple:
    """Заказды таксистке бекіту және қабылданған уақытты жазу"""
    async with aiosqlite.connect(DB_PATH) as db:
        accepted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor = await db.execute(
            """UPDATE orders 
               SET driver_id = ?, price = ?, status = 'accepted', accepted_at = ? 
               WHERE order_id = ? AND status = 'waiting'""",
            (driver_id, final_price, accepted_at, order_id)
        )
        await db.commit()
        return cursor.rowcount > 0, accepted_at


# 🌟 ТҮЗЕТІЛДІ: o.order_type соңына қосылды (индекс 6 болады, ескі кодтар бұзылмайды)
async def get_order_details(order_id: int):
    """Заказ бен оған қатысты клиенттің толық мәліметін алу"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT o.from_address, o.to_address, o.price, u.full_name, u.phone_number, o.client_id, o.order_type 
            FROM orders o
            JOIN users u ON o.client_id = u.telegram_id
            WHERE o.order_id = ?
        """, (order_id,)) as cursor:
            return await cursor.fetchone()


async def get_general_statistics():
    """Бастыққа арналған жалпы статистиканы алу"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE is_client = 1") as c:
            clients_count = (await c.fetchone())[0]

        async with db.execute("SELECT COUNT(*) FROM drivers") as c:
            drivers_count = (await c.fetchone())[0]

        today = datetime.now().strftime("%Y-%m-%d")
        async with db.execute("SELECT COUNT(*) FROM orders WHERE created_at LIKE ?", (f"{today}%",)) as c:
            orders_today = (await c.fetchone())[0]

        return clients_count, drivers_count, orders_today


async def get_recent_orders(limit: int = 5):
    """Соңғы бірнеше заказдың тізімін алу"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
                "SELECT order_id, from_address, to_address, price, status FROM orders ORDER BY order_id DESC LIMIT ?",
                (limit,)
        ) as cursor:
            return await cursor.fetchall()


async def get_waiting_orders() -> list:
    """Күту режимінде тұрған барлық белсенді заказдарды алу"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT o.order_id, o.from_address, o.to_address, o.price, u.full_name, u.phone_number 
            FROM orders o
            JOIN users u ON o.client_id = u.telegram_id
            WHERE o.status = 'waiting'
        """) as cursor:
            return await cursor.fetchall()


async def cancel_order_by_client(order_id: int) -> bool:
    """Клиент тапсырысты жойғанда қолданылады"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE orders SET status = 'cancelled' WHERE order_id = ? AND status = 'waiting'",
            (order_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_all_drivers_admin() -> list:
    """Админ үшін барлық таксистердің деректерін алу"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT 
                u.full_name, 
                u.phone_number, 
                d.car_model, 
                d.car_number, 
                IFNULL(d.registration_date, 'Белгісіз') as registration_date, 
                IFNULL(d.subscription_start, 'Жоқ') as sub_start_date, 
                IFNULL(d.subscription_end, 'Жоқ') as sub_end_date, 
                COUNT(CASE WHEN o.status LIKE '%completed%' THEN 1 END) as completed_orders, 
                d.is_online 
            FROM users u
            JOIN drivers d ON u.telegram_id = d.telegram_id
            LEFT JOIN orders o ON o.driver_id = u.telegram_id
            WHERE u.is_driver = 1
            GROUP BY u.telegram_id
        """) as cursor:
            return await cursor.fetchall()


async def get_all_clients_admin() -> list:
    """Админ үшін барлық клиенттердің деректерін алу"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT 
                u.full_name, 
                u.phone_number, 
                IFNULL(u.registration_date, 'Жоқ') as registration_date, 
                COUNT(CASE WHEN o.status LIKE '%completed%' THEN 1 END) as completed_orders 
            FROM users u
            LEFT JOIN orders o ON o.client_id = u.telegram_id
            WHERE u.is_client = 1
            GROUP BY u.telegram_id
        """) as cursor:
            return await cursor.fetchall()


async def get_all_orders_admin() -> list:
    """Админ үшін барлық заказдарды алу (Баға мен пікір қосылған нұсқа)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT 
                o.order_id, 
                IFNULL(c.full_name, 'Өшірілген қолданушы') as client_name, 
                IFNULL(d.full_name, 'Ізделуде...') as driver_name,
                o.from_address, 
                o.to_address, 
                o.price, 
                o.status,
                IFNULL(o.rating, 0) as rating,   
                IFNULL(o.review, '') as review   
            FROM orders o
            LEFT JOIN users c ON o.client_id = c.telegram_id
            LEFT JOIN users d ON o.driver_id = d.telegram_id
            ORDER BY o.order_id DESC LIMIT 50
        """) as cursor:
            return await cursor.fetchall()


# 🌟 ТҮЗЕТІЛДІ: timeout_seconds параметрі қосылды (әдепкі бойынша 600 секунд)
async def auto_cancel_order_after_timeout(order_id: int, bot: Bot, timeout_seconds: int = 600):
    """Заказ белгіленген уақыт ішінде аяқталмаса, оны автоматты түрде жою фондық функциясы"""
    await asyncio.sleep(timeout_seconds)
    minutes = timeout_seconds // 60  # Студентке/жүргізушіге минут түрінде көрсету үшін

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT status, client_id, driver_id FROM orders WHERE order_id = ?",
                              (order_id,)) as cursor:
            row = await cursor.fetchone()

            if row and row[0] == 'accepted':
                await db.execute("UPDATE orders SET status = 'cancelled' WHERE order_id = ?", (order_id,))
                await db.commit()

                client_id, driver_id = row[1], row[2]

                try:
                    await bot.send_message(
                        chat_id=client_id,
                        text=f"❌ <b>№{order_id} Тапсырыс жойылды.</b>\nТаксист {minutes} минут ішінде аяқтап үлгермеді."
                    )
                    await bot.send_message(
                        chat_id=driver_id,
                        text=f"❌ <b>№{order_id} Тапсырыс уақыты бітті!</b>\nСіз тапсырысты {minutes} минут ішінде аяқтамадыңыз. Ол автоматты түрде жойылды."
                    )
                except Exception:
                    pass


async def save_order_rating(order_id: int, rating: int):
    """Тапсырысқа қойылған жұлдызды (1-5) сақтау"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET rating = ? WHERE order_id = ?", (rating, order_id))
        await db.commit()

async def save_order_review(order_id: int, review: str):
    """Тапсырысқа жазылған пікірді сақтау"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET review = ? WHERE order_id = ?", (review, order_id))
        await db.commit()

async def change_user_mode(telegram_id: int, new_mode: str):
    """Қолданушының қазіргі режимін ауыстыру ('client' немесе 'driver')"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET current_mode = ? WHERE telegram_id = ?", (new_mode, telegram_id))
        await db.commit()