from fastapi import Security, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Valida el token JWT de Supabase y retorna el UUID del usuario."""
    supabase_jwt_secret = os.environ.get("SUPABASE_JWT_SECRET")
    
    if not supabase_jwt_secret:
        # Check if we're likely outside of a properly loaded environment
        raise HTTPException(
            status_code=500, 
            detail="Error de configuración del servidor: SUPABASE_JWT_SECRET no configurado"
        )
        
    try:
        # Supabase uses HS256 by default
        payload = jwt.decode(
            credentials.credentials, 
            supabase_jwt_secret, 
            algorithms=["HS256"], 
            audience="authenticated"
        )
        return payload.get("sub") # UUID del usuario
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Sesión inválida.")
    except Exception:
        raise HTTPException(status_code=401, detail="Error de autenticación.")
