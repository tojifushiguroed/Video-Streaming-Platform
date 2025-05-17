import paho.mqtt.client as mqtt
import json
from datetime import datetime
import time

MQTT_BROKER = "broker.hivemq.com"  # Kendi broker adresiniz
MQTT_PORT = 1883
MQTT_TOPICS = [("durum/kamera1/#", 0), ("analiz/kamera1/#", 0)] # Abone olunacak topicler
OUTPUT_JSON_FILE = "mqtt_output.json"
mqtt_data = []

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT broker'a bağlandı.")
        client.subscribe(MQTT_TOPICS)
    else:
        print(f"MQTT broker'a bağlanma hatası: {rc}")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        timestamp = datetime.now().isoformat()
        mqtt_data.append({"topic": msg.topic, "payload": json.loads(payload), "timestamp": timestamp})
        print(f"Topic: {msg.topic}, Mesaj Kaydedildi.") # Terminale sadece kaydetme bilgisini yazdır

        # İsteğe bağlı: Veriyi anında dosyaya yazma (her mesajda dosyaya yazmak performansı etkileyebilir)
        # with open(OUTPUT_JSON_FILE, 'w') as f:
        #     json.dump(mqtt_data, f, indent=4)

    except Exception as e:
        print(f"Mesaj işleme hatası: {e}")

def write_to_json():
    while True:
        time.sleep(4) # Belirli aralıklarla dosyaya yaz (performans için daha iyi)
        if mqtt_data:
            with open(OUTPUT_JSON_FILE, 'w') as f:
                json.dump(mqtt_data, f, indent=4)
            print(f"Veri '{OUTPUT_JSON_FILE}' dosyasına yazıldı.")
            mqtt_data.clear() # Yazdıktan sonra listeyi temizle (isteğe bağlı)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, 60)

import threading
write_thread = threading.Thread(target=write_to_json)
write_thread.daemon = True
write_thread.start()

client.loop_forever()