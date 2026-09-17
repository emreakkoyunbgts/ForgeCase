"""Explicit one-time model provisioning; requests never download model weights."""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import services  # Load root .env before selecting the model.
from sentence_transformers import SentenceTransformer

if __name__ == '__main__':
    SentenceTransformer(os.getenv('LIBRARIAN_MODEL', 'sentence-transformers/all-MiniLM-L6-v2'))
    print('Librarian model cache is ready.')
