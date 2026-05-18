
# lambda_function.py
import os
import json
import boto3
import uuid
import base64
import time
import datetime as dt
import secrets
import jwt

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# ========================= ENVIRONMENT =========================
USERS_TABLE    = os.environ["USERS_TABLE"]
SESSIONS_TABLE = os.environ["SESSIONS_TABLE"]
KMS_KEY_ID     = os.environ["KMS_KEY_ID"]

ISSUER         = os.environ.get("ISSUER", "https://api.myapp.com")
AUDIENCE       = os.environ.get("AUDIENCE", "ecs-chat-server")
ACCESS_TTL     = int(os.environ.get("ACCESS_TTL", "900"))         # 15 min
REFRESH_TTL    = int(os.environ.get("REFRESH_TTL", "2592000"))    # 30 days
TICKET_TTL     = int(os.environ.get("TICKET_TTL", "60"))          # 1 min

dynamodb = boto3.resource("dynamodb")
kms       = boto3.client("kms")
users_tbl = dynamodb.Table(USERS_TABLE)
sessions_tbl = dynamodb.Table(SESSIONS_TABLE)

ph = PasswordHasher(  # Production Argon2id settings
    time_cost=3,
    memory_cost=64 * 1024,   # 64 MB RAM
    parallelism=2,
    hash_len=32,
    salt_len=16
)

# ========================= UTILITIES =========================

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def sign_kms(message: bytes) -> bytes:
    """Sign JWT header.payload using AWS KMS (private key never leaves KMS)."""
    resp = kms.sign(
        KeyId=KMS_KEY_ID,
        Message=message,
        MessageType="RAW",
        SigningAlgorithm="RSASSA_PKCS1_V1_5_SHA_256"
    )
    return resp["Signature"]

def sign_jwt(payload: dict) -> str:
    header = {"alg": "RS256", "typ": "JWT", "kid": KMS_KEY_ID.split("/")[-1]}

    h = b64url(json.dumps(header, separators=(",", ":")).encode())
    p = b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()

    sig = sign_kms(signing_input)
    s = b64url(sig)
    return f"{h}.{p}.{s}"

def now() -> int:
    return int(time.time())

def secure_random_token(n=48) -> str:
    return secrets.token_urlsafe(n)

def hash_refresh_token(raw: str, sid: str) -> str:
    # One-way hash of refresh token + session id to prevent replay
    return base64.urlsafe_b64encode(
        boto3.utils.sha256(f"{sid}:{raw}".encode())
    ).decode()

# ========================= TOKEN GENERATION =========================

def create_access_token(user_id: str, email: str, roles: list, perms: list):
    iat = now()
    exp = iat + ACCESS_TTL

    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": user_id,
        "email": email,
        "roles": roles,
        "permissions": perms,
        "iat": iat,
        "exp": exp,
        "jti": str(uuid.uuid4())
    }
    return sign_jwt(payload), exp

def create_session_ticket(user_id: str):
    iat = now()
    exp = iat + TICKET_TTL

    payload = {
        "iss": ISSUER,
        "aud": "ecs-realtime-connect",
        "sub": user_id,
        "type": "session-ticket",
        "iat": iat,
        "exp": exp,
        "nonce": str(uuid.uuid4())
    }
    return sign_jwt(payload), exp

# ========================= CORE HANDLERS =========================

def signup(data):
    email = data["email"].lower()
    password = data["password"]

    hashed = ph.hash(password)

    users_tbl.put_item(
        Item={
            "email": email,
            "user_id": str(uuid.uuid4()),
            "pwd_hash": hashed,
            "status": "active",
            "created_at": dt.datetime.utcnow().isoformat() + "Z"
        },
        ConditionExpression="attribute_not_exists(email)"
    )

    return resp(201, {"message": "user_created"})

def login(data, ip, ua):
    email = data["email"].lower()
    password = data["password"]
    device = data.get("device_id", "")

    user = users_tbl.get_item(Key={"email": email}).get("Item")
    if not user or user["status"] != "active":
        return resp(401, {"error": "invalid_credentials"})

    try:
        ph.verify(user["pwd_hash"], password)
    except VerifyMismatchError:
        return resp(401, {"error": "invalid_credentials"})

    access_jwt, access_exp = create_access_token(
        user["user_id"], email, ["user"], ["chat:read", "chat:write"]
    )

    refresh_raw = secure_random_token()
    session_id = str(uuid.uuid4())
    refresh_hash = hash_refresh_token(refresh_raw, session_id)

    sessions_tbl.put_item(
        Item={
            "session_id": session_id,
            "user_id": user["user_id"],
            "refresh_hash": refresh_hash,
            "issued_at": now(),
            "expires_at": now() + REFRESH_TTL,
            "revoked": False,
            "device_id": device,
            "ip": ip or "",
            "ua": ua or ""
        }
    )

    ticket, ticket_exp = create_session_ticket(user["user_id"])

    return resp(200, {
        "accessToken": access_jwt,
        "accessTokenExpiresAt": access_exp,
        "refreshToken": refresh_raw,
        "sessionId": session_id,
        "sessionTicket": ticket,
        "sessionTicketExpiresAt": ticket_exp
    })

def refresh(event, data, ip, ua):
    # expects Authorization: Bearer <refresh>
    auth = event["headers"].get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return resp(401, {"error": "missing_refresh_token"})

    raw_refresh = auth.split(" ")[1].strip()
    session_id = data["session_id"]

    sess = sessions_tbl.get_item(Key={"session_id": session_id}).get("Item")
    if not sess or sess["revoked"] or now() > sess["expires_at"]:
        return resp(401, {"error": "invalid_session"})

    expected = sess["refresh_hash"]
    got = hash_refresh_token(raw_refresh, session_id)
    if not secrets.compare_digest(expected, got):
        sessions_tbl.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET revoked = :r",
            ExpressionAttributeValues={":r": True}
        )
        return resp(401, {"error": "token_mismatch"})

    # rotate refresh token
    new_raw = secure_random_token()
    new_hash = hash_refresh_token(new_raw, session_id)

    sessions_tbl.update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET refresh_hash=:h, ip=:ip, ua=:ua",
        ExpressionAttributeValues={
            ":h": new_hash,
            ":ip": ip or "",
            ":ua": ua or ""
        }
    )

    # new access token
    user_id = sess["user_id"]
    access_jwt, access_exp = create_access_token(
        user_id, "", ["user"], ["chat:read", "chat:write"]
    )

    return resp(200, {
        "accessToken": access_jwt,
        "accessTokenExpiresAt": access_exp,
        "refreshToken": new_raw,
        "sessionId": session_id
    })

def ticket(event):
    claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    user_id = claims["sub"]

    t, exp = create_session_ticket(user_id)
    return resp(200, {
        "sessionTicket": t,
        "sessionTicketExpiresAt": exp
    })

# ========================= ROUTER =========================

def handler(event, context):
    path = event["rawPath"]
    body = json.loads(event.get("body") or "{}")
    method = event["requestContext"]["http"]["method"]

    ip = event["requestContext"]["http"].get("sourceIp")
    ua = event["headers"].get("user-agent")

    if path == "/auth/signup" and method == "POST":
        return signup(body)

    if path == "/auth/login" and method == "POST":
        return login(body, ip, ua)

    if path == "/auth/refresh" and method == "POST":
        return refresh(event, body, ip, ua)

    if path == "/auth/ticket" and method == "POST":
        return ticket(event)

    return resp(404, {"error": "not_found"})

# ========================= RESPONSE UTIL =========================

def resp(status, obj):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(obj)
    }
