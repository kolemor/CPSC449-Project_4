import pika
import smtplib
from email.message import EmailMessage
import json

def email_callback(ch, method, properties, body):
    data = json.loads(body)
    to_address = data.get('email')
    message_text = data.get('message')

    # Create EmailMessage object
    msg = EmailMessage()
    msg.set_content(message_text)
    msg['Subject'] = f'Enrollment Notification for {data.get("class_name")}'
    msg['From'] = 'edwinperaza@csu.fullerton.edu'
    msg['To'] = to_address

    # Send email using smtplib
    # server = smtplib.SMTP('localhost', 8025)
    server = smtplib.SMTP('localhost')
    server.send_message(msg)
    server.quit()

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
channel.basic_consume(queue=queue_name, on_message_callback=email_callback, auto_ack=True)

# Start consuming messages
print('Email Notification Consumer is waiting for messages. To exit press CTRL+C')
channel.start_consuming()
