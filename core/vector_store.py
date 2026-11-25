import chromadb
from chromadb.config import Settings as ChromaSettings
from config.settings import BASE_DIR

def get_collection():
    client = chromadb.PersistentClient(path=str(BASE_DIR / "data" / "chroma"),
                                       settings=ChromaSettings(anonymized_telemetry=False))
    return client.get_or_create_collection("educite")
