import ssl
import json
import time
import uuid
import paho.mqtt.client as mqtt


class BambuClient:
    def __init__(self, ip, access_code):
        self.ip = ip
        self.access_code = access_code
        self.client_id = f"printmind_{uuid.uuid4().hex[:8]}"
        self.topic = "device/request"

        self.client = mqtt.Client(client_id=self.client_id, protocol=mqtt.MQTTv311)
        self.client.username_pw_set("bblp", access_code)

        self.client.tls_set(cert_reqs=ssl.CERT_NONE)
        self.client.tls_insecure_set(True)

    def connect(self):
        self.client.connect(self.ip, 8883, 60)
        self.client.loop_start()
        time.sleep(1)

    def send_gcode(self, gcode_path):
        with open(gcode_path, "rb") as f:
            gcode_data = f.read()

        payload = {
            "print": {
                "sequence_id": str(uuid.uuid4()),
                "command": "project_file",
                "param": {
                    "file": gcode_data.decode("latin1"),
                    "name": "printmind_job.gcode"
                }
            }
        }

        self.client.publish(self.topic, json.dumps(payload))
        time.sleep(2)

    def start_print(self):
        payload = {
            "print": {
                "sequence_id": str(uuid.uuid4()),
                "command": "start"
            }
        }

        self.client.publish(self.topic, json.dumps(payload))
        time.sleep(2)

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()