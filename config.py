import os
from dotenv import load_dotenv

# .env файлынан мәліметтерді жүктеу
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# Егер ADMIN_ID бос болмаса, оны санға (integer) айналдырамыз
if ADMIN_ID:
    ADMIN_ID = int(ADMIN_ID)