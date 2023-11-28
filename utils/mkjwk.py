#!/usr/bin/env python

import os
import sys
import json

from jwcrypto import jwk


def usage():
    program = os.path.basename(sys.argv[0])
    print(f"Usage: {program} KEY_ID...", file=sys.stderr)


def generate_keys(key_ids):
    keys = [jwk.JWK.generate(kid=key_id, kty="RSA", alg="RS256") for key_id in key_ids]
    exported_keys = [
        key.export(private_key=private) for key in keys for private in [False, True]
    ]
    keys_as_json = [json.loads(exported_key) for exported_key in exported_keys]
    jwks = {"keys": keys_as_json}
    output = json.dumps(jwks, indent=4)
    print(output)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        usage()
        sys.exit(1)

    generate_keys(sys.argv[1:])