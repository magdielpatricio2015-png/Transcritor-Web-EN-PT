        translator, argos_status = load_argos_translation()
        st.caption(argos_status)

        if translator is None and st.button("Instalar traducao EN-PT"):
            with st.spinner("Instalando pacote de traducao..."):
                garantir_argos_en_pt.clear()
                st.success(garantir_argos_en_pt())
                st.rerun()

    modo_entrada = st.radio(
        "Escolha a origem do audio/video",
        ["Enviar arquivo", "Usar link"],
        horizontal=True,
    )

    uploaded = None
    link_midia = ""

    if modo_entrada == "Enviar arquivo":
        uploaded = st.file_uploader(
            "Envie um audio ou video em ingles",
            type=[
                "mp3",
                "wav",
                "m4a",
                "aac",
                "flac",
                "ogg",
                "opus",
                "mp4",
                "mkv",
                "mov",
                "avi",
                "webm",
            ],
        )

        if uploaded is None:
            st.info("Escolha um arquivo para comecar.")
            return

        c1, c2, c3 = st.columns(3)
        c1.metric("Arquivo", limpar_texto(uploaded.name)[:32])
        c2.metric("Tamanho", f"{uploaded.size / (1024 * 1024):.1f} MB")
        c3.metric("Modelo", model_name)

    else:
        link_midia = st.text_input(
            "Cole o link do audio ou video",
            placeholder="https://www.youtube.com/watch?v=... ou https://site.com/audio.mp3",
        )
        mostrar_ajuda_youtube()

        if link_midia.strip() and eh_youtube(link_midia):
            if COOKIES_FILE.exists():
                st.success("cookies.txt encontrado. O app vai tentar usar esses cookies no YouTube.")
            else:
                st.warning("YouTube detectado. Sem cookies.txt, o Streamlit Cloud pode ser bloqueado.")

        if not link_midia.strip():
            st.info("Cole um link para comecar.")
            return

        c1, c2, c3 = st.columns(3)
        c1.metric("Origem", "YouTube" if eh_youtube(link_midia) else "Link")
        c2.metric("Cookies", "Sim" if COOKIES_FILE.exists() else "Nao")
        c3.metric("Modelo", model_name)

    if not st.button("Transcrever agora", type="primary", use_container_width=True):
        return

    temp_path: Path | None = None
    temp_dir_link: Path | None = None
    source_name = ""

    try:
        if modo_entrada == "Enviar arquivo":
            temp_path = salvar_upload(uploaded)
            source_name = uploaded.name
        else:
            with st.spinner("Baixando midia do link..."):
                temp_path, source_name, temp_dir_link = baixar_midia_link(link_midia)

        with st.spinner("Carregando modelo e transcrevendo..."):
            segments, english_lines, _info = transcrever(
                temp_path,
                model_name,
                device,
                compute_type,
                local_only,
            )

        portuguese_lines: list[str] | None = None
        traducao_falhou = False

        if traduzir:
            with st.spinner("Traduzindo para portugues..."):
                try:
                    portuguese_lines = translate_lines_argos(english_lines)
                except Exception as exc:
                    traducao_falhou = True
                    st.warning(
                        "A transcricao foi concluida, mas a traducao nao foi realizada. "
                        f"Motivo: {exc}"
                    )

        with st.spinner("Gerando arquivos..."):
            files, preview_pt, preview_en = gerar_arquivos(
                source_name,
                segments,
                english_lines,
                portuguese_lines,
                pause_seconds,
            )

        tab1, tab2 = st.tabs(["Portugues", "Ingles"])

        with tab1:
            if portuguese_lines and not traducao_falhou:
                st.text_area("Traducao", preview_pt, height=320)
            else:
                st.info("Traducao indisponivel.")

        with tab2:
            st.text_area("Transcricao original", preview_en, height=320)

        st.success("Processamento concluido. Baixe os arquivos abaixo.")

        for file_path in files:
            with file_path.open("rb") as file:
                st.download_button(
                    label=f"Baixar {file_path.name}",
                    data=file,
                    file_name=file_path.name,
                    mime="application/octet-stream",
                )

    except Exception as exc:
        message = str(exc)

        if not mostrar_diagnostico and "Detalhe tecnico do yt-dlp:" in message:
            message = message.split("Detalhe tecnico do yt-dlp:", maxsplit=1)[0].strip()

        st.error(message)

    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

        if temp_dir_link and temp_dir_link.exists():
            shutil.rmtree(temp_dir_link, ignore_errors=True)


if __name__ == "__main__":
    main()
