#!/bin/sh

foreman start -m enrollment=3,primary=1,secondary=1,tertiary=1,krakend=1,dynamodb=1

# This command runs the SMTP server in debugging mode
python -m aiosmtpd -n -d 