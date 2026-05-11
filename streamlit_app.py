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

    with st.sidebar:
        st.header("Configuracao")
        model_name = st.selectbox("Modelo Whisper", ["tiny", "base", "small", "medium"], index=1)
        device = st.selectbox("Dispositivo", ["cpu", "cuda"], index=0)
        compute_type = st.selectbox("Precisao", ["int8", "float16", "float32"], index=0)
        local_only = st.checkbox("Usar somente modelos ja baixados", value=False)
        pause_seconds = st.slider("Pausa para paragrafo", 0.5, 5.0, 0.8, 0.1)
        traduzir = st.checkbox("Traduzir para portugues", value=True)

        translator, argos_status = load_argos_translation()
        st.caption(argos_status)
        if translator is None and st.button("Instalar traducao EN-PT"):
            with st.spinner("Instalando pacote de traducao..."):
                try:
                    st.success(instalar_argos_en_pt())
                    st.rerun()
                except Exception as exc:
                    st.error(f"Nao foi possivel instalar: {exc}")

    uploaded = st.file_uploader(
        "Envie um audio ou video em ingles",
        type=["mp3", "wav", "m4a", "aac", "flac", "ogg", "mp4", "mkv", "mov", "avi", "webm"],
    )

    if uploaded is None:
        st.info("Escolha um arquivo para comecar.")
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
            segments, english_lines, info = transcrever(temp_path, model_name, device, compute_type, local_only)

        portuguese_lines: list[str] | None = None
        if traduzir:
            portuguese_lines = translate_lines_argos(english_lines)

        created, preview_pt, preview_en = gerar_arquivos(
            uploaded.name,
            segments,
            english_lines,
            portuguese_lines,
            pause_seconds,
        )

        st.success("Concluido. Arquivos prontos para download.")
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

        tab1, tab2, tab3 = st.tabs(["Portugues", "Ingles", "Arquivos"])
        with tab1:
            if preview_pt:
                st.text_area("Previa da traducao", preview_pt, height=320)
            else:
                st.info("Traducao nao gerada nesta execucao.")
        with tab2:
            st.text_area("Previa da transcricao", preview_en, height=320)
        with tab3:
            for path in created[1:]:
                mime = "application/octet-stream"
                if path.suffix == ".txt":
                    mime = "text/plain"
                elif path.suffix == ".srt":
                    mime = "text/plain"
                elif path.suffix == ".docx":
                    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                st.download_button(path.name, path.read_bytes(), file_name=path.name, mime=mime)

    except Exception as exc:
        st.error("Nao foi possivel concluir a transcricao.")
        st.exception(exc)
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    main()
