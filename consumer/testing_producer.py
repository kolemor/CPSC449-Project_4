import pika
import json
import sys

class_data = {"name": "CPSC 332", "id": 1}
webhook = "https://smee.io/AHsFDRRzOn3QtCg"
email = "edwinperaza@cu.fullerton.edu"

message = {
    "class_name": class_data["name"],
    "message": "You have been enrolled in " + class_data["name"] + " by the registrar",
    "webhook_url": webhook,
    "email": email,
}
message = json.dumps(message)
#subscription_details = sub.get_subscription(next_student, class_id)
# message = "You have been enrolled in " + class_data["name"] + " by the registrar"
connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
channel = connection.channel()

channel.exchange_declare(exchange='enrollment_notifications', exchange_type='fanout')
channel.basic_publish(exchange='enrollment_notifications', routing_key='', body=message, properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent))
print(f" [x] Sent {message}")
connection.close()