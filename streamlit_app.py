    content = [title, "=" * len(title), ""]
    content.extend(lines)
    path.write_text("\n".join(content).strip() + "\n", encoding="utf-8")


def write_srt(path: Path, segments: list[dict], lines: list[str] | None = None) -> None:
    blocks = []
    for i, seg in enumerate(segments, 1):
        text = lines[i - 1] if lines else seg["text"]
        blocks.append(
            f"{i}\n"
            f"{format_timestamp(seg['start'])} --> {format_timestamp(seg['end'])}\n"
            f"{text.strip()}\n"
        )
    path.write_text("\n".join(blocks).strip() + "\n", encoding="utf-8")


def group_by_pause(segments: list[dict], lines: list[str], pause_seconds: float = 0.8) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    previous_end: float | None = None

    for seg, line in zip(segments, lines):
        text = (line or "").strip()
        if not text:
            continue

        gap = 0.0 if previous_end is None else float(seg["start"]) - previous_end
        if current and gap >= pause_seconds:
            paragraphs.append(" ".join(current).strip())
            current = []

        current.append(text)
        previous_end = float(seg["end"])

    if current:
        paragraphs.append(" ".join(current).strip())

    return paragraphs


def write_docx(
    path: Path,
    source_name: str,
    english_paragraphs: list[str],
    portuguese_paragraphs: list[str] | None = None,
) -> None:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    styles = doc.styles
    styles["Normal"].font.name = "Times New Roman"
    styles["Normal"].font.size = Pt(12)

    doc.add_heading("Transcricao e traducao", level=1)
    doc.add_paragraph(f"Arquivo de origem: {source_name}")

    if portuguese_paragraphs is not None:
        doc.add_heading("Traducao em portugues", level=2)
        for paragraph in portuguese_paragraphs:
            if paragraph.strip():
                doc.add_paragraph(paragraph.strip())

    doc.add_heading("Transcricao em ingles", level=2)
    for paragraph in english_paragraphs:
        if paragraph.strip():
            doc.add_paragraph(paragraph.strip())

    doc.save(path)


def load_argos_translation():
    try:
        import argostranslate.translate
    except Exception as exc:
        return None, f"Argos Translate nao instalado: {exc}"

    try:
        installed = argostranslate.translate.get_installed_languages()
        source = next((lang for lang in installed if lang.code == "en"), None)
        target = next((lang for lang in installed if lang.code == "pt"), None)
        if not source or not target:
            return None, "Pacote Argos en->pt ainda nao instalado."
        translation = source.get_translation(target)
        if not translation:
            return None, "Traducao Argos en->pt nao encontrada."
        return translation, "Argos en->pt pronto."
    except Exception as exc:
        return None, f"Falha ao carregar Argos en->pt: {exc}"


def instalar_argos_en_pt() -> str:
    import argostranslate.package

    argostranslate.package.update_package_index()
    packages = argostranslate.package.get_available_packages()
    package = next((p for p in packages if p.from_code == "en" and p.to_code == "pt"), None)
    if package is None:
        raise RuntimeError("Pacote Argos en->pt nao encontrado.")
    path = package.download()
    argostranslate.package.install_from_path(path)
    return "Pacote Argos en->pt instalado."


def translate_lines_argos(lines: list[str]) -> list[str]:
    translator, status = load_argos_translation()
    if translator is None:
        st.warning("Pacote de traducao EN-PT ainda nao instalado. Tentando preparar automaticamente...")
        try:
            instalar_argos_en_pt()
            translator, status = load_argos_translation()
        except Exception as exc:
            raise RuntimeError(
                f"{status}\n\n"
                "Nao foi possivel instalar a traducao automaticamente. "
                "Tente novamente ou desmarque 'Traduzir para portugues' para gerar apenas a transcricao.\n\n"
                f"Detalhe: {exc}"
            ) from exc
    if translator is None:
        raise RuntimeError(status)
    translated: list[str] = []
    progress = st.progress(0, text="Traduzindo para portugues...")
    total = max(len(lines), 1)
    for i, line in enumerate(lines, 1):
        clean = line.strip()
        translated.append(translator.translate(clean) if clean else "")
        if i == 1 or i == total or i % 5 == 0:
            progress.progress(i / total, text=f"Traduzindo linha {i}/{total}...")
    progress.empty()
    return translated


@st.cache_resource(show_spinner=False)
def carregar_modelo(model_name: str, device: str, compute_type: str, local_only: bool):
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_name,
        device=device,
        compute_type=compute_type,
        download_root=str(MODELS_DIR),
        local_files_only=local_only,
    )


def transcrever(input_path: Path, model_name: str, device: str, compute_type: str, local_only: bool):
    model = carregar_modelo(model_name, device, compute_type, local_only)
    segments_iter, info = model.transcribe(
        str(input_path),
        language="en",
        task="transcribe",
        vad_filter=True,
        beam_size=5,
    )

    segments: list[dict] = []
    english_lines: list[str] = []
    status = st.empty()
    for seg in segments_iter:
        text = seg.text.strip()
        segments.append({"start": float(seg.start), "end": float(seg.end), "text": text})
        english_lines.append(text)
        if len(segments) == 1 or len(segments) % 10 == 0:
            status.info(f"Transcrevendo trecho {len(segments)}...")
    status.empty()

    if not segments:
        raise RuntimeError("Nenhum texto foi encontrado no audio/video.")

    return segments, english_lines, info


def salvar_upload(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".mp3"
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp.write(uploaded_file.getbuffer())
    temp.close()
    return Path(temp.name)


def gerar_arquivos(
    source_name: str,
    segments: list[dict],
    english_lines: list[str],
    portuguese_lines: list[str] | None,
    pause_seconds: float,
) -> tuple[list[Path], str, str]:
    base = safe_name(source_name)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_DIR / f"{base}_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    english_paragraphs = group_by_pause(segments, english_lines, pause_seconds)
    portuguese_paragraphs = (
        group_by_pause(segments, portuguese_lines, pause_seconds) if portuguese_lines is not None else None
    )

    created: list[Path] = []
    english_txt = out_dir / f"{base}_transcricao_en.txt"
    write_txt(english_txt, "Transcricao em ingles", english_paragraphs)
    created.append(english_txt)

    if portuguese_paragraphs is not None:
        pt_txt = out_dir / f"{base}_traducao_pt.txt"
        write_txt(pt_txt, "Traducao em portugues", portuguese_paragraphs)
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


def main():
    aplicar_estilo()

    st.title(f"{APP_TITLE} {VERSION}")
    st.caption("Transcricao de audio/video em ingles, traducao para portugues e geracao de legenda.")
    st.markdown(
        """
        <div class="hero">
            <strong>Primeira versao online do seu transcritor</strong>
            <span>Envie um arquivo, transcreva, traduza e baixe TXT, SRT, Word e ZIP.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
