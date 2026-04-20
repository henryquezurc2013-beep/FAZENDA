from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

SQLALCHEMY_DATABASE_URL = "sqlite:///./rebanho.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)


@event.listens_for(engine, "connect")
def _configurar_sqlite(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=MEMORY")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_fazenda_id(request: Request) -> int:
    fid = (
        request.headers.get("X-Fazenda-ID")
        or request.query_params.get("fazenda_id")
        or "1"
    )
    try:
        return int(fid)
    except (ValueError, TypeError):
        return 1


def _migrate():
    """Apply additive schema migrations for existing databases."""
    migrations = [
        # Legacy migrations
        "ALTER TABLE animais ADD COLUMN valor_compra REAL",
        "ALTER TABLE animais ADD COLUMN custo_kg REAL",
        "ALTER TABLE animais ADD COLUMN custo_arroba REAL",
        "ALTER TABLE piquetes ADD COLUMN coordenadas TEXT",
        "ALTER TABLE piquetes ADD COLUMN cor_mapa TEXT DEFAULT '#2E7D32'",
        "ALTER TABLE piquetes ADD COLUMN icone_mapa TEXT DEFAULT '🌿'",
        # Multi-fazenda migrations
        "ALTER TABLE animais ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE pesagens ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE sanidade ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE inseminacoes ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE plano_nutricional ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE lancamento_racao ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE estoque_suplemento ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE pastos ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE piquetes ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE manejo_pastagem ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE lotes ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE lote_animais ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE chuva ADD COLUMN fazenda_id INTEGER DEFAULT 1",
        "ALTER TABLE adubacao_pastagem ADD COLUMN fazenda_id INTEGER DEFAULT 1",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(__import__('sqlalchemy').text(sql))
                conn.commit()
            except Exception:
                pass  # column already exists


def create_tables():
    from models import (  # noqa: F401
        Animal, Pesagem, Sanidade, Inseminacao,
        Compra, Venda, Despesa, Pessoa, Config,
        Fazenda,
    )
    Base.metadata.create_all(bind=engine)
    _migrate()
