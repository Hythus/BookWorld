import os
import secrets
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Charge les variables du fichier .env (notamment API_TOKEN)
load_dotenv()

DB_PATH = Path(__file__).resolve().parent / "database" / "bookworld.db"
API_TOKEN = os.getenv("API_TOKEN")

app = FastAPI(title="BookWorld API")

# Déclare l'authentification par Bearer Token (ajoute le bouton "Authorize" dans /docs)
security = HTTPBearer(auto_error=False)


def verifier_token(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    """Vérifie que le token envoyé dans l'en-tête Authorization correspond à API_TOKEN."""
    if not API_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="API_TOKEN non configuré dans le fichier .env.",
        )

    if credentials is None or not secrets.compare_digest(credentials.credentials, API_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="Token manquant ou invalide.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/health")
def health():
    """Vérifie si l'API et la base de données sont opérationnelles (route publique)."""
    if not DB_PATH.exists():
        return {"status": "error", "message": "Base de données introuvable"}
    return {"status": "ok", "message": "API opérationnelle"}


@app.get("/sales-by-country")
def get_sales_by_country(
    country_code: str | None = None,
    _token=Depends(verifier_token),
):
    """Retourne les ventes agrégées par pays (route protégée par Bearer Token)."""
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="Base de données introuvable. Lancez pipeline.py d'abord.",
        )

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        if country_code:
            code = country_code.strip().upper()
            lignes = conn.execute(
                "SELECT * FROM sales_by_country WHERE country_code = ?;",
                (code,),
            ).fetchall()

            if not lignes:
                raise HTTPException(
                    status_code=404,
                    detail=f"Pays '{code}' introuvable.",
                )
        else:
            lignes = conn.execute(
                "SELECT * FROM sales_by_country ORDER BY total_revenue_eur DESC;"
            ).fetchall()

    return [dict(ligne) for ligne in lignes]
