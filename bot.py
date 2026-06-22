import asyncio
import logging
from aiogram.types import BotCommand
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database.db import init_db
from handlers import client, driver, admin

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    logging.info("Деректер базасы сәтті қосылды!")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # 🛠️ ЖАҢА ЖОЛДАР: Командаларды дайын опция (Меню батырмасы) жасау
    await bot.set_my_commands([
        BotCommand(command="start", description="Ботты қайта іске қосу / Тіркелу"),
        BotCommand(command="admin", description="Бастық панелі (Тек әкімшіге)")
    ])

    dp.include_router(client.router)
    dp.include_router(driver.router)
    dp.include_router(admin.router)

    logging.info("Бот іске қосылды және хабарламаларды күтуде...")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот тоқтатылды.")