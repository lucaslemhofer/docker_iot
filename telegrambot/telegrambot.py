from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import logging, os, asyncio, aiomysql, traceback, locale, ssl
import matplotlib.pyplot as plt
from io import BytesIO
import aiomqtt

token = os.environ["TB_TOKEN"]

logging.basicConfig(format='%(asctime)s - TelegramBot - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# MAC del rpi pasada por variable de entorno, funciona como topico
DEVICE_ID = os.environ.get("DEVICE_ID")

clienteMqtt = None  # Variable global para almacenar el cliente MQTT activo

async def conexionMqtt():
    global clienteMqtt
    # Configuración de TLS para MQTTS
    tls_context = ssl.create_default_context()
    
    async with aiomqtt.Client(
        os.environ["SERVIDOR"],
        username=os.environ["MQTT_USR"],
        password=os.environ["MQTT_PASS"],
        port=int(os.environ["PUERTO_MQTTS"]),
        tls_context=tls_context,
    ) as client:
        while True:
            clienteMqtt = client
            logging.info(f"Bot conectado a MQTTS en {os.environ['SERVIDOR']}:{os.environ['PUERTO_MQTTS']}")
            
            await client.subscribe(DEVICE_ID)
            
            async for message in client.messages:
                logging.info(f"Telegram detecta actividad de la pico")

# CORRUTINA PARA PUBLICAR EN MQTTS
async def publicarMqtt(subtopic, msg):
    if clienteMqtt:
        topic = f"{DEVICE_ID}/{subtopic}"
        await clienteMqtt.publish(topic, payload=str(msg))
        logging.info(f"Comando enviado a MQTT -> {topic}: {msg}")
        return True
    return False


# FUNCIONES DE TELEGRAM

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"Se conectó: " + str(update.message.from_user.id))
    if update.message.from_user.first_name:
        nombre=update.message.from_user.first_name
    else:
        nombre=""
    if update.message.from_user.last_name:
        apellido=update.message.from_user.last_name
    else:
        apellido=""
    kb = [["temperatura", "humedad"],["modoAuto", "modoManual"],["destello"]]
    await context.bot.send_message(update.message.chat.id, text="Bienvenido al Bot "+ nombre + " " + apellido,reply_markup=ReplyKeyboardMarkup(kb))

async def setpoint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /setpoint [temperatura]\nEjemplo: /setpoint 25.5")
    else:
        valor = context.args[0].replace(',', '.')
        await publicarMqtt("setpoint", valor)
        await update.message.reply_text(f"Cambio de setpoint a {valor}°C")

async def periodo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /periodo [segundos]\nEjemplo: /periodo 5")
    else:
        valor = context.args[0]
        await publicarMqtt("periodo", valor)
        await update.message.reply_text(f"Solicitado cambio de periodo a {valor}s")
    
async def modo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "modoAuto":
        await publicarMqtt("modo", "auto")
        await update.message.reply_text("Termostato cambiado a modo AUTOMÁTICO.")
    elif update.message.text == "modoManual":
        await publicarMqtt("modo", "manual")
        await update.message.reply_text("Termostato cambiado a modo MANUAL. \nAhora puedes usar /rele_on y /rele_off.")
    elif update.message.text == "destello":
        await publicarMqtt("destello", "true")
        await update.message.reply_text("Comando destello enviado a la pico.")

async def releOn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await publicarMqtt("rele", "0") 
    await update.message.reply_text("Comando Relé ACTIVAR (0) enviado.")

async def releOff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await publicarMqtt("rele", "1")
    await update.message.reply_text("Comando Relé DESACTIVAR (1) enviado.")

async def acercade(update: Update, context):
    await context.bot.send_message(update.message.chat.id, text="Este bot fue creado para el curso de IoT FIO")

async def ayuda(update: Update, context):
    await context.bot.send_message(update.message.chat.id, text="help me")

async def messi(update: Update, context):
    if context.args and context.args[0] == ' goat':
        await context.bot.send_animation(update.message.chat.id, "messisisisisi")
    else:  
        await context.bot.send_message(update.message.chat.id, text="🐐")

async def medicion(update: Update, context):
    sql = f"SELECT timestamp, {update.message.text} FROM mediciones ORDER BY timestamp DESC LIMIT 1"
    conn = await aiomysql.connect(host=os.environ["MARIADB_SERVER"], port=3306, user=os.environ["MARIADB_USER"], password=os.environ["MARIADB_USER_PASS"], db=os.environ["MARIADB_DB"])
    async with conn.cursor() as cur:
        await cur.execute(sql)
        r = await cur.fetchone()
        unidad = 'ºC' if update.message.text == 'temperatura' else '%'
        await context.bot.send_message(update.message.chat.id, text="La última {} es de {} {},\nregistrada a las {:%H:%M:%S %d/%m/%Y}".format(update.message.text, str(r[1]).replace('.',','), unidad, r[0]))
    conn.close()

async def graficos(update: Update, context):
    sql = f"""SELECT timestamp, {update.message.text.split()[1]} FROM (SELECT timestamp, {update.message.text.split()[1]}, ROW_NUMBER() OVER (ORDER BY id) AS rn FROM mediciones WHERE timestamp >= NOW() - INTERVAL 1 DAY AND sensor_id LIKE 'sensor_1') AS t WHERE rn % 2 = 0 ORDER BY timestamp;"""
    conn = await aiomysql.connect(host=os.environ["MARIADB_SERVER"], port=3306, user=os.environ["MARIADB_USER"], password=os.environ["MARIADB_USER_PASS"], db=os.environ["MARIADB_DB"])
    async with conn.cursor() as cur:
        await cur.execute(sql)
        filas = await cur.fetchall()
        fig, ax = plt.subplots(figsize=(7, 4))
        fecha, var = zip(*filas)
        ax.plot(fecha, var)
        ax.grid(True, which='both')
        ax.set_title(update.message.text, fontsize=14, verticalalignment='bottom')
        buffer = BytesIO()
        fig.tight_layout()
        fig.savefig(buffer, format='png')
        plt.close()
        buffer.seek(0)
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=buffer)
        buffer.close()
    conn.close()

async def post_init(application: Application):
    # Iniciamos el daemon de escucha MQTT
    asyncio.create_task(conexionMqtt())

def main():
    application = Application.builder().token(token).post_init(post_init).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('setpoint', setpoint))
    application.add_handler(CommandHandler('periodo', periodo))
    application.add_handler(CommandHandler('rele_on', releOn))
    application.add_handler(CommandHandler('rele_off', releOff))
    application.add_handler(CommandHandler('messi', messi))
    application.add_handler(CommandHandler('acercade', acercade))
    application.add_handler(CommandHandler('ayuda', ayuda))

    # Tus filtros existentes de mensajes de texto y regex
    application.add_handler(MessageHandler(filters.Regex("^(temperatura|humedad)$"), medicion))
    application.add_handler(MessageHandler(filters.Regex("^(gráfico temperatura|gráfico humedad)$"), graficos))
    application.add_handler(MessageHandler(filters.Regex("^(modoAuto|modoManual|destello)$"), modo))

    application.run_polling()

if __name__ == '__main__':
    main()