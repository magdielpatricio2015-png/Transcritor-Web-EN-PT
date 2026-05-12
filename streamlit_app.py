import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import streamlit as st
from docx import Document
from faster_whisper import WhisperModel


APP_TITLE = "Transcritor EN-PT"
VERSION = "v2.0"
OUTPUT_DIR = Path("outputs")
COOKIES_FILE = Path("cookies.txt")

SUPPORTED_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".opus",
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
}

YOUTUBE_DOMAINS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
}


@dataclass
class Segmento:
    start: float
    end: float
    text: str


def aplicar_estilo() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🎙️", layout="wide")
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 2rem;
                max-width: 1120px;
            }
            .status-box {
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: .85rem 1rem;
                background: #f9fafb;
                color: #374151;
                margin: .75rem 0 1rem;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def carregar_modelo(
    model_name: str,
    device: str,
    compute_type: str,
    local_only: bool,
) -> WhisperModel:
    return WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
        local_files_only=local_only,
    )


def limpar_texto(nome: str) -> str:
    return re.sub(r"\s+", " ", nome).strip()


def nome_seguro(nome: str) -> str:
    stem = Path(nome).stem
    stem = re.sub(r"[^\w\-. ]+", "", stem, flags=re.UNICODE)
    stem = re.sub(r"\s+", "_", stem).strip("._-")
    return stem or "transcricao"

