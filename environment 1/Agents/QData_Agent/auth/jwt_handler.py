import os
import json
import time
import uuid
import base64
import jwt
from config import (
    IS_PROD, KMS_KEY_ID, JWT_SECRET,
    ISSUER, AUDIENCE, ACCESS_TTL
)

kms = None
if IS_PROD:
    import boto3
    kms = boto3.client("kms")

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

# ── KMS signing (prod) ────────────────────────────────────────────────────────
def _sign_kms(message: bytes) -> bytes:
    resp = kms.sign(
        KeyId            = KMS_KEY_ID,
        Message          = message,
        MessageType      = "RAW",
        SigningAlgorithm = "RSASSA_PKCS1_V1_5_SHA_256"
    )
    return resp["Signature"]

def _build_jwt_kms(payload: dict) -> str:
    header = {"alg": "RS256", "typ": "JWT", "kid": KMS_KEY_ID.split("/")[-1]}
    h      = b64url(json.dumps(header, separators=(",", ":")).encode())
    p      = b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig    = _sign_kms(f"{h}.{p}".encode())
    return f"{h}.{p}.{b64url(sig)}"

# ── Local signing (dev) ───────────────────────────────────────────────────────
def _build_jwt_local(payload: dict) -> str:
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

# ── Generate service token ────────────────────────────────────────────────────
def generate_service_token(
    user_id:  str,
    email:    str  = "",
    metadata: dict = {},
) -> str:
    iat     = int(time.time())
    payload = {
        "iss":  ISSUER,
        "aud":  AUDIENCE,
        "sub":  user_id,
        "email": email,
        "type": "service",
        "iat":  iat,
        "exp":  iat + ACCESS_TTL,
        "jti":  str(uuid.uuid4()),
        **metadata,
    }
    if IS_PROD:
        return _build_jwt_kms(payload)
    return _build_jwt_local(payload)

# ── Verify service token ──────────────────────────────────────────────────────
def verify_service_token(token: str) -> dict:
    if IS_PROD:
        pub_key = kms.get_public_key(KeyId=KMS_KEY_ID)["PublicKey"]
        return jwt.decode(
            token, pub_key,
            algorithms = ["RS256"],
            audience   = AUDIENCE,
            issuer     = ISSUER,
        )
    return jwt.decode(
        token, JWT_SECRET,
        algorithms = ["HS256"],
        audience   = AUDIENCE,
        issuer     = ISSUER,
    )

# ── Verify user token (issued by Lambda auth) ─────────────────────────────────
def verify_user_token(token: str) -> dict:
    if IS_PROD:
        pub_key = kms.get_public_key(KeyId=KMS_KEY_ID)["PublicKey"]
        return jwt.decode(
            token, pub_key,
            algorithms = ["RS256"],
            audience   = "ecs-chat-server",
            issuer     = ISSUER,
        )
    return jwt.decode(
        token, JWT_SECRET,
        algorithms = ["HS256"],
    )
