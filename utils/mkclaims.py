#!/usr/bin/env python

import os
import sys
import json
import datetime


def usage():
    program = os.path.basename(sys.argv[0])
    print(f"Usage: {program} USERNAME USER_ID ROLE...", file=sys.stderr)


def expiration_in(minutes):
    creation = datetime.datetime.now(tz=datetime.timezone.utc)
    expiration = creation + datetime.timedelta(minutes=minutes)
    return creation, expiration


def generate_claims(username, user_id, roles):
    _, exp = expiration_in(20)

    claims = {
        "aud": "krakend.local.gd",
        "iss": "auth.local.gd",
        "sub": username,
        "jti": str(user_id),
        "roles": roles,
        "exp": int(exp.timestamp()),
    }
    token = {
        "access_token": claims,
        "refresh_token": claims,
        "exp": int(exp.timestamp()),
    }

    output = json.dumps(token, indent=4)
    print(output)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        usage()
        sys.exit(1)

    generate_claims(sys.argv[1], sys.argv[2], sys.argv[3:])