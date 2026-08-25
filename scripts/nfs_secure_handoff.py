#!/usr/bin/env python3
import argparse
import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def unb64(text: str) -> bytes:
    return base64.b64decode(text.encode('ascii'))


def encrypt(public_key_path: str, input_path: str, output_path: str):
    public_key = serialization.load_pem_public_key(Path(public_key_path).read_bytes())
    plaintext = Path(input_path).read_bytes()
    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, None)
    wrapped_key = public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    payload = {
        'version': 1,
        'alg': 'RSA-OAEP-SHA256+A256GCM',
        'wrapped_key': b64(wrapped_key),
        'nonce': b64(nonce),
        'ciphertext': b64(ciphertext),
    }
    Path(output_path).write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')


def decrypt(private_key_path: str, input_path: str, output_path: str):
    private_key = serialization.load_pem_private_key(Path(private_key_path).read_bytes(), password=None)
    payload = json.loads(Path(input_path).read_text(encoding='utf-8'))
    if payload.get('version') != 1:
        raise SystemExit('Unsupported secure handoff version')
    aes_key = private_key.decrypt(
        unb64(payload['wrapped_key']),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    plaintext = AESGCM(aes_key).decrypt(unb64(payload['nonce']), unb64(payload['ciphertext']), None)
    Path(output_path).write_bytes(plaintext)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)

    enc = sub.add_parser('encrypt')
    enc.add_argument('--public-key', required=True)
    enc.add_argument('--input', required=True)
    enc.add_argument('--output', required=True)

    dec = sub.add_parser('decrypt')
    dec.add_argument('--private-key', required=True)
    dec.add_argument('--input', required=True)
    dec.add_argument('--output', required=True)

    args = parser.parse_args()
    if args.command == 'encrypt':
        encrypt(args.public_key, args.input, args.output)
    else:
        decrypt(args.private_key, args.input, args.output)


if __name__ == '__main__':
    main()
