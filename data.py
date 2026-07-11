#ps aux | grep data.py
#nohup /home/pi/tesis_env/bin/python3 /home/pi/DATALOGGER/data.py &
import paho.mqtt.client as mqtt
import json
import csv
from datetime import datetime

# --- CONFIGURACIÓN MQTT ---
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TOPIC = "tesis/proano/huerto/datos"
ARCHIVO_CSV = 'datos_tesis_v5_metricas_completas.csv'

# --- COLUMNAS (Añadidas las nuevas métricas) ---
COLUMNAS = [
    "Fecha_Hora", "Tipo_Mensaje", "ID_Nodo", "Msg_ID", 
    "Paquetes_Perdidos", "Perdida_%", "Hum_Local_%", 
    "Hum_Global_%", "Urgencia_Riego", "Estado_CNP", "Valvula", 
    "Temp_C", "Luz_%", "Estres_Evap", "Nivel_Tanque_%", 
    "Vecinos_Red", "Alerta_Sensor", "Alerta_Valvula",
    "Latencia_Subasta_ms", "Error_Cuadratico_Consenso", 
    "Violacion_Exclusion_Mutua", "Tiempo_Recuperacion_s", "Consumo_Estimado_mAh"
]

# --- DICCIONARIOS DE MEMORIA PARA MÉTRICAS ---
qos_tracker = {}
ultimo_clima_conocido = {
    "Temp_C": "N/A", "Luz_%": "N/A", 
    "Estres_Evap": "N/A", "Nivel_Tanque_%": "N/A"
}

# Memoria para las nuevas métricas
estado_valvulas_red = {}
tiempos_subasta = {} # Guarda el gw_millis cuando inicia un cfp
tiempos_falla = {} # Guarda el datetime cuando un nodo falla
ultima_lectura_tiempo = {} # Para calcular el consumo energético (Delta t)

def inicializar_csv():
    try:
        with open(ARCHIVO_CSV, mode='x', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(COLUMNAS)
            print(f"📁 Archivo {ARCHIVO_CSV} creado. ¡Listo para medir el rendimiento de la red!")
    except FileExistsError:
        print(f"📁 Archivo {ARCHIVO_CSV} ya existe. Se añadirán los datos al final.")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"🌐 Conectado a HiveMQ exitosamente.")
        client.subscribe(MQTT_TOPIC)
    else:
        print(f"❌ Error de conexión MQTT. Código: {rc}")

def on_message(client, userdata, msg):
    payload = msg.payload.decode('utf-8')
    try:
        datos = json.loads(payload)
        procesar_datos(datos)
    except json.JSONDecodeError:
        pass 

def procesar_datos(datos):
    global qos_tracker, ultimo_clima_conocido, estado_valvulas_red
    global tiempos_subasta, tiempos_falla, ultima_lectura_tiempo

    if "tipo" not in datos:
        return
        
    tipo = datos["tipo"]
    node_id = datos.get("id")
    msg_id = datos.get("msgID", "N/A") 
    gw_millis = datos.get("gw_millis", 0)
    hora_actual_dt = datetime.now()
    hora_actual = hora_actual_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # Preparar fila base
    fila = {col: "N/A" for col in COLUMNAS}
    fila["Fecha_Hora"] = hora_actual
    fila["Tipo_Mensaje"] = tipo
    fila["ID_Nodo"] = node_id if node_id else "N/A"
    fila["Msg_ID"] = msg_id
    
    # 1. QoS Tracking (Mantenemos tu lógica)
    if msg_id != "N/A" and node_id is not None:
        if node_id not in qos_tracker:
            qos_tracker[node_id] = {"last_id": msg_id, "lost": 0, "total_received": 1}
        else:
            expected_id = qos_tracker[node_id]["last_id"] + 1
            if msg_id > expected_id:
                qos_tracker[node_id]["lost"] += (msg_id - expected_id)
            elif msg_id < qos_tracker[node_id]["last_id"]:
                qos_tracker[node_id] = {"last_id": msg_id, "lost": 0, "total_received": 1}
            
            qos_tracker[node_id]["last_id"] = msg_id
            qos_tracker[node_id]["total_received"] += 1
            
        fila["Paquetes_Perdidos"] = qos_tracker[node_id]["lost"]
        fila["Perdida_%"] = round((qos_tracker[node_id]["lost"] / (qos_tracker[node_id]["lost"] + qos_tracker[node_id]["total_received"])) * 100, 2)

    # 2. PROCESAMIENTO POR TIPO DE MENSAJE
    if tipo == "clima": 
        ultimo_clima_conocido["Temp_C"] = datos.get("temp", "N/A")
        ultimo_clima_conocido["Luz_%"] = datos.get("luz", "N/A")
        ultimo_clima_conocido["Estres_Evap"] = round(datos.get("estres_evap", 0), 2) if "estres_evap" in datos else "N/A"
        ultimo_clima_conocido["Nivel_Tanque_%"] = datos.get("nivel_tanque", "N/A")
        fila.update(ultimo_clima_conocido)
        print(f"🌤️ Clima actualizado.")
        print(f"🌤️ NODO RECURSOS -> Temp: {ultimo_clima_conocido['Temp_C']}°C | Luz: {ultimo_clima_conocido['Luz_%']}% | Tanque: {ultimo_clima_conocido['Nivel_Tanque_%']}%")
        return # No guardamos línea en CSV para no ensuciarlo, solo actualizamos el clima

    elif tipo == "cfp":
        # Inicia la medición de latencia de subasta
        tiempos_subasta["activa"] = gw_millis
        return # No guardamos línea en CSV para no ensuciarlo, solo guardamos el tiempo

    elif tipo == "winner":
        # Subasta terminada, calculamos latencia
        if "activa" in tiempos_subasta:
            latencia = gw_millis - tiempos_subasta["activa"]
            print(f"⏱️ ¡Subasta resuelta! Latencia: {latencia} ms")
            fila["Latencia_Subasta_ms"] = latencia
            del tiempos_subasta["activa"] # Limpiamos la memoria
        return # Solo guardaremos la latencia en la próxima línea de consenso

    elif tipo == "consenso":
        hum_local = datos.get("hum_local", 0)
        hum_global = datos.get("hum_global", 0)
        valvula = datos.get("valvula", 0)
        
        fila["Hum_Local_%"] = hum_local
        fila["Hum_Global_%"] = round(hum_global, 2)
        fila["Urgencia_Riego"] = round(datos.get("urgencia", 0), 2)
        fila["Estado_CNP"] = datos.get("estado_cnp", "N/A")
        fila["Valvula"] = valvula
        fila["Vecinos_Red"] = datos.get("vecinos", "N/A")
        fila.update(ultimo_clima_conocido)
        
        # --- MÉTRICA: ERROR RMS (Error Cuadrático) ---
        if hum_local != -1.0: # Solo si el sensor sirve
            fila["Error_Cuadratico_Consenso"] = round((hum_local - hum_global) ** 2, 4)
        else:
            fila["Error_Cuadratico_Consenso"] = "N/A"

        # --- MÉTRICA: EXCLUSIÓN MUTUA ---
        estado_valvulas_red[node_id] = valvula
        valvulas_abiertas_simultaneas = sum(estado_valvulas_red.values())
        if valvulas_abiertas_simultaneas > 1:
            fila["Violacion_Exclusion_Mutua"] = "SI"
            print("🚨 ¡PELIGRO! Violación de Exclusión Mutua. Múltiples válvulas abiertas.")
        else:
            fila["Violacion_Exclusion_Mutua"] = "NO"

        # --- MÉTRICA: TIEMPO DE RECUPERACIÓN (FAILSAFE) ---
        alerta_sensor = datos.get("sensor_error", False) or (hum_local == -1.0)
        fila["Alerta_Sensor"] = alerta_sensor
        fila["Alerta_Valvula"] = datos.get("alerta_valvula", False)

        if alerta_sensor:
            if node_id not in tiempos_falla:
                tiempos_falla[node_id] = hora_actual_dt # Empieza el cronómetro
        else:
            # Si el sensor se recuperó (o la red se estabilizó) y estaba fallando
            if node_id in tiempos_falla:
                tiempo_recuperacion = (hora_actual_dt - tiempos_falla[node_id]).total_seconds()
                fila["Tiempo_Recuperacion_s"] = round(tiempo_recuperacion, 2)
                del tiempos_falla[node_id] # Detenemos el cronómetro

        # --- MÉTRICA: ESTIMACIÓN DE CONSUMO ENERGÉTICO ---
        if node_id in ultima_lectura_tiempo:
            delta_t_segundos = (hora_actual_dt - ultima_lectura_tiempo[node_id]).total_seconds()
            consumo_esp32_mA = 100 # Promedio con WiFi/Mesh activo
            consumo_valvula_mA = 500 if valvula == 1 else 0
            consumo_total_mAh = ((consumo_esp32_mA + consumo_valvula_mA) * delta_t_segundos) / 3600
            fila["Consumo_Estimado_mAh"] = round(consumo_total_mAh, 6)
        
        ultima_lectura_tiempo[node_id] = hora_actual_dt

        print(f"💧 Nodo {node_id} | Hum: {hum_local}% | Valvula: {valvula} | Error_Consenso²: {fila['Error_Cuadratico_Consenso']}")
        ##print(f"💧 Nodo {node_id} | Hum: {hum_local}% | Valvula: {valvula} | Temp: {ultimo_clima_conocido['Temp_C']}°C | Tanque: {ultimo_clima_conocido['Nivel_Tanque_%']}%")

    else:
        return # Cualquier otro mensaje se ignora

    # Guardar en CSV
    with open(ARCHIVO_CSV, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([fila[col] for col in COLUMNAS])

if __name__ == '__main__':
    inicializar_csv()
    client = mqtt.Client(client_id="PythonRecolector_Tesis", protocol=mqtt.MQTTv311)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        print("Intentando conectar a broker.hivemq.com...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever() 
    except KeyboardInterrupt:
        print("\n🛑 Recolección detenida por el usuario.")
        client.disconnect()
    except Exception as e:
        print(f"\n❌ Error: {e}")