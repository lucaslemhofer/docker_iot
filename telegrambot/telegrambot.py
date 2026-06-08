from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import logging, os, asyncio, aiomysql, traceback, locale, ssl
import matplotlib.pyplot as plt
from io import BytesIO
import aiomqtt
import json

token = os.environ["TB_TOKEN"]

logging.basicConfig(format='%(asctime)s - TelegramBot - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# MAC del rpi pasada por variable de entorno, funciona como topico
DEVICE_ID = os.environ.get("DEVICE_ID")

clienteMqtt = None  # Variable global para almacenar el cliente MQTT

estadoPico={
    "temperatura": None,
    "humedad": None,
    "setpoint": None,
    "modo": None,
    "periodo": None
}

async def conexionMqtt():
    global clienteMqtt
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
                payload = message.payload.decode("utf-8")
                logging.info(f"Mensaje recibido en MQTT -> {message.topic}: {payload}")

                datos = json.loads(payload)
                estadoPico["temperatura"] = datos.get("temperatura")
                estadoPico["humedad"] = datos.get("humedad")
                estadoPico["setpoint"] = datos.get("setpoint")
                estadoPico["modo"] = datos.get("modo")
                estadoPico["periodo"] = datos.get("periodo")

# CORRUTINA PARA PUBLICAR EN MQTTS
async def publicarMqtt(subtopic, msg):
    if clienteMqtt:
        topic = f"{DEVICE_ID}/{subtopic}"
        await clienteMqtt.publish(topic, payload=str(msg))
        logging.info(f"Comando enviado a MQTT {topic}: {msg}")
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
    await context.bot.send_message(update.message.chat.id, text="Bienvenido al Bot "+ nombre + " " + apellido,reply_markup=ReplyKeyboardMarkup(kb),read_timeout=10, write_timeout=10)

async def setpoint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /setpoint [temperatura]\nEjemplo: /setpoint 25.5")
        await update.message.reply_text("La temperatura umbral actual es de " + str(estadoPico.get("setpoint")) + "°C.")
    else:
        valor = context.args[0].replace(',', '.')
        await publicarMqtt("setpoint", valor)
        await update.message.reply_text(f"Cambio de setpoint a {valor}°C")

async def periodo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: /periodo [segundos]\nEjemplo: /periodo 5")
        await update.message.reply_text("El periodo de medición actual es de " + str(estadoPico.get("periodo")) + " segundos.")
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
    if estadoPico.get("modo") != "manual":
        await update.message.reply_text("Modo actual AUTOMÁTICO. \nCambia al modo manual para controlar el relé.")
    else:
        await publicarMqtt("rele", "0") 
        await update.message.reply_text("Comando Relé ACTIVAR enviado.")

async def releOff(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if estadoPico.get("modo") != "manual":
        await update.message.reply_text("Modo actual AUTOMÁTICO. \nCambia al modo manual para controlar el relé.")
    else:
        await publicarMqtt("rele", "1")
        await update.message.reply_text("Comando Relé DESACTIVAR enviado.")

async def info(update: Update, context):
    await context.bot.send_message(update.message.chat.id, text="Este bot fue creado para el curso de IoT FIO por Lucas Lemhofer")

async def ayuda(update: Update, context):
    await context.bot.send_message(update.message.chat.id, text="Comandos disponibles:\n/start - Iniciar el bot\n/setpoint [temp] - Cambiar temperatura destino incluyendo como argumento la temperatura solicitada\n/periodo [seg] - Cambiar periodo de medicion inlcuyendo el tiempo de muestreo solicitado\n/destello - Hace parpadear un LED de la pico.\n/estado - Estado actual de las mediciones y configuraciones\n/info - Información del bot\n\nmodoManual - El usuario controla el rele con los comandos.\n/rele_on - Activar rele (modo manual)\n/rele_off - Desactivar rele (modo manual)\n\nmodoAuto - El termostato regula el rele según la temperatura sensada y setpoint.")

async def estado(update: Update, context):
    estado_texto = (
        f"Estado actual del termostato:\n"
        f"Temperatura: {estadoPico.get('temperatura')}°C\n"
        f"Humedad: {estadoPico.get('humedad')}%\n"
        f"Setpoint: {estadoPico.get('setpoint')}°C\n"
        f"Modo: {estadoPico.get('modo')}\n"
        f"Periodo de medición: {estadoPico.get('periodo')} segundos"
    )
    await update.message.reply_text(estado_texto)

    
async def medicion(update: Update, context):
    if update.message.text == "temperatura":
        valor = estadoPico.get("temperatura")
        if valor is not None:
            await update.message.reply_text(f"Temperatura actual: {valor}°C")
        else:
            await update.message.reply_text("No se ha recibido una medición de temperatura.")
    elif update.message.text == "humedad":
        valor = estadoPico.get("humedad")
        if valor is not None:
            await update.message.reply_text(f"Humedad actual: {valor}%")
        else:
            await update.message.reply_text("No se ha recibido una medición de humedad.")

async def post_init(application: Application):
    commands = [
        ("start", "Iniciar"),
        ("setpoint", "Cambiar temperatura destino"),
        ("periodo", "Cambiar periodo de medicion"),
        ("rele_on", "Activar relé"),
        ("rele_off", "Desactivar relé"),
        ("info", "Informacion del bot"),
        ("estado", "Estado actual de las mediciones y configuraciones"),
        ("ayuda", "Ayuda"),
    ]
    await application.bot.set_my_commands(commands)
    
    asyncio.create_task(conexionMqtt())

def main():
    application = Application.builder().token(token).post_init(post_init).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('setpoint', setpoint))
    application.add_handler(CommandHandler('periodo', periodo))
    application.add_handler(CommandHandler('rele_on', releOn))
    application.add_handler(CommandHandler('rele_off', releOff))
    application.add_handler(CommandHandler('info', info))
    application.add_handler(CommandHandler('estado', estado))
    application.add_handler(CommandHandler('ayuda', ayuda))
    application.add_handler(MessageHandler(filters.Regex("^(modoAuto|modoManual|destello)$"), modo))
    application.add_handler(MessageHandler(filters.Regex("^(temperatura|humedad)$"), medicion))


    application.run_polling()

if __name__ == '__main__':
    main()