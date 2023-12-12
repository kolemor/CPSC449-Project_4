#!/bin/sh

foreman start -m enrollment=3,primary=1,secondary=1,tertiary=1,krakend=1,dynamodb=1,notification=1,email-consumer=3,webhook-consumer=3,aiosmtpd=1
