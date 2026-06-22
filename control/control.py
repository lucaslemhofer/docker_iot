from flask import Flask, render_template, request, redirect, url_for, flash
from flask_mysqldb import MySQL
from werkzeug.middleware.proxy_fix import ProxyFix
import os, logging
import paho.mqtt.client as mqtt

logging.basicConfig(format='%(asctime)s - CONTROL - %(levelname)s - %(message)s', level=logging.INFO)

app = Flask(__name__)

app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

app.secret_key = os.environ.get("FLASK_SECRET_KEY") 
app.config["MYSQL_USER"] = os.environ.get("MYSQL_USER") 
app.config["MYSQL_PASSWORD"] = os.environ.get("MYSQL_PASSWORD")
app.config["MYSQL_DB"] = os.environ.get("MYSQL_DB") 
app.config["MYSQL_HOST"] = os.environ.get("MYSQL_HOST", "mariadb")
mysql = MySQL(app)

import paho.mqtt.publish as mqttpublish
import ssl

MQTT_BROKER = os.environ.get("SERVIDOR")
MQTT_PORT = int(os.environ.get("PUERTO_MQTTS"))
MQTT_USER = os.environ.get("MQTT_USR") 
MQTT_PASS = os.environ.get("MQTT_PASS") 


@app.route('/')
def index():
    datos = []
    try:
        cur = mysql.connection.cursor()
        cur.execute('SELECT * FROM nodos')
        datos = cur.fetchall()
        cur.close()
    except Exception as e:
        logging.error(f"Error fetching nodos: {e}")
        flash(f"Error de base de datos: {e}", "danger")
    return render_template('index.html', nodos=datos)

@app.route('/add_nodo', methods=['POST'])
def add_nodo():
    if request.method == 'POST':
        nombre = request.form['nombre'].strip()
        mac = request.form['mac'].strip()
        if not mac:
            flash('La dirección MAC no puede estar vacía.', 'danger')
            return redirect(url_for('index'))
            
        try:
            cur = mysql.connection.cursor()
            cur.execute("INSERT INTO nodos (nombre, mac) VALUES (%s, %s)", (nombre, mac))
            mysql.connection.commit()
            flash('Nodo agregado exitosamente', 'success')
            logging.info(f"Se agregó el nodo con MAC: {mac}")
            cur.close()
        except Exception as e:
            logging.error(f"Error al agregar nodo: {e}")
            flash(f'Error al agregar el nodo. Motivo: {e}', 'danger')
    return redirect(url_for('index'))

@app.route('/borrar/<string:id>', methods=['GET'])
def borrar_nodo(id):
    try:
        cur = mysql.connection.cursor()
        cur.execute('DELETE FROM nodos WHERE id = %s', (id,))
        mysql.connection.commit()
        flash('Nodo eliminado exitosamente', 'success')
        logging.info(f"Se eliminó el nodo con ID: {id}")
        cur.close()
    except Exception as e:
        logging.error(f"Error al eliminar nodo: {e}")
        flash(f'Error al eliminar el nodo: {e}', 'danger')
    return redirect(url_for('index'))

@app.route('/send_command', methods=['POST'])
def send_command():
    if request.method == 'POST':
        mac = request.form.get('mac')
        comando = request.form.get('comando')
        
        if not mac or not comando:
            flash('Debe seleccionar un nodo y un comando.', 'danger')
            return redirect(url_for('index'))
            
        topic = f"{mac}/{comando}"
        # Envia setpoint
        if comando == 'setpoint':
            try:
                payload = str(float(request.form.get('temperatura', '0')))
            except ValueError:
                flash('Valor de setpoint no válido.', 'danger')
                return redirect(url_for('index'))
       # Envia destello
        else:
            payload = "1"

        logging.info(f"Broker={MQTT_BROKER}")
        logging.info(f"Puerto={MQTT_PORT}")
        logging.info(f"Topic={topic}")
        logging.info(f"Payload={payload}")

        try:
            mqttpublish.single(topic, payload=payload, hostname=MQTT_BROKER, port=MQTT_PORT, auth={'username': MQTT_USER, 'password': MQTT_PASS}, tls={"tls_version": ssl.PROTOCOL_TLS_CLIENT})
            flash(f'Comando {comando} enviado al nodo {mac} con valor: {payload}', 'success')
            logging.info(f"Publicado a MQTT - Topic: {topic}, Payload: {payload}")
        except Exception as e:
            logging.error(f"Error al enviar MQTT: {e}")
            flash(f'Error al conectar/enviar a Mosquitto: {e}', 'danger')
            
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)