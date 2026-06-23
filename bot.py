import asyncio
import logging
import os  #
from aiogram.types import BotCommand
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database.db import init_db
from handlers import client, driver, admin
from aiohttp import web  #

logging.basicConfig(level=logging.INFO)

# 🌟 Render өшіріп тастамас үшін кішкентай веб-бетше құрамыз
async def handle(request):
    return web.Response(text="Бот 24/7 белсенді жұмыс істеп тұр!")

async def main():
    await init_db()
    logging.info("Деректер базасы сәтті қосылды!")

    # 🌟 Веб-серверді іске қосу (Render портын қабылдау үшін)
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Веб-сервер {port} портында іске қосылды.")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    await bot.set_my_commands([
        BotCommand(command="start", description="Ботты қайта іске қосу / Тіркелу"),
        BotCommand(command="admin", description="Бастық панелі (Тек әкімшіге)")
    ])

    dp.include_router(admin.router)
    dp.include_router(client.router)
    dp.include_router(driver.router)

    logging.info("Бот іске қосылды және хабарламаларды күтуде...")

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот тоқтатылды.")