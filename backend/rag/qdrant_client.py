from qdrant_client import QdrantClient

client = QdrantClient(
    url="http://127.0.0.1:6333"
)

print(client.get_collections())
