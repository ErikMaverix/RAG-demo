# backend/auth.py
from functools import lru_cache
from typing import Any, Dict

import os
import requests
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError


AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE")
ALGORITHMS = ["RS256"]

bearer_scheme = HTTPBearer(auto_error=True)


@lru_cache(maxsize=1)
def get_jwks() -> Dict[str, Any]:
    if not AUTH0_DOMAIN:
        raise RuntimeError("AUTH0_DOMAIN mangler")

    jwks_url = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"
    response = requests.get(jwks_url, timeout=10)
    response.raise_for_status()
    return response.json()


def verify_jwt_token(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
) -> Dict[str, Any]:
    if not AUTH0_DOMAIN or not AUTH0_AUDIENCE:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth0 er ikke konfigurert korrekt på serveren.",
        )

    token = credentials.credentials

    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ugyldig token-header.",
        )

    jwks = get_jwks()
    rsa_key = {}

    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            rsa_key = {
                "kty": key.get("kty"),
                "kid": key.get("kid"),
                "use": key.get("use"),
                "n": key.get("n"),
                "e": key.get("e"),
            }
            break

    if not rsa_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Fant ikke gyldig signeringsnøkkel.",
        )

    try:
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=ALGORITHMS,
            audience=AUTH0_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/",
        )
        return payload

    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token er utløpt.",
        )
    except JWTClaimsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token claims er ugyldige.",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kunne ikke validere token.",
        )
