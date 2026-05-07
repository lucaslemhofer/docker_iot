import asyncio, ssl, logging
import aiomqtt
from environs import Env

# Configuracion de como se muestra la informacion
logging.basicConfig(format='%(asctime)s - %(taskName)s - %(levelname)s: %(message)s', level=logging.INFO, datefmt='%d/%m/%Y %H:%M:%S')

# Corrutinas para procesar cada topico por separado
async def atenderTopico1(mensaje):
    logging.info(f"{mensaje}")

async def atenderTopico2(mensaje):
    logging.info(f"{mensaje}")

# Corrutina para el incremento del contador cada 3s
async def incrementar(estado):
    while True:
        await asyncio.sleep(3)
        estado["contador"] += 1

# Corrutina para publicar el estado cada 5s
async def publicar(client, estado, topico):
    while True:
        await asyncio.sleep(5)
        await client.publish(topico, payload=str(estado["contador"]))

async def main():

    env = Env()
    env.read_env() #lee el archivo con las variables. por defecto .env
    topico1 = env("TOPICO_1")
    topico2 = env("TOPICO_2")
    t_contador = env("TOPICO_CONTADOR")
    estado = {"contador": 0}

    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    tls_context.verify_mode = ssl.CERT_REQUIRED
    tls_context.check_hostname = True
    tls_context.load_default_certs()

    async with aiomqtt.Client(
        env("SERVIDOR"),
        port=8883,
        tls_context=tls_context,
    ) as client:
        
        logging.info(f"Se conectó al broker: {env('SERVIDOR')}") # debug
        # Suscripciones   
        await client.subscribe(topico1)
        await client.subscribe(topico2)
        
        logging.info(f"Suscrito a: {topico1} y {topico2}") # debug

        asyncio.create_task(incrementar(estado))
        asyncio.create_task(publicar(client, estado, t_contador), name="Publicación")

        logging.info("Esperando mensajes") # debug
        async for message in client.messages:
            mensaje = message.payload.decode("utf-8")
            # Derivamos a corrutinas segun el topico
            if message.topic.matches(topico1):
                asyncio.create_task(atenderTopico1(mensaje), name=f"TÓPICO: {topico1}")
            elif message.topic.matches(topico2):
                asyncio.create_task(atenderTopico2(mensaje), name=f"TÓPICO: {topico2}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Fin de la comunicación.")
        
        
