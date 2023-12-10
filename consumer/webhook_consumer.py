import pika
import httpx
import json

def webhook_callback(ch, method, properties, body):
    data = json.loads(body)
    webhook_url = data.get('webhook_url')
    message_text = data.get('message')

    try:
        response = httpx.post(webhook_url, json={'message': message_text})
        response.raise_for_status()
    except httpx.HTTPError as e:
        print(f"Error sending Webhook callback: {e}")

# Set up RabbitMQ connection and channel
connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()

# Declare a fanout exchange
channel.exchange_declare(exchange='enrollment_notifications', exchange_type='fanout')

# Declare a queue and bind it to the exchange
result = channel.queue_declare(queue='', exclusive=True)
queue_name = result.method.queue

channel.queue_bind(exchange='enrollment_notifications', queue=queue_name)

# Set up the consumer callback
channel.basic_consume(queue=queue_name, on_message_callback=webhook_callback, auto_ack=True)

# Start consuming messages
print('Webhook Callback Consumer is waiting for messages. To exit press CTRL+C')
channel.start_consuming()
