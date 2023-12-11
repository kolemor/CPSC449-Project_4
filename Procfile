enrollment: uvicorn enrollment.enrollment:app --host 0.0.0.0 --port $PORT --reload
primary: bin/litefs mount -config etc/primary.yml
secondary: bin/litefs mount -config etc/secondary.yml
tertiary: bin/litefs mount -config etc/tertiary.yml
krakend: echo ./etc/krakend.json | entr -nrz krakend run --config etc/krakend.json --port $PORT
dynamodb: java -Djava.library.path=./DynamoDBLocal_lib -jar DynamoDBLocal.jar -sharedDb --port $PORT
notification: uvicorn notification.notification:app --host 0.0.0.0 --port $PORT --reload
email-consumer: python consumer/email_consumer.py
webhook-consumer: python consumer/webhook_consumer.py
aiosmtpd: python -m aiosmtpd -n -d