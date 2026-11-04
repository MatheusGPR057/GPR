
from pathlib import Path
from io import BytesIO
from datetime import datetime

import pandas as pd
import streamlit as st
import seguranca

from database import (
    init_db,
    get_connection,
    create_partnership,
    excluir_partnership,
    list_partnerships,
    save_visit,
    get_visit_by_partnership,
    authorize_partnership,
    get_authorization_by_partnership,
    get_or_generate_authorization_summary,
    iniciar_execucao,
    get_execution_by_partnership,
    registrar_atualizacao_execucao,
)

BACIAS = ["BAJ", "BPA", "BME", "BCL", "BSA", "BBA", "BBJ", "BAC"]

STATUS = [
    "Não visitada",
    "Visitada",
    "Autorizada",
    "Iniciada",
    "Em execução",
    "Paralisada",
    "Concluída",
]

PARECERES = [
    "Viável",
    "Não viável",
    "Viável com ressalvas",
]


def gerar_pdf_planilha_parcerias(dados):
    """Gera PDF em formato de planilha com as parcerias atualmente filtradas."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    )

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=0.8 * cm,
        leftMargin=0.8 * cm,
        topMargin=0.8 * cm,
        bottomMargin=0.8 * cm,
    )
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "TituloPlanilhaGPR",
        parent=estilos["Title"],
        alignment=TA_CENTER,
        fontSize=14,
        spaceAfter=8,
    )
    pequeno = ParagraphStyle(
        "TextoPequenoGPR",
        parent=estilos["BodyText"],
        fontSize=7,
        leading=8,
    )

    conteudo = [
        Paragraph("RELATÓRIO DE PARCERIAS RURAIS — GPR", titulo),
        Paragraph(
            f"Total de parcerias listadas: {len(dados)}"
            f" | Relatório gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            pequeno,
        ),
        Spacer(1, 8),
    ]

    cabecalho = [
        "Código", "Bacia", "Município", "Comunidade",
        "Famílias", "Recebimento", "Situação",
        "Última atualização",
    ]
    linhas = [cabecalho]
    for item in dados:
        linhas.append([
            Paragraph(str(item.get("Código", "")), pequeno),
            Paragraph(str(item.get("Bacia", "")), pequeno),
            Paragraph(str(item.get("Município", "")), pequeno),
            Paragraph(str(item.get("Comunidade", "")), pequeno),
            Paragraph(str(item.get("Famílias", "")), pequeno),
            Paragraph(str(item.get("Data de recebimento", "")), pequeno),
            Paragraph(str(item.get("Situação", "")), pequeno),
            Paragraph(str(item.get("Última atualização", "")), pequeno),
        ])

    tabela = Table(
        linhas,
        colWidths=[2.3*cm, 1.2*cm, 2.5*cm, 3.5*cm,
                   1.3*cm, 2.1*cm, 2.5*cm, 3.5*cm],
        repeatRows=1,
    )
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (4, 1), (4, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#EEF3F8")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    conteudo.append(tabela)
    documento.build(conteudo)
    buffer.seek(0)
    return buffer.getvalue()


def data_ultima_atualizacao_execucao(parceria_id):
    """Retorna a data mais recente registrada no acompanhamento da execução."""
    execucao = get_execution_by_partnership(parceria_id)
    if not execucao:
        return "Não iniciada"

    registros = execucao.get("registros") or []
    if registros:
        ultimo = max(
            registros,
            key=lambda registro: (
                registro.get("data_registro") or "",
                registro.get("id") or 0,
            ),
        )
        data = ultimo.get("data_registro")
    else:
        data = execucao.get("data_inicio")

    if not data:
        return "Sem atualização registrada"

    try:
        return datetime.fromisoformat(str(data)).strftime("%d/%m/%Y")
    except ValueError:
        try:
            return datetime.strptime(str(data)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return str(data)


st.set_page_config(
    page_title="GPR | Gestão de Parcerias Rurais",
    page_icon="💧",
    layout="wide",
)


init_db()
seguranca.inicializar_seguranca()

# SISTEMA SEM TELA DE LOGIN
# O GPR abre diretamente na página principal.
st.title("GPR — Gestão de Parcerias Rurais")
st.caption(
    "Sistema de cadastro e acompanhamento de solicitações de parcerias rurais"
)

menu = st.sidebar.radio(
    "Menu",
    ["Nova parceria", "Parcerias cadastradas"],
)


def preparar_arquivos_execucao(arquivos):
    """Converte os arquivos enviados para o formato esperado pelo banco."""

    resultado = []

    for arquivo in arquivos or []:
        extensao = Path(arquivo.name).suffix.lower()

        tipo_arquivo = (
            "Fotografia"
            if extensao in [".jpg", ".jpeg", ".png"]
            else "Documento"
        )

        resultado.append(
            {
                "nome": arquivo.name,
                "bytes": arquivo.getvalue(),
                "tipo": tipo_arquivo,
            }
        )

    return resultado


def exibir_arquivos_execucao(arquivos, identificador):
    """Exibe os arquivos anexados a um registro de execução."""

    if not arquivos:
        return

    st.write("**Arquivos anexados:**")

    for indice, arquivo in enumerate(arquivos):
        caminho = Path(arquivo["arquivo_path"])

        if caminho.exists():
            with open(caminho, "rb") as documento:
                st.download_button(
                    label=(
                        f"Baixar [{arquivo.get('tipo_arquivo', 'Arquivo')}] "
                        f"{arquivo['arquivo_nome']}"
                    ),
                    data=documento.read(),
                    file_name=arquivo["arquivo_nome"],
                    key=f"arquivo_execucao_{identificador}_{indice}",
                )


# ---------------------------------------------------------------------
# TELA 1 — CADASTRO DE NOVA PARCERIA
# ---------------------------------------------------------------------

if menu == "Nova parceria":
    st.header("Cadastro de solicitação")
    st.caption(
        "O número de famílias e o ofício podem ser informados posteriormente."
    )

    with st.form("form_parceria", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            data_recebimento = st.date_input("Data de recebimento")
            origem = st.selectbox(
                "Origem da solicitação",
                ["Prefeitura", "SISAR"],
            )
            municipio = st.text_input("Município")
            comunidade = st.text_input("Comunidade")

        with col2:
            bacia = st.selectbox("Bacia", BACIAS)
            responsavel_cadastro = st.text_input("Responsavel pelo cadastro")

            familias_texto = st.text_input(
                "Número de famílias (opcional)",
                placeholder="Deixe em branco se ainda não souber",
            )

            oficio = st.file_uploader(
                "Anexar ofício (opcional — PDF ou imagem)",
                type=["pdf", "png", "jpg", "jpeg"],
            )

        submitted = st.form_submit_button(
            "Cadastrar parceria",
            type="primary",
        )

    if submitted:
        if (not municipio.strip() or not comunidade.strip() or not responsavel_cadastro.strip()):
            st.error("Informe município, comunidade e responsavel pelo cadastro.")
        else:
            try:
                familias = (
                    int(familias_texto)
                    if familias_texto.strip()
                    else None
                )

                if familias is not None and familias < 0:
                    st.error("O número de famílias não pode ser negativo.")
                else:
                    codigo = create_partnership(
                        data_recebimento=data_recebimento.isoformat(),
                        origem=origem,
                        municipio=municipio.strip(),
                        comunidade=comunidade.strip(),
                        bacia=bacia,
                        familias=familias,
                        arquivo_nome=oficio.name if oficio else None,
                        arquivo_bytes=oficio.getvalue() if oficio else None,
                    )

                    with get_connection() as conn:
                        parceria_auditada = conn.execute(
                            "SELECT id FROM parcerias WHERE codigo = ?",
                            (codigo,)
                        ).fetchone()

                    if parceria_auditada:
                        seguranca.registrar_auditoria(
                            responsavel=responsavel_cadastro.strip(),
                            acao="Cadastro de parceria",
                            entidade="Parceria",
                            registro_id=parceria_auditada["id"],
                            parceria_id=parceria_auditada["id"],
                            antes=None,
                            depois={
                                "codigo": codigo,
                                "data_recebimento": data_recebimento.isoformat(),
                                "origem": origem,
                                "municipio": municipio.strip(),
                                "comunidade": comunidade.strip(),
                                "bacia": bacia,
                                "familias": familias,
                                "status": "Não visitada",
                                "oficio": oficio.name if oficio else None,
                            },
                            detalhes=f"Cadastro inicial da parceria {codigo}."
                        )


                    st.success(
                        f"Parceria cadastrada com sucesso! Código: {codigo}"
                    )
                    st.info("Status inicial: Não visitada.")

            except ValueError:
                st.error(
                    "Informe um número inteiro válido de famílias "
                    "ou deixe o campo em branco."
                )
            except Exception as exc:
                st.error(f"Não foi possível cadastrar: {exc}")


# ---------------------------------------------------------------------
# TELA 2 — CONSULTA E ABERTURA INDIVIDUAL DAS PARCERIAS
# ---------------------------------------------------------------------

elif menu == "Parcerias cadastradas":
    if not st.session_state.get("parceria_selecionada"):
        st.header("Parcerias cadastradas")
        st.caption(
            "Consulte todas as solicitações, filtre por bacia, município e situação "
            "e gere um PDF da relação exibida."
        )

        # Carrega as opções a partir das parcerias existentes no banco.
        todas_para_filtros = list_partnerships(incluir_excluidas=False)
        municipios_disponiveis = sorted({
            p["municipio"] for p in todas_para_filtros if p.get("municipio")
        })

        col1, col2, col3 = st.columns(3)

        with col1:
            bacia_filtro = st.selectbox(
                "Filtrar por bacia",
                ["Todas"] + BACIAS,
                key="consulta_filtro_bacia",
            )

        with col2:
            municipio_filtro = st.selectbox(
                "Filtrar por município",
                ["Todos"] + municipios_disponiveis,
                key="consulta_filtro_municipio",
            )

        with col3:
            status_filtro = st.selectbox(
                "Filtrar por situação",
                ["Todos"] + STATUS,
                key="consulta_filtro_status",
            )

        pesquisa = st.text_input(
            "Pesquisar por código, município ou comunidade",
            key="consulta_pesquisa",
        )

        # A listagem principal exibe somente parcerias ativas.
        parcerias = list_partnerships(
            bacia=None if bacia_filtro == "Todas" else bacia_filtro,
            status=None if status_filtro == "Todos" else status_filtro,
            search=pesquisa.strip() or None,
            incluir_excluidas=False,
        )

        if municipio_filtro != "Todos":
            parcerias = [
                p for p in parcerias if p.get("municipio") == municipio_filtro
            ]

        # Monta uma única relação para a tela e para o PDF.
        linhas_relatorio = []
        for parceria in parcerias:
            ultima_atualizacao = data_ultima_atualizacao_execucao(parceria["id"])
            if parceria.get("excluida_em"):
                situacao = "Excluída"
            else:
                situacao = parceria.get("status") or "Não informada"

            linhas_relatorio.append({
                "Código": parceria.get("codigo", ""),
                "Bacia": parceria.get("bacia", ""),
                "Município": parceria.get("municipio", ""),
                "Comunidade": parceria.get("comunidade", ""),
                "Famílias": parceria.get("familias") or "Não informado",
                "Data de recebimento": parceria.get("data_recebimento", ""),
                "Situação": situacao,
                "Última atualização": ultima_atualizacao,
            })

        st.write(f"**Total de parcerias encontradas: {len(parcerias)}**")

        if linhas_relatorio:
            # Tabela em linhas clicáveis, com a lixeira integrada em cada parceria.
            # O botão com o código abre os detalhes; a lixeira solicita confirmação.
            larguras = [1.65, 0.75, 1.25, 1.45, 0.9, 1.55, 1.25, 1.65, 0.42]
            cabecalhos = [
                "Código", "Bacia", "Município", "Comunidade", "Famílias",
                "Data de recebimento", "Situação", "Última atualização", ""
            ]
            colunas_cabecalho = st.columns(larguras, gap="small")
            for coluna, titulo in zip(colunas_cabecalho, cabecalhos):
                with coluna:
                    st.caption(f"**{titulo}**" if titulo else " ")

            st.divider()
            for indice, (parceria_item, linha) in enumerate(zip(parcerias, linhas_relatorio)):
                colunas = st.columns(larguras, gap="small")
                with colunas[0]:
                    if st.button(
                        linha["Código"],
                        key=f"abrir_parceria_{parceria_item['id']}",
                        help="Clique para abrir os detalhes desta parceria",
                        use_container_width=True,
                        type="secondary",
                    ):
                        st.session_state["parceria_selecionada"] = parceria_item["codigo"]
                        st.rerun()
                valores = [
                    linha["Bacia"], linha["Município"], linha["Comunidade"],
                    linha["Famílias"], linha["Data de recebimento"],
                    linha["Situação"], linha["Última atualização"],
                ]
                for coluna, valor in zip(colunas[1:8], valores):
                    with coluna:
                        st.write(str(valor))
                with colunas[8]:
                    if st.button(
                        " ",
                        icon=":material/delete:",
                        key=f"lixeira_parceria_{parceria_item['id']}",
                        help=f"Excluir parceria {parceria_item['codigo']}",
                        type="secondary",
                    ):
                        st.session_state["confirmar_exclusao_parceria_id"] = parceria_item["id"]
                        st.rerun()
                st.divider()

            pdf = gerar_pdf_planilha_parcerias(linhas_relatorio)
            st.download_button(
                "Gerar PDF da planilha",
                data=pdf,
                file_name="relatorio_parcerias_GPR.pdf",
                mime="application/pdf",
                type="primary",
                key="baixar_pdf_planilha_parcerias",
            )

            # Confirmação simples: não solicita responsável nem motivo.
            id_pendente = st.session_state.get("confirmar_exclusao_parceria_id")
            if id_pendente is not None:
                parceria_pendente = next(
                    (p for p in parcerias if p["id"] == id_pendente),
                    None,
                )
                if parceria_pendente:
                    st.warning(
                        f"Tem certeza que deseja excluir a parceria "
                        f"{parceria_pendente['codigo']}?"
                    )
                    col_sim, col_nao, _ = st.columns([1, 1, 8])
                    with col_sim:
                        if st.button("Sim, excluir", type="primary", key="confirmar_sim_exclusao"):
                            responsavel = "Usuário do sistema"
                            try:
                                with get_connection() as conn:
                                    antes = conn.execute(
                                        "SELECT * FROM parcerias WHERE id = ?",
                                        (parceria_pendente["id"],),
                                    ).fetchone()
                                    antes = dict(antes) if antes else None

                                data_exclusao = excluir_partnership(
                                    parceria_pendente["id"],
                                    responsavel,
                                    "Exclusão confirmada pelo usuário no sistema GPR.",
                                )
                                seguranca.registrar_auditoria(
                                    responsavel=responsavel,
                                    acao="Exclusão lógica de parceria",
                                    entidade="Parceria",
                                    registro_id=parceria_pendente["id"],
                                    parceria_id=parceria_pendente["id"],
                                    antes=antes,
                                    depois={
                                        "excluida_em": data_exclusao,
                                        "excluida_por": responsavel,
                                        "motivo_exclusao": "Exclusão confirmada pelo usuário no sistema GPR.",
                                    },
                                    detalhes=f"Exclusão da parceria {parceria_pendente['codigo']} confirmada pelo usuário.",
                                )
                                if st.session_state.get("parceria_selecionada") == parceria_pendente["codigo"]:
                                    st.session_state.pop("parceria_selecionada", None)
                                st.session_state.pop("confirmar_exclusao_parceria_id", None)
                                st.success(f"Parceria {parceria_pendente['codigo']} excluída.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Não foi possível excluir a parceria: {exc}")
                    with col_nao:
                        if st.button("Não", key="cancelar_exclusao"):
                            st.session_state.pop("confirmar_exclusao_parceria_id", None)
                            st.rerun()

        else:
            st.info("Nenhuma parceria encontrada com esses filtros.")

    # ---------------------------------------------------------------
    # DETALHES DA PARCERIA
    # ---------------------------------------------------------------

    if st.session_state.get("parceria_selecionada"):
        codigo_selecionado = st.session_state["parceria_selecionada"]

        registros = list_partnerships(search=codigo_selecionado, incluir_excluidas=True)

        parceria_aberta = next(
            (
                p for p in registros
                if p["codigo"] == codigo_selecionado
            ),
            None,
        )

        if parceria_aberta:
            st.header("Detalhes da parceria")
            if st.button("← Voltar para parcerias cadastradas", key="voltar_lista_topo"):
                st.session_state.pop("parceria_selecionada", None)
                st.rerun()
            st.divider()
            st.subheader(parceria_aberta["codigo"])

            col1, col2 = st.columns(2)

            with col1:
                st.write(
                    f"**Data de recebimento:** "
                    f"{parceria_aberta['data_recebimento']}"
                )
                st.write(f"**Origem:** {parceria_aberta['origem']}")
                st.write(f"**Município:** {parceria_aberta['municipio']}")
                st.write(f"**Comunidade:** {parceria_aberta['comunidade']}")

            with col2:
                st.write(f"**Bacia:** {parceria_aberta['bacia']}")

                familias = parceria_aberta["familias"]
                familias_texto = (
                    familias if familias is not None else "Não informado"
                )

                st.write(f"**Número de famílias:** {familias_texto}")
                st.write(f"**Situação:** {parceria_aberta['status']}")

            if parceria_aberta.get("arquivo_path"):
                caminho_oficio = Path(parceria_aberta["arquivo_path"])

                if caminho_oficio.exists():
                    with open(caminho_oficio, "rb") as arquivo:
                        st.download_button(
                            "Baixar ofício",
                            data=arquivo.read(),
                            file_name=(
                                parceria_aberta["arquivo_nome"] or "oficio"
                            ),
                            key=f"baixar_oficio_{parceria_aberta['codigo']}",
                        )
            else:
                st.info("Nenhum ofício foi anexado a esta parceria.")

            # -------------------------------------------------------
            # ABAS INTERNAS DA PARCERIA
            # -------------------------------------------------------

            (
                aba_dados,
                aba_visita,
                aba_autorizacao,
                aba_execucao,
            ) = st.tabs(
                [
                    "Dados da parceria",
                    "Visita técnica",
                    "Autorização",
                    "Execução",
                ]
            )

            with aba_dados:
                st.subheader("Informações do cadastro")
                st.write(f"**Código:** {parceria_aberta['codigo']}")
                st.write(f"**Município:** {parceria_aberta['municipio']}")
                st.write(f"**Comunidade:** {parceria_aberta['comunidade']}")
                st.write(f"**Bacia:** {parceria_aberta['bacia']}")
                st.write(f"**Situação atual:** {parceria_aberta['status']}")

            # -------------------------------------------------------
            # ABA DE VISITA TÉCNICA
            # -------------------------------------------------------

            with aba_visita:
                st.subheader("Registro da visita técnica")

                visita = get_visit_by_partnership(
                    parceria_aberta["id"]
                )

                if visita:
                    st.success("Esta parceria já possui visita registrada.")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.write(f"**Data da visita:** {visita['data_visita']}")
                        st.write(f"**Responsável:** {visita['responsavel']}")
                        st.write(f"**Parecer técnico:** {visita['parecer']}")

                    with col2:
                        valor = visita["orcamento_total"]

                        if valor is not None:
                            st.write(
                                f"**Orçamento estimado:** R$ {valor:,.2f}"
                            )

                    if visita["justificativa"]:
                        st.write("**Justificativa técnica:**")
                        st.write(visita["justificativa"])

                    st.divider()
                    st.write("**Materiais previstos na visita**")
                    st.caption(
                        "Materiais registrados no salvamento da visita técnica. "
                        "Este registro é definitivo e fica disponível apenas para consulta."
                    )

                    if visita["materiais"]:
                        tabela_materiais = pd.DataFrame(
                            [
                                {
                                    "Material": m["tipo"],
                                    "Diâmetro": m["diametro"] or "-",
                                    "Quantidade": m["quantidade"],
                                    "Unidade": m["unidade"],
                                }
                                for m in visita["materiais"]
                            ]
                        )

                        st.dataframe(
                            tabela_materiais,
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("Nenhum material foi informado.")

                    st.divider()
                    st.write("**Documentos da visita**")

                    if visita["relatorio_path"]:
                        caminho = Path(visita["relatorio_path"])

                        if caminho.exists():
                            with open(caminho, "rb") as arquivo:
                                st.download_button(
                                    "Baixar relatório da visita",
                                    data=arquivo.read(),
                                    file_name=visita["relatorio_nome"],
                                    key=f"relatorio_{visita['id']}",
                                )

                    if visita["orcamento_path"]:
                        caminho = Path(visita["orcamento_path"])

                        if caminho.exists():
                            with open(caminho, "rb") as arquivo:
                                st.download_button(
                                    "Baixar orçamento",
                                    data=arquivo.read(),
                                    file_name=visita["orcamento_nome"],
                                    key=f"orcamento_{visita['id']}",
                                )

                else:
                    st.info(
                        "Esta parceria ainda não possui visita técnica registrada."
                    )

                    if parceria_aberta["status"] == "Não visitada":
                        st.markdown("### Preencher visita técnica")

                        with st.form(
                            f"form_visita_{parceria_aberta['id']}"
                        ):
                            col1, col2 = st.columns(2)

                            with col1:
                                data_visita = st.date_input(
                                    "Data da visita",
                                    key=f"data_visita_{parceria_aberta['id']}",
                                )

                                responsavel = st.text_input(
                                    "Responsável pela visita",
                                    key=f"responsavel_{parceria_aberta['id']}",
                                )

                                parecer = st.selectbox(
                                    "Parecer técnico",
                                    PARECERES,
                                    key=f"parecer_{parceria_aberta['id']}",
                                )

                            with col2:
                                orcamento_total = st.number_input(
                                    "Orçamento total estimado (R$)",
                                    min_value=0.0,
                                    value=0.0,
                                    step=100.0,
                                    key=f"orcamento_{parceria_aberta['id']}",
                                )

                                relatorio = st.file_uploader(
                                    "Relatório da visita (PDF)",
                                    type=["pdf"],
                                    key=f"relatorio_upload_{parceria_aberta['id']}",
                                )

                                arquivo_orcamento = st.file_uploader(
                                    "Planilha ou arquivo do orçamento",
                                    type=["pdf", "xlsx", "xls", "csv"],
                                    key=f"orcamento_upload_{parceria_aberta['id']}",
                                )

                            justificativa = st.text_area(
                                "Justificativa / observações técnicas",
                                placeholder=(
                                    "Informe os detalhes e as ressalvas "
                                    "identificadas na visita."
                                ),
                                key=f"justificativa_{parceria_aberta['id']}",
                            )

                            st.divider()
                            st.markdown("### Materiais necessários")

                            st.caption(
                                "Adicione uma linha para cada material "
                                "necessário. As linhas em branco serão ignoradas."
                            )

                            materiais_df = pd.DataFrame(
                                [
                                    {
                                        "Material": "",
                                        "Diâmetro": "",
                                        "Quantidade": 0.0,
                                        "Unidade": "m",
                                    }
                                ]
                            )

                            materiais_editados = st.data_editor(
                                materiais_df,
                                num_rows="dynamic",
                                use_container_width=True,
                                hide_index=True,
                                key=f"materiais_{parceria_aberta['id']}",
                                column_config={
                                    "Material": st.column_config.TextColumn(
                                        "Material",
                                        help="Ex.: Tubo PVC PBA, registro, conexão",
                                    ),
                                    "Diâmetro": st.column_config.TextColumn(
                                        "Diâmetro",
                                        help="Ex.: DN 50, DN 75, DN 100",
                                    ),
                                    "Quantidade": st.column_config.NumberColumn(
                                        "Quantidade",
                                        min_value=0.0,
                                        step=1.0,
                                    ),
                                    "Unidade": st.column_config.SelectboxColumn(
                                        "Unidade",
                                        options=["m", "un", "kg", "outro"],
                                    ),
                                },
                            )

                            enviar_visita = st.form_submit_button(
                                "Salvar visita técnica",
                                type="primary",
                            )

                        if enviar_visita:
                            # Os dois documentos são obrigatórios para concluir a visita.
                            if not relatorio or not relatorio.getvalue():
                                st.error("Anexe o relatório da visita em PDF para continuar.")

                            elif not arquivo_orcamento or not arquivo_orcamento.getvalue():
                                st.error("Anexe o arquivo do orçamento para continuar.")

                            elif not responsavel.strip():
                                st.error(
                                    "Informe o responsável pela visita."
                                )

                            elif (
                                parecer in [
                                    "Não viável",
                                    "Viável com ressalvas",
                                ]
                                and not justificativa.strip()
                            ):
                                st.error(
                                    "Para esse parecer, informe a justificativa técnica."
                                )

                            else:
                                materiais = []
                                erro_material = None

                                for _, linha in materiais_editados.iterrows():
                                    tipo = str(linha["Material"]).strip()
                                    diametro = str(linha["Diâmetro"]).strip()
                                    quantidade = float(linha["Quantidade"])
                                    unidade = str(linha["Unidade"]).strip()

                                    if not tipo and quantidade == 0:
                                        continue

                                    if not tipo:
                                        erro_material = (
                                            "Informe o nome do material "
                                            "em todas as linhas preenchidas."
                                        )
                                        break

                                    if quantidade <= 0:
                                        erro_material = (
                                            f"Informe uma quantidade maior "
                                            f"que zero para {tipo}."
                                        )
                                        break

                                    materiais.append(
                                        {
                                            "tipo": tipo,
                                            "diametro": diametro or None,
                                            "quantidade": quantidade,
                                            "unidade": unidade or "m",
                                        }
                                    )

                                if erro_material:
                                    st.error(erro_material)
                                else:
                                    try:
                                        save_visit(
                                            parceria_id=parceria_aberta["id"],
                                            data_visita=data_visita.isoformat(),
                                            responsavel=responsavel.strip(),
                                            parecer=parecer,
                                            justificativa=(
                                                justificativa.strip() or None
                                            ),
                                            materiais=materiais,
                                            orcamento_total=orcamento_total,
                                            relatorio_nome=(
                                                relatorio.name if relatorio else None
                                            ),
                                            relatorio_bytes=(
                                                relatorio.getvalue()
                                                if relatorio else None
                                            ),
                                            orcamento_nome=(
                                                arquivo_orcamento.name
                                                if arquivo_orcamento else None
                                            ),
                                            orcamento_bytes=(
                                                arquivo_orcamento.getvalue()
                                                if arquivo_orcamento else None
                                            ),
                                        )

                                        st.success(
                                            "Visita técnica registrada com sucesso!"
                                        )
                                        st.info(
                                            "A situação da parceria foi atualizada "
                                            "para Visitada."
                                        )
                                        st.rerun()

                                    except Exception as exc:
                                        st.error(
                                            f"Não foi possível salvar a visita: {exc}"
                                        )

                    else:
                        st.warning(
                            "O cadastro da visita não está disponível porque "
                            "a situação atual desta parceria não é 'Não visitada'."
                        )

            # -------------------------------------------------------
            # ABA DE AUTORIZAÇÃO
            # -------------------------------------------------------

            with aba_autorizacao:
                st.subheader("Autorização da parceria")

                visita_autorizacao = get_visit_by_partnership(
                    parceria_aberta["id"]
                )

                autorizacao = get_authorization_by_partnership(
                    parceria_aberta["id"]
                )

                if autorizacao:
                    st.success("Esta parceria já foi autorizada.")

                    st.write(
                        f"**Responsável pela autorização:** "
                        f"{autorizacao['autorizado_por']}"
                    )
                    st.write(
                        f"**Data da autorização:** "
                        f"{autorizacao['data_autorizacao']}"
                    )
                    st.write("**Materiais efetivamente liberados:**")
                    st.write(autorizacao.get("materiais_liberados") or "Não informado.")

                    nota_path = autorizacao.get("nota_fiscal_path")
                    if nota_path and Path(nota_path).exists():
                        with open(nota_path, "rb") as nf:
                            st.download_button(
                                "Baixar nota fiscal dos materiais liberados",
                                data=nf.read(),
                                file_name=autorizacao.get("nota_fiscal_nome") or "nota_fiscal",
                                key=f"baixar_nf_autorizacao_{parceria_aberta['id']}",
                            )
                    else:
                        st.caption("Nenhuma nota fiscal foi anexada.")

                    try:
                        # Mantém o relatório disponível após a autorização.
                        # Se o arquivo tiver sido movido/apagado, recria-o sem
                        # registrar uma nova autorização.
                        caminho_resumo = get_or_generate_authorization_summary(
                            parceria_aberta["id"]
                        )
                        with open(caminho_resumo, "rb") as arquivo:
                            st.download_button(
                                "Baixar relatório resumo da parceria",
                                data=arquivo.read(),
                                file_name=caminho_resumo.name,
                                mime="application/pdf",
                                type="primary",
                                key=f"baixar_resumo_{parceria_aberta['id']}",
                            )
                    except Exception as exc:
                        st.error(
                            "Não foi possível disponibilizar o relatório resumo: "
                            f"{exc}"
                        )

                elif not visita_autorizacao:
                    st.info(
                        "A autorização ficará disponível após o registro "
                        "da visita técnica."
                    )

                elif visita_autorizacao["parecer"] == "Não viável":
                    st.error(
                        "Esta parceria recebeu parecer Não viável e não "
                        "pode ser autorizada."
                    )

                elif parceria_aberta["status"] != "Visitada":
                    st.warning(
                        "A parceria não está na situação necessária "
                        "para receber uma autorização."
                    )

                else:
                    st.success(
                        f"Parecer técnico: {visita_autorizacao['parecer']}"
                    )

                    if visita_autorizacao["parecer"] == "Viável com ressalvas":
                        st.warning(
                            "A parceria possui ressalvas técnicas. "
                            "Analise a justificativa antes de autorizar."
                        )
                        st.write(
                            visita_autorizacao["justificativa"]
                            or "Não foram informadas ressalvas."
                        )

                    st.write(
                        "Confira os dados da visita, os materiais e o "
                        "orçamento antes de tomar a decisão."
                    )

                    with st.form(
                        f"form_autorizacao_{parceria_aberta['id']}"
                    ):
                        autorizado_por = st.text_input(
                            "Nome de quem está autorizando",
                            key=f"autorizado_por_{parceria_aberta['id']}",
                        )
                        materiais_liberados = st.text_area(
                            "Materiais efetivamente liberados",
                            placeholder=(
                                "Ex.: 1.200 m de tubo PVC PBA DN 50; "
                                "12 registros de manobra DN 50..."
                            ),
                            help="Informe o tipo, diâmetro e quantidade realmente liberados.",
                            key=f"materiais_liberados_{parceria_aberta['id']}",
                        )
                        nota_fiscal = st.file_uploader(
                            "Nota fiscal dos materiais liberados (opcional)",
                            type=["pdf", "jpg", "jpeg", "png"],
                            key=f"nota_fiscal_autorizacao_{parceria_aberta['id']}",
                        )

                        confirmar_autorizacao = st.checkbox(
                            "Confirmo que analisei as informações e autorizo "
                            "o prosseguimento desta parceria.",
                            key=f"confirmar_autorizacao_{parceria_aberta['id']}",
                        )

                        enviar_autorizacao = st.form_submit_button(
                            "Autorizar parceria e gerar relatório",
                            type="primary",
                        )

                    if enviar_autorizacao:
                        if not autorizado_por.strip():
                            st.error(
                                "Informe o nome de quem está autorizando."
                            )
                        elif not confirmar_autorizacao:
                            st.error(
                                "Marque a confirmação antes de autorizar."
                            )
                        else:
                            try:
                                caminho_pdf = authorize_partnership(
                                    parceria_id=parceria_aberta["id"],
                                    autorizado_por=autorizado_por.strip(),
                                    materiais_liberados=materiais_liberados,
                                    nota_fiscal_nome=(nota_fiscal.name if nota_fiscal else None),
                                    nota_fiscal_bytes=(nota_fiscal.getvalue() if nota_fiscal else None),
                                )

                                st.success(
                                    "Parceria autorizada e relatório resumo "
                                    "gerado com sucesso!"
                                )

                                with open(caminho_pdf, "rb") as arquivo:
                                    st.download_button(
                                        "Baixar relatório resumo da parceria",
                                        data=arquivo.read(),
                                        file_name=caminho_pdf.name,
                                        type="primary",
                                        key=(
                                            f"baixar_resumo_novo_"
                                            f"{parceria_aberta['id']}"
                                        ),
                                    )

                                st.rerun()

                            except Exception as exc:
                                st.error(
                                    f"Não foi possível autorizar a parceria: {exc}"
                                )

            # -------------------------------------------------------
            # ABA DE EXECUÇÃO
            # -------------------------------------------------------

            with aba_execucao:
                st.subheader("Acompanhamento da execução")

                parceria_id = parceria_aberta["id"]
                status_atual = parceria_aberta["status"]

                execucao = get_execution_by_partnership(parceria_id)

                # ---------------------------------------------------
                # ETAPA 1 — INICIAR EXECUÇÃO
                # ---------------------------------------------------

                if execucao is None:
                    if status_atual == "Autorizada":
                        st.info(
                            "Esta parceria está autorizada e aguarda "
                            "o registro do início da execução."
                        )

                        with st.form(
                            f"form_inicio_execucao_{parceria_id}"
                        ):
                            data_inicio = st.date_input(
                                "Data de início da execução",
                                key=f"data_inicio_{parceria_id}",
                            )

                            responsavel_inicio = st.text_input(
                                "Responsável pelo início da execução",
                                key=f"responsavel_inicio_{parceria_id}",
                            )

                            iniciar = st.form_submit_button(
                                "Registrar início da execução",
                                type="primary",
                            )

                        if iniciar:
                            if not responsavel_inicio.strip():
                                st.error(
                                    "Informe o responsável pelo início da execução."
                                )
                            else:
                                try:
                                    iniciar_execucao(
                                        parceria_id=parceria_id,
                                        responsavel=responsavel_inicio.strip(),
                                        data_inicio=data_inicio.isoformat(),
                                    )

                                    st.success(
                                        "Início da execução registrado com sucesso!"
                                    )
                                    st.rerun()

                                except Exception as exc:
                                    st.error(
                                        f"Não foi possível iniciar a execução: {exc}"
                                    )

                    else:
                        st.info(
                            "O acompanhamento da execução ficará disponível "
                            "após a autorização da parceria."
                        )

                # ---------------------------------------------------
                # ETAPA 2 — EXECUÇÃO JÁ INICIADA
                # ---------------------------------------------------

                else:
                    status_execucao = execucao["status"]

                    st.success("Execução cadastrada.")

                    col1, col2, col3 = st.columns(3)

                    col1.metric(
                        "Data de início",
                        execucao["data_inicio"],
                    )

                    col2.metric(
                        "Responsável pelo início",
                        execucao["responsavel"],
                    )

                    col3.metric(
                        "Situação atual",
                        status_execucao,
                    )

                    if execucao.get("data_conclusao"):
                        st.write(
                            f"**Data de conclusão:** "
                            f"{execucao['data_conclusao']}"
                        )

                    # -----------------------------------------------
                    # HISTÓRICO DA EXECUÇÃO
                    # -----------------------------------------------

                    st.divider()
                    st.markdown("### Histórico da execução")

                    registros_execucao = execucao.get("registros", [])

                    if registros_execucao:
                        for registro in registros_execucao:
                            with st.container(border=True):
                                st.markdown(
                                    f"**{registro['tipo']} — "
                                    f"{registro['data_registro']}**"
                                )

                                st.write(
                                    f"**Responsável:** "
                                    f"{registro['responsavel']}"
                                )

                                if registro.get("observacao"):
                                    st.write(
                                        f"**Observações:** "
                                        f"{registro['observacao']}"
                                    )

                                if registro.get("motivo_paralisacao"):
                                    st.warning(
                                        f"**Motivo da paralisação:** "
                                        f"{registro['motivo_paralisacao']}"
                                    )

                                if registro.get("previsao_retorno"):
                                    st.write(
                                        f"**Previsão de retorno:** "
                                        f"{registro['previsao_retorno']}"
                                    )

                                exibir_arquivos_execucao(
                                    registro.get("arquivos", []),
                                    registro["id"],
                                )
                    else:
                        st.info("Ainda não existem atualizações registradas.")

                    # -----------------------------------------------
                    # ETAPA 3 — ATUALIZAR EXECUÇÃO E ENCERRAMENTO
                    # -----------------------------------------------

                    st.divider()
                    st.markdown("### Registrar atualização")

                    if status_execucao == "Concluída":
                        st.success(
                            "Esta execução foi concluída. "
                            "O histórico e os documentos permanecem "
                            "disponíveis para consulta."
                        )

                    else:
                        if status_execucao == "Paralisada":
                            tipos_permitidos = ["Retomada"]

                            st.warning(
                                "A execução está paralisada. "
                                "Registre a retomada para voltar a acompanhar "
                                "os serviços em andamento."
                            )
                        else:
                            tipos_permitidos = [
                                "Em execução",
                                "Paralisada",
                                "Concluída",
                            ]

                        tipo_atualizacao = st.selectbox(
                            "Tipo de atualização",
                            tipos_permitidos,
                            key=f"tipo_atualizacao_{parceria_id}",
                        )

                        with st.form(
                            f"form_atualizacao_execucao_{parceria_id}"
                        ):
                            data_registro = st.date_input(
                                "Data do registro",
                                key=f"data_registro_execucao_{parceria_id}",
                            )

                            responsavel_atualizacao = st.text_input(
                                "Responsável pelo registro",
                                key=f"responsavel_atualizacao_{parceria_id}",
                            )

                            observacao = st.text_area(
                                "Observações sobre a execução",
                                placeholder=(
                                    "Descreva o andamento dos serviços, "
                                    "as atividades realizadas ou outras informações."
                                ),
                                key=f"observacao_execucao_{parceria_id}",
                            )

                            motivo_paralisacao = None
                            previsao_retorno = None

                            if tipo_atualizacao == "Paralisada":
                                motivo_paralisacao = st.text_area(
                                    "Motivo da paralisação",
                                    placeholder=(
                                        "Informe por que os serviços foram paralisados."
                                    ),
                                    key=f"motivo_paralisacao_{parceria_id}",
                                )

                                informar_previsao = st.checkbox(
                                    "Informar previsão de retorno",
                                    key=f"informar_previsao_{parceria_id}",
                                )

                                if informar_previsao:
                                    previsao_retorno = st.date_input(
                                        "Previsão de retorno",
                                        key=f"previsao_retorno_{parceria_id}",
                                    )

                            if tipo_atualizacao == "Concluída":
                                st.divider()
                                st.markdown(
                                    "### Documentação de encerramento"
                                )

                                st.info(
                                    "Para concluir a execução, é obrigatório "
                                    "anexar o relatório final em PDF. "
                                    "Fotografias não são exigidas."
                                )

                                relatorio_final = st.file_uploader(
                                    "Relatório final da execução (PDF) — obrigatório",
                                    type=["pdf"],
                                    key=f"relatorio_final_{parceria_id}",
                                )

                                documentos_complementares = st.file_uploader(
                                    "Documentos complementares (opcional)",
                                    type=[
                                        "pdf",
                                        "xlsx",
                                        "xls",
                                        "csv",
                                    ],
                                    accept_multiple_files=True,
                                    key=f"documentos_conclusao_{parceria_id}",
                                )

                                arquivos_enviados = []

                            else:
                                relatorio_final = None
                                documentos_complementares = []

                                arquivos_enviados = st.file_uploader(
                                    "Anexar documentos e fotografias (opcional)",
                                    type=[
                                        "pdf",
                                        "jpg",
                                        "jpeg",
                                        "png",
                                        "xlsx",
                                        "xls",
                                        "csv",
                                    ],
                                    accept_multiple_files=True,
                                    key=f"arquivos_execucao_{parceria_id}",
                                )

                            salvar_atualizacao = st.form_submit_button(
                                "Salvar atualização",
                                type="primary",
                            )

                        if salvar_atualizacao:
                            if not responsavel_atualizacao.strip():
                                st.error(
                                    "Informe o responsável pelo registro."
                                )

                            elif (
                                tipo_atualizacao == "Paralisada"
                                and not motivo_paralisacao.strip()
                            ):
                                st.error(
                                    "Informe o motivo da paralisação."
                                )

                            elif (
                                tipo_atualizacao == "Concluída"
                                and not relatorio_final
                            ):
                                st.error(
                                    "Anexe o relatório final da execução em PDF."
                                )

                            else:
                                try:
                                    if tipo_atualizacao == "Concluída":
                                        arquivos_preparados = [
                                            {
                                                "nome": relatorio_final.name,
                                                "bytes": relatorio_final.getvalue(),
                                                "tipo": "Relatório final",
                                            }
                                        ]

                                        arquivos_preparados.extend(
                                            preparar_arquivos_execucao(
                                                documentos_complementares
                                            )
                                        )
                                    else:
                                        arquivos_preparados = (
                                            preparar_arquivos_execucao(
                                                arquivos_enviados
                                            )
                                        )

                                    registrar_atualizacao_execucao(
                                        parceria_id=parceria_id,
                                        tipo=tipo_atualizacao,
                                        data_registro=data_registro.isoformat(),
                                        responsavel=responsavel_atualizacao.strip(),
                                        observacao=observacao.strip() or None,
                                        motivo_paralisacao=(
                                            motivo_paralisacao.strip()
                                            if motivo_paralisacao
                                            else None
                                        ),
                                        previsao_retorno=(
                                            previsao_retorno.isoformat()
                                            if previsao_retorno
                                            else None
                                        ),
                                        arquivos=arquivos_preparados,
                                    )

                                    st.success(
                                        "Atualização da execução registrada "
                                        "com sucesso!"
                                    )

                                    if tipo_atualizacao == "Concluída":
                                        st.success(
                                            "Encerramento documental registrado "
                                            "com o relatório final."
                                        )

                                    st.rerun()

                                except Exception as exc:
                                    st.error(
                                        f"Não foi possível registrar a atualização: {exc}"
                                    )

        else:
            st.warning("A parceria selecionada não foi localizada.")

            if st.button("Limpar seleção"):
                del st.session_state["parceria_selecionada"]
                st.rerun()


st.sidebar.divider()
st.sidebar.caption("GPR — Gestão de Parcerias Rurais")
