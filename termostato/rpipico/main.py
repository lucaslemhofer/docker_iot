# Importacion de librerias y herramientas
from mqtt_as import MQTTClient  #Importa el cliente para hablar con el idioma MQTT
from mqtt_local import config   #Carga los datos de WIFI y servidor
import uasyncio as asyncio      #Multitarea asincrona
import dht, machine             #Herramientas para el sensor y los pines fisicos
import ujson 

#Obtencion de la MAC del Raspberry Pi Pico W/2W
#Codigo prveniente de la datasheet de Raspberry Pi Pico W https://pip-assets.raspberrypi.com/categories/686-raspberry-pi-pico-w/documents/RP-008257-DS-1-connecting-to-the-internet-with-pico-w.pdf?disposition=inline
import network
import ubinascii
 
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
ID_DEVICE = ubinascii.hexlify(network.WLAN().config('mac'),':').decode()
#print(ID_DEVICE) # Verificacion de la mac

# Toma del sensor
d = dht.DHT22(machine.Pin(15))  #DHT22 conectado en el pin fisico 20/GP15 del RB Pi
# Pin relé
pinRele = machine.Pin(16, machine.Pin.OUT)  # Se establece como salida para comando del relé al pin fisico 21/GP16 
pinRele.value(1)                            # Seteo de pin del rele en 1 por seguridad

# Definicion global de los estados de actualizacion de variables, se inicializan como predeterminados 
estado = {
    "setpoint": 24.0,
    "periodo": 5,
    "modo": "auto",
    "rele": 1
}

# Funciones para guardar y cargar los datos
def guardarEstado():
    try:
        with open("estado.json", "w") as f:
            ujson.dump(estado, f)
        print("Estado guardado")
    except:
        print("Error al guardar")

def cargarEstado():
    global estado
    try:
        with open("estado.json", "r") as f:
            estado = ujson.load(f)
        print("Estado cargado\nEstado inicial: ", estado)
        
    except:
        print("No existe archivo previo. Usando datos por defecto", estado)
    
async def destelloLed():
    led = machine.Pin("LED", machine.Pin.OUT)

    for i in range(10):
        i += 1
        led.toggle()
        await asyncio.sleep(1)
    led.off()  

def controlRele(temp):
    if estado["modo"] == "auto":
        if temp > estado["setpoint"]:
            pinRele.value(0)
            estado["rele"] = 0
        else:
            pinRele.value(1)
            estado["rele"] = 1
    elif estado["modo"] == "manual":
        pinRele.value(estado["rele"])

# Receptor de mensajes 
async def messages(client):
    async for topic, msg, retained in client.queue:
        mensaje = msg.decode().strip().strip('"').lower() # Normalizacion
        topico = topic.decode()
        print('Topico = {} -> Valor = {}'.format(topico, mensaje))

        if topico == f"{ID_DEVICE}/setpoint":
            estado["setpoint"] = float(mensaje)
            guardarEstado()
            print("Setpoint actualizado")

        elif topico == f"{ID_DEVICE}/periodo":
            estado["periodo"] = int(mensaje)
            guardarEstado()
            print("Periodo actualizado")

        elif topico == f"{ID_DEVICE}/modo":
            if mensaje == "manual" or mensaje == "auto":
                print("Modo anterior: {}".format(estado["modo"]))
                estado["modo"] = mensaje
                guardarEstado()
                print("Modo actualizado")
                print("Modo actual: {}".format(estado["modo"]))
            else:
                print("Modo ingresado no valido. Por favor reintente")

        elif topico == f"{ID_DEVICE}/rele":
            if int(mensaje) == 0 or int(mensaje) == 1:
                estado["rele"] = int(mensaje)
                guardarEstado()
            else:
                print("Estado de relé no valido. Por favor reintente")

        elif topico == f"{ID_DEVICE}/destello":
            asyncio.create_task(destelloLed())
            print("Destello de LED")

# Esta funcion se queda esperando a que llegue algun mensaje en al cola, es el encargado de la comunicacion entrante

# Gestor de conexion
async def up(client):  # Respond to connectivity being (re)established
    while True:
        await client.up.wait()  # Wait on an Event
        client.up.clear()
        print("Conectado con exito")
        # Se suscribe a los diferentes topicos
        await client.subscribe(f"{ID_DEVICE}/setpoint", 0)
        await client.subscribe(f"{ID_DEVICE}/periodo", 0)
        await client.subscribe(f"{ID_DEVICE}/destello", 0)
        await client.subscribe(f"{ID_DEVICE}/modo", 0)
        await client.subscribe(f"{ID_DEVICE}/rele", 0) 
# Solo se activa cuando client.up cambia, se encarga del renovar las suscripciones

# Lectura y envio
async def sensor(client):
    while True:
        try:
            d.measure()
            temperatura = d.temperature()
            humedad = d.humidity()
            datos = {
                "temperatura": temperatura,
                "humedad": humedad,
                "setpoint": estado["setpoint"],
                "periodo": estado["periodo"],       
                "modo": estado["modo"]        
            }
            controlRele(temperatura)
            envio_datos = ujson.dumps(datos)
            await client.publish(ID_DEVICE, envio_datos, qos=1)

        except OSError:
            print("Error: No se pudo leer el sensor.")
        
        await asyncio.sleep(estado["periodo"]) 
#Encargado de recolectar los datos.
#Cada valor contenido en periodo envia los datos sensados por el DHT22, enviandolos al servidor

async def main(client):
    cargarEstado()
    await client.connect()  #Se conecta al servidor
    await asyncio.sleep(2)  # Give broker time

    # Lanzamos todas las tareas al mismo tiempo
    asyncio.create_task(messages(client))
    asyncio.create_task(up(client))  
    print("Sistema iniciado. Monitoreando sensor")
    await sensor(client)

# Configuracion
config['queue_len'] = 10    #Tamaño del buzon de mensajes
config['ssl'] = True

# Set up client/arranque del sistema
MQTTClient.DEBUG = True  # Optional
client = MQTTClient(config)
try:
    asyncio.run(main(client))
finally:
    client.close()
    asyncio.new_event_loop()
