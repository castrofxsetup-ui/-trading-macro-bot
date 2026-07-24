import discord
from discord.ext import commands, tasks
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

# --- БЛОК БЕСПЛАТНОГО ХОСТИНГА (ОБХОД ОГРАНИЧЕНИЙ RENDER) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Macro Bot is active!")

def run_web_server():
    server = HTTPServer(('0.0.0.0', 10000), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_web_server, daemon=True).start()
# -----------------------------------------------------------

# НАСТРОЙКИ БОТА
TARGET_CHANNEL_ID = 1528319066513604688  # ID вашей новостной ветки
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.guild_scheduled_events = True  # Критично для отслеживания стримов

bot = commands.Bot(command_prefix="!", intents=intents)

# Базы данных в памяти для исключения дубликатов уведомлений
notified_news = set()
notified_events_60m = set()
notified_events_15m = set()

@bot.event
async def on_ready():
    print(f"Макро-бот {bot.user.name} успешно запущен!")
    check_macro_and_events.start()  # Запуск циклической проверки

# ОСНОВНОЙ ТАЙМЕР ПРОВЕРКИ (срабатывает раз в 60 секунд)
@tasks.loop(seconds=60)
async def check_macro_and_events():
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        return

    now_utc = datetime.now(timezone.utc)

    # --- 1. БЛОК ЭКОНОМИЧЕСКОГО КАЛЕНДАРЯ (FOREX FACTORY) ---
    try:
        # Используем стабильный публичный XML фид календаря
        url = "https://forexfactory.com"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
        
        root = ET.fromstring(xml_data)
        
        for event in root.findall('event'):
            impact = event.find('impact').text
            if impact != "High":  # Фильтруем только КРАСНЫЕ новости
                continue
                
            title = event.find('title').text
            currency = event.find('currency').text  # Актив (USD, EUR и т.д.)
            date_str = event.find('date').text      # MM-DD-YYYY
            time_str = event.find('time').text      # HH:MM AM/PM
            
            # Парсим дату и время новости (фид Forex Factory отдает время в формате EST/EDT)
            # Для надежности приводим к объекту времени без привязки к зоне, учитывая сдвиг FF Нью-Йорк (-5/-4)
            # В данном алгоритме мы проверяем разницу относительно времени самого фида
            try:
                event_datetime = datetime.strptime(f"{date_str} {time_str}", "%m-%d-%Y %I:%M%p").replace(tzinfo=timezone(timedelta(hours=-5)))
            except Exception:
                continue

            # Проверяем, осталось ли до новости ровно от 29 до 31 минуты
            time_diff = event_datetime - now_utc
            event_id = f"{title}_{date_str}_{time_str}"

            if timedelta(minutes=29) <= time_diff <= timedelta(minutes=31) and event_id not in notified_news:
                # Форматируем красивый Embed по вашему шаблону
                embed = discord.Embed(
                    title="🚨 ВНИМАНИЕ! КРАСНЫЕ НОВОСТИ",
                    color=0xff0000,
                    timestamp=datetime.now()
                )
                embed.add_field(name="Ожидаемые события:", value=title, inline=False)
                embed.add_field(name="Актив:", value=f"**{currency}**", inline=True)
                embed.add_field(name="Время выхода:", value=f"⏰ {time_str} (Нью-Йорк)", inline=True)
                embed.add_field(name="Важность:", value="🔴 **HIGH IMPACT**", inline=False)
                embed.set_footer(text="Публикация через 30 минут")

                # Публикация с тегом @everyone
                await channel.send(content="@everyone Срочное предупреждение о волатильности!", embed=embed)
                notified_news.add(event_id)
                
    except Exception as e:
        print(f"Ошибка парсинга Forex Factory: {e}")

    # --- 2. БЛОК МОНИТОРИНГА СТРИМОВ / МЕРОПРИЯТИЙ СЕРВЕРА ---
    for guild in bot.guilds:
        try:
            # Получаем список запланированных ивентов на сервере
            events = await guild.fetch_scheduled_events()
            for event in events:
                if event.status != discord.EventStatus.scheduled:
                    continue
                
                time_to_start = event.start_time - now_utc
                event_url = f"https://discord.com{guild.id}/{event.id}"

                # Уведомление за 60 минут
                if timedelta(minutes=58) <= time_to_start <= timedelta(minutes=62) and event.id not in notified_events_60m:
                    await channel.send(
                        f"@everyone 📢 **До начала стрима остался 1 час!**\n"
                        f"📝 Мероприятие: **{event.name}**\n"
                        f"🔗 Ссылка на подключение: {event_url}"
                    )
                    notified_events_60m.add(event.id)

                # Уведомление за 15 минут
                if timedelta(minutes=13) <= time_to_start <= timedelta(minutes=17) and event.id not in notified_events_15m:
                    await channel.send(
                        f"@everyone 🚨 **Стрим начнется через 15 минут! Готовьте графики.**\n"
                        f"📝 Мероприятие: **{event.name}**\n"
                        f"🔗 Зайти на стрим: {event_url}"
                    )
                    notified_events_15m.add(event.id)
        except Exception as e:
            print(f"Ошибка проверки мероприятий сервера {guild.name}: {e}")

# Перед запуском вставьте токен вашего бота ниже вместо ВАШ_ТОКЕН
import os
bot.run(os.getenv("DISCORD_TOKEN"))
