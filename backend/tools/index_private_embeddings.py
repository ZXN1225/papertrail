"""Build an owner's private embedding index after authorization to send text to the provider."""

import argparse
import json

from app.config import get_settings
from app.embeddings.client import OpenAIEmbeddingClient
from app.private_documents import PrivateDocumentService
from app.storage.repository import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True)
    args = parser.parse_args()
    settings = get_settings()
    store = PaperStore(settings.resolved_data_storage_path)
    provider = OpenAIEmbeddingClient(settings)
    try:
        print(json.dumps(PrivateDocumentService(store).build_embeddings(args.user_id, provider)))
    finally:
        provider.close()


if __name__ == "__main__":
    main()
