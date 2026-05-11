import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import streamlit as st
from docx import Document
from faster_whisper import WhisperModel


APP_TITLE = "Transcritor"
VERSION = "v1.1"
OUTPUT_DIR = Path("outputs")
SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
    ".mp4", ".mkv", ".mov", ".avi", ".webm",
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
            .hero {
                padding: 1rem 1.25rem;
                border-radius: 14px;
                background: linear-gradient(135deg, #111827, #1f2937);
                color: white;
                margin-bottom: 1rem;
            }
            .hero strong {
                display: block;
                font-size: 1.05rem;
                margin-bottom: .25rem;
            }
            .hero span {
                color: #d1d5db;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def carregar_modelo(model_name: str, device: str, compute_type: str, local_only: bool) -> WhisperModel:
    return WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
        local_files_only=local_only,
    )


def salvar_upload(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Formato não suportado: {suffix}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return Path(tmp.name)


def transcrever(
    audio_path: Path,
    model_name: str,
    device: str,
    compute_type: str,
    local_only: bool,
) -> tuple[list[Segmento], list[str], object]:
    model = carregar_modelo(model_name, device, compute_type, local_only)

    raw_segments, info = model.transcribe(
        str(audio_path),
        language="en",
        vad_filter=True,
        beam_size=5,
    )

    segmentos: list[Segmento] = []
    linhas: list[str] = []

    for segment in raw_segments:
        texto = segment.text.strip()
        if not texto:
            continue

        segmentos.append(Segmento(start=float(segment.start), end=float(segment.end), text=texto))
        linhas.append(texto)

    if not segmentos:
        raise RuntimeError("Nenhum trecho de fala foi detectado no arquivo.")

    return segmentos, linhas, info


@st.cache_resource(show_spinner=False)
def garantir_argos_en_pt() -> str:
    """
    Garante que o Argos Translate e o pacote inglês -> português estejam disponíveis.

    Em ambientes como JetHub/Streamlit Cloud, o sistema pode reiniciar sem manter
    pacotes baixados manualmente. Por isso esta função verifica e instala quando necessário.
    """
    try:
        import argostranslate.package
        import argostranslate.translate
    except ImportError as exc:
        raise RuntimeError(
            "Argos Translate não está instalado. Adicione 'argostranslate' no requirements.txt."
        ) from exc

    installed_languages = argostranslate.translate.get_installed_languages()
    from_lang = next((lang for lang in installed_languages if lang.code == "en"), None)
    to_lang = next((lang for lang in installed_languages if lang.code == "pt"), None)

    if from_lang is not None and to_lang is not None:
        try:
            from_lang.get_translation(to_lang)
            return "Tradução EN -> PT já disponível."
        except Exception:
            pass

    argostranslate.package.update_package_index()
    available_packages = argostranslate.package.get_available_packages()

    package = next(
        (
            pkg for pkg in available_packages
            if pkg.from_code == "en" and pkg.to_code == "pt"
        ),
        None,
    )

    if package is None:
        raise RuntimeError("Pacote EN -> PT não encontrado no índice do Argos.")

    package_path = package.download()
    argostranslate.package.install_from_path(package_path)

    return "Pacote de tradução EN -> PT instalado com sucesso."


def load_argos_translation():
    try:
        import argostranslate.translate
    except ImportError:
        return None, "Argos Translate não está instalado."

    installed_languages = argostranslate.translate.get_installed_languages()
    from_lang = next((lang for lang in installed_languages if lang.code == "en"), None)
    to_lang = next((lang for lang in installed_languages if lang.code == "pt"), None)

    if from_lang is None or to_lang is None:
        return None, "Pacote de tradução EN -> PT ainda não instalado."

    try:
        translator = from_lang.get_translation(to_lang)
    except Exception:
        return None, "Pacote de tradução EN -> PT encontrado, mas não pôde ser carregado."

    return translator, "Tradução EN -> PT disponível."


def instalar_argos_en_pt() -> str:
    garantir_argos_en_pt.clear()
    return garantir_argos_en_pt()


def translate_lines_argos(lines: Iterable[str]) -> list[str]:
    translator, status = load_argos_translation()

    if translator is None:
        raise RuntimeError(status)

    translated: list[str] = []
    for line in lines:
        translated.append(translator.translate(line).strip())

    return translated


def agrupar_paragrafos(
    segments: list[Segmento],
    lines: list[str],
    pause_seconds: float,
) -> list[str]:
    if not segments or not lines:
        return []

    paragraphs: list[str] = []
    current: list[str] = [lines[0]]

    for index in range(1, min(len(segments), len(lines))):
        pause = segments[index].start - segments[index - 1].end

        if pause >= pause_seconds:
            paragraphs.append(" ".join(current).strip())
            current = [lines[index]]
        else:
            current.append(lines[index])

    if current:
        paragraphs.append(" ".join(current).strip())

    return paragraphs


def format_srt_time(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours = milliseconds // 3_600_000
    milliseconds %= 3_600_000
    minutes = milliseconds // 60_000
    milliseconds %= 60_000
    secs = milliseconds // 1000
    millis = milliseconds % 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_srt(path: Path, segments: list[Segmento], lines: list[str] | None = None) -> None:
    with path.open("w", encoding="utf-8") as file:
        for index, segment in enumerate(segments, start=1):
            text = lines[index - 1] if lines and index - 1 < len(lines) else segment.text

            file.write(f"{index}\n")
            file.write(f"{format_srt_time(segment.start)} --> {format_srt_time(segment.end)}\n")
            file.write(f"{text.strip()}\n\n")


def write_txt(path: Path, title: str, paragraphs: list[str]) -> None:
    with path.open("w", encoding="utf-8") as file:
        file.write(f"{title}\n")
        file.write("=" * len(title))
        file.write("\n\n")
        file.write("\n\n".join(paragraphs))


def write_docx(
    path: Path,
    source_name: str,
    english_paragraphs: list[str],
    portuguese_paragraphs: list[str] | None,
) -> None:
    doc = Document()

    doc.add_heading("Transcrição e tradução", level=1)
    doc.add_paragraph(f"Arquivo original: {source_name}")
    doc.add_paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    if portuguese_paragraphs:
        doc.add_heading("Tradução em português", level=2)
        for paragraph in portuguese_paragraphs:
            doc.add_paragraph(paragraph)

    doc.add_heading("Transcrição em inglês", level=2)
    for paragraph in english_paragraphs:
        doc.add_paragraph(paragraph)

    doc.save(path)


def nome_seguro(nome: str) -> str:
    stem = Path(nome).stem
    stem = re.sub(r"[^\w\-. ]+", "", stem, flags=re.UNICODE)
    stem = re.sub(r"\s+", "_", stem).strip("._-")
    return stem or "transcricao"


def gerar_arquivos(
    source_name: str,
    segments: list[Segmento],
    english_lines: list[str],
    portuguese_lines: list[str] | None,
    pause_seconds: float,
) -> tuple[list[Path], str, str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    base = nome_seguro(source_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_DIR / f"{base}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    english_paragraphs = agrupar_paragrafos(segments, english_lines, pause_seconds)
    portuguese_paragraphs = (
        agrupar_paragrafos(segments, portuguese_lines, pause_seconds)
        if portuguese_lines is not None
        else None
    )

    created: list[Path] = []

    english_txt = out_dir / f"{base}_transcricao_en.txt"
    write_txt(english_txt, "Transcrição em inglês", english_paragraphs)
    created.append(english_txt)

    if portuguese_paragraphs is not None:
        pt_txt = out_dir / f"{base}_traducao_pt.txt"
        write_txt(pt_txt, "Tradução em português", portuguese_paragraphs)
        created.append(pt_txt)

    en_srt = out_dir / f"{base}_legenda_en.srt"
    write_srt(en_srt, segments)
    created.append(en_srt)

    if portuguese_lines is not None:
        pt_srt = out_dir / f"{base}_legenda_pt.srt"
        write_srt(pt_srt, segments, portuguese_lines)
        created.append(pt_srt)

    docx_path = out_dir / f"{base}_transcricao_traducao.docx"
    write_docx(docx_path, source_name, english_paragraphs, portuguese_paragraphs)
    created.append(docx_path)

    zip_path = out_dir / f"{base}_resultado.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in created:
            zf.write(path, arcname=path.name)

    preview_pt = "\n\n".join(portuguese_paragraphs or [])
    preview_en = "\n\n".join(english_paragraphs)
    return [zip_path] + created, preview_pt, preview_en


def limpar_texto_tamanho(nome: str) -> str:
    return re.sub(r"\s+", " ", nome).strip()


def main() -> None:
    aplicar_estilo()

    st.title(f"{APP_TITLE} {VERSION}")
    st.caption("Transcrição de áudio/vídeo em inglês, tradução para português e geração de legenda.")
    st.markdown(
        """
        <div class="hero">
            <strong>Transcritor online com instalação automática da tradução</strong>
            <span>Envie um arquivo, transcreva, traduza e baixe TXT, SRT, Word e ZIP.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Configuração")
        model_name = st.selectbox("Modelo Whisper", ["tiny", "base", "small", "medium"], index=1)
        device = st.selectbox("Dispositivo", ["cpu", "cuda"], index=0)
        compute_type = st.selectbox("Precisão", ["int8", "float16", "float32"], index=0)
        local_only = st.checkbox("Usar somente modelos já baixados", value=False)
        pause_seconds = st.slider("Pausa para parágrafo", 0.5, 5.0, 0.8, 0.1)
        traduzir = st.checkbox("Traduzir para português", value=True)
        instalar_auto = st.checkbox("Instalar tradução EN-PT automaticamente", value=True)

        if traduzir and instalar_auto:
            try:
                with st.spinner("Verificando tradução EN -> PT..."):
                    status_auto = garantir_argos_en_pt()
                st.caption(status_auto)
            except Exception as exc:
                st.warning(f"Tradução automática indisponível: {exc}")

        translator, argos_status = load_argos_translation()
        st.caption(argos_status)

        if translator is None and st.button("Instalar tradução EN-PT"):
            with st.spinner("Instalando pacote de tradução..."):
                try:
                    st.success(instalar_argos_en_pt())
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível instalar: {exc}")

    uploaded = st.file_uploader(
        "Envie um áudio ou vídeo em inglês",
        type=["mp3", "wav", "m4a", "aac", "flac", "ogg", "mp4", "mkv", "mov", "avi", "webm"],
    )

    if uploaded is None:
        st.info("Escolha um arquivo para começar.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Arquivo", limpar_texto_tamanho(uploaded.name)[:32])
    c2.metric("Tamanho", f"{uploaded.size / (1024 * 1024):.1f} MB")
    c3.metric("Modelo", model_name)

    if not st.button("Transcrever agora", type="primary", use_container_width=True):
        return

    temp_path: Path | None = None

    try:
        temp_path = salvar_upload(uploaded)

        with st.spinner("Carregando modelo e transcrevendo..."):
            segments, english_lines, info = transcrever(
                temp_path,
                model_name,
                device,
                compute_type,
                local_only,
            )

        portuguese_lines: list[str] | None = None
        traducao_falhou = False

        if traduzir:
            with st.spinner("Traduzindo para português..."):
                try:
                    portuguese_lines = translate_lines_argos(english_lines)
                except Exception as exc:
                    traducao_falhou = True
                    portuguese_lines = None
                    st.warning(
                        "A transcrição foi concluída, mas a tradução não pôde ser gerada. "
                        f"Motivo: {exc}"
                    )

        created, preview_pt, preview_en = gerar_arquivos(
            uploaded.name,
            segments,
            english_lines,
            portuguese_lines,
            pause_seconds,
        )

        if traducao_falhou:
            st.success("Transcrição concluída. Arquivos em inglês prontos para download.")
        else:
            st.success("Concluído. Arquivos prontos para download.")

        m1, m2, m3 = st.columns(3)
        m1.metric("Trechos", len(segments))
        m2.metric("Idioma", getattr(info, "language", "en"))
        m3.metric("Arquivos", len(created) - 1)

        zip_path = created[0]
        st.download_button(
            "Baixar tudo em ZIP",
            data=zip_path.read_bytes(),
            file_name=zip_path.name,
            mime="application/zip",
            use_container_width=True,
        )

        tab1, tab2, tab3 = st.tabs(["Português", "Inglês", "Arquivos"])

        with tab1:
            if preview_pt:
                st.text_area("Prévia da tradução", preview_pt, height=320)
            else:
                st.info("Tradução não gerada nesta execução.")

        with tab2:
            st.text_area("Prévia da transcrição", preview_en, height=320)

        with tab3:
            for path in created[1:]:
                mime = "application/octet-stream"

                if path.suffix in {".txt", ".srt"}:
                    mime = "text/plain"
                elif path.suffix == ".docx":
                    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

                st.download_button(
                    label=path.name,
                    data=path.read_bytes(),
                    file_name=path.name,
                    mime=mime,
                )

    except Exception as exc:
        st.error("Não foi possível concluir a transcrição.")
        st.exception(exc)

    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    main()
