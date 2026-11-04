
import re
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "gpr.db"
UPLOAD_DIR = BASE_DIR / "documentos"
UPLOAD_DIR.mkdir(exist_ok=True)


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parcerias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT NOT NULL UNIQUE,
                data_recebimento TEXT NOT NULL,
                origem TEXT NOT NULL,
                municipio TEXT NOT NULL,
                comunidade TEXT NOT NULL,
                bacia TEXT NOT NULL,
                familias INTEGER,
                status TEXT NOT NULL DEFAULT 'Não visitada',
                arquivo_nome TEXT,
                arquivo_path TEXT,
                criado_em TEXT NOT NULL
            )
        """)

        colunas = {
            row[1]: row
            for row in conn.execute("PRAGMA table_info(parcerias)")
        }

        precisa_migrar = any(
            colunas[c][3]
            for c in ("arquivo_nome", "arquivo_path")
        )

        if precisa_migrar:
            conn.execute("ALTER TABLE parcerias RENAME TO parcerias_antiga")

            conn.execute("""
                CREATE TABLE parcerias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    data_recebimento TEXT NOT NULL,
                    origem TEXT NOT NULL,
                    municipio TEXT NOT NULL,
                    comunidade TEXT NOT NULL,
                    bacia TEXT NOT NULL,
                    familias INTEGER,
                    status TEXT NOT NULL DEFAULT 'Não visitada',
                    arquivo_nome TEXT,
                    arquivo_path TEXT,
                    criado_em TEXT NOT NULL
                )
            """)

            conn.execute("""
                INSERT INTO parcerias
                (id, codigo, data_recebimento, origem, municipio, comunidade,
                 bacia, familias, status, arquivo_nome, arquivo_path, criado_em)
                SELECT id, codigo, data_recebimento, origem, municipio,
                       comunidade, bacia, familias, status, arquivo_nome,
                       arquivo_path, criado_em
                FROM parcerias_antiga
            """)

            conn.execute("DROP TABLE parcerias_antiga")

        colunas_parcerias = {
            row[1] for row in conn.execute("PRAGMA table_info(parcerias)")
        }

        if "excluida_em" not in colunas_parcerias:
            conn.execute("ALTER TABLE parcerias ADD COLUMN excluida_em TEXT")

        if "excluida_por" not in colunas_parcerias:
            conn.execute("ALTER TABLE parcerias ADD COLUMN excluida_por TEXT")

        if "motivo_exclusao" not in colunas_parcerias:
            conn.execute("ALTER TABLE parcerias ADD COLUMN motivo_exclusao TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parceria_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                data_hora TEXT NOT NULL,
                observacao TEXT,
                FOREIGN KEY(parceria_id) REFERENCES parcerias(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS visitas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parceria_id INTEGER NOT NULL UNIQUE,
                data_visita TEXT NOT NULL,
                responsavel TEXT NOT NULL,
                parecer TEXT NOT NULL,
                justificativa TEXT,
                orcamento_total REAL,
                relatorio_nome TEXT,
                relatorio_path TEXT,
                orcamento_nome TEXT,
                orcamento_path TEXT,
                criado_em TEXT NOT NULL,
                FOREIGN KEY(parceria_id) REFERENCES parcerias(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS materiais_visita (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visita_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                diametro TEXT,
                quantidade REAL NOT NULL,
                unidade TEXT NOT NULL DEFAULT 'm',
                FOREIGN KEY(visita_id) REFERENCES visitas(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS autorizacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parceria_id INTEGER NOT NULL UNIQUE,
                autorizado_por TEXT NOT NULL,
                data_autorizacao TEXT NOT NULL,
                resumo_nome TEXT,
                resumo_path TEXT,
                FOREIGN KEY(parceria_id) REFERENCES parcerias(id)
            )
        """)

        # Campos adicionais da autorização: materiais efetivamente liberados e nota fiscal.
        colunas_autorizacoes = {
            row[1] for row in conn.execute("PRAGMA table_info(autorizacoes)")
        }
        if "materiais_liberados" not in colunas_autorizacoes:
            conn.execute("ALTER TABLE autorizacoes ADD COLUMN materiais_liberados TEXT")
        if "nota_fiscal_nome" not in colunas_autorizacoes:
            conn.execute("ALTER TABLE autorizacoes ADD COLUMN nota_fiscal_nome TEXT")
        if "nota_fiscal_path" not in colunas_autorizacoes:
            conn.execute("ALTER TABLE autorizacoes ADD COLUMN nota_fiscal_path TEXT")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS execucoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parceria_id INTEGER NOT NULL UNIQUE,
                data_inicio TEXT,
                responsavel TEXT,
                status TEXT NOT NULL DEFAULT 'Autorizada',
                data_conclusao TEXT,
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL,
                FOREIGN KEY(parceria_id) REFERENCES parcerias(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS registros_execucao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execucao_id INTEGER NOT NULL,
                tipo TEXT NOT NULL,
                data_registro TEXT NOT NULL,
                responsavel TEXT NOT NULL,
                observacao TEXT,
                motivo_paralisacao TEXT,
                previsao_retorno TEXT,
                FOREIGN KEY(execucao_id) REFERENCES execucoes(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS arquivos_execucao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                registro_id INTEGER NOT NULL,
                arquivo_nome TEXT NOT NULL,
                arquivo_path TEXT NOT NULL,
                tipo_arquivo TEXT NOT NULL,
                FOREIGN KEY(registro_id) REFERENCES registros_execucao(id)
            )
        """)

        # =============================================================
        # NOVAS TABELAS — CONTROLE DE MATERIAIS ENTREGUES
        # =============================================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS entregas_materiais (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parceria_id INTEGER NOT NULL,
                data_entrega TEXT NOT NULL,
                responsavel TEXT NOT NULL,
                observacao TEXT,
                comprovante_nome TEXT,
                comprovante_path TEXT,
                criado_em TEXT NOT NULL,
                FOREIGN KEY(parceria_id) REFERENCES parcerias(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS itens_entrega (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entrega_id INTEGER NOT NULL,
                material_visita_id INTEGER NOT NULL,
                quantidade REAL NOT NULL,
                justificativa_excedente TEXT,
                FOREIGN KEY(entrega_id) REFERENCES entregas_materiais(id),
                FOREIGN KEY(material_visita_id) REFERENCES materiais_visita(id)
            )
        """)


def _proximo_codigo(conn, bacia):
    prefixo = f"GPR-{bacia}-"

    row = conn.execute("""
        SELECT codigo
        FROM parcerias
        WHERE bacia = ?
        ORDER BY id DESC
        LIMIT 1
    """, (bacia,)).fetchone()

    if not row:
        numero = 1
    else:
        match = re.search(r"-(\d+)$", row["codigo"])
        numero = int(match.group(1)) + 1 if match else 1

    return f"{prefixo}{numero:04d}"


def create_partnership(
    data_recebimento,
    origem,
    municipio,
    comunidade,
    bacia,
    familias,
    arquivo_nome=None,
    arquivo_bytes=None
):
    with get_connection() as conn:
        codigo = _proximo_codigo(conn, bacia)
        safe_name = None
        caminho = None

        if arquivo_nome and arquivo_bytes:
            safe_name = Path(arquivo_nome).name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            caminho = UPLOAD_DIR / f"{codigo}_{timestamp}_{safe_name}"
            caminho.write_bytes(arquivo_bytes)

        cur = conn.execute("""
            INSERT INTO parcerias
            (codigo, data_recebimento, origem, municipio, comunidade,
             bacia, familias, status, arquivo_nome, arquivo_path, criado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Não visitada', ?, ?, ?)
        """, (
            codigo,
            data_recebimento,
            origem,
            municipio,
            comunidade,
            bacia,
            familias,
            safe_name,
            str(caminho) if caminho else None,
            datetime.now().isoformat(timespec="seconds")
        ))

        conn.execute("""
            INSERT INTO historico
            (parceria_id, status, data_hora, observacao)
            VALUES (?, 'Não visitada', ?, 'Cadastro inicial da solicitação')
        """, (
            cur.lastrowid,
            datetime.now().isoformat(timespec="seconds")
        ))

        return codigo


def excluir_partnership(parceria_id, responsavel, motivo):
    responsavel = responsavel.strip()
    motivo = motivo.strip()

    if not responsavel or not motivo:
        raise ValueError("Informe o responsável e o motivo da exclus?o.")

    with get_connection() as conn:
        parceria = conn.execute(
            "SELECT id, excluida_em FROM parcerias WHERE id = ?",
            (parceria_id,)
        ).fetchone()

        if not parceria:
            raise ValueError("Parceria não encontrada.")

        if parceria["excluida_em"]:
            raise ValueError("Esta parceria já está excluída.")

        agora = datetime.now().isoformat(timespec="seconds")

        conn.execute("""
            UPDATE parcerias
            SET excluida_em = ?,
                excluida_por = ?,
                motivo_exclusao = ?
            WHERE id = ?
        """, (agora, responsavel, motivo, parceria_id))

        return agora


def list_partnerships(bacia=None, status=None, search=None, incluir_excluidas=False):
    sql = "SELECT * FROM parcerias WHERE 1=1"
    params = []

    if not incluir_excluidas:
        sql += " AND excluida_em IS NULL"

    if bacia:
        sql += " AND bacia = ?"
        params.append(bacia)

    if status:
        sql += " AND status = ?"
        params.append(status)

    if search:
        termo = f"%{search}%"
        sql += """
            AND (
                codigo LIKE ?
                OR municipio LIKE ?
                OR comunidade LIKE ?
            )
        """
        params.extend([termo, termo, termo])

    sql += " ORDER BY criado_em DESC"

    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(sql, params).fetchall()
        ]


def get_visit_by_partnership(parceria_id):
    with get_connection() as conn:
        visita = conn.execute("""
            SELECT *
            FROM visitas
            WHERE parceria_id = ?
        """, (parceria_id,)).fetchone()

        if not visita:
            return None

        resultado = dict(visita)

        materiais = conn.execute("""
            SELECT *
            FROM materiais_visita
            WHERE visita_id = ?
            ORDER BY id
        """, (visita["id"],)).fetchall()

        resultado["materiais"] = [
            dict(material) for material in materiais
        ]

        return resultado


def save_visit(
    parceria_id,
    data_visita,
    responsavel,
    parecer,
    justificativa,
    materiais,
    orcamento_total,
    relatorio_nome=None,
    relatorio_bytes=None,
    orcamento_nome=None,
    orcamento_bytes=None
):
    # Proteção no banco: não registra visita sem os dois documentos obrigatórios.
    if not relatorio_nome or not relatorio_bytes:
        raise ValueError("O relatório da visita em PDF é obrigatório.")
    if not orcamento_nome or not orcamento_bytes:
        raise ValueError("O arquivo do orçamento é obrigatório.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    agora = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        parceria = conn.execute("""
            SELECT id, codigo, status
            FROM parcerias
            WHERE id = ?
        """, (parceria_id,)).fetchone()

        if not parceria:
            raise ValueError("Parceria não encontrada.")

        if parceria["status"] != "Não visitada":
            raise ValueError(
                "A parceria não está disponível para receber uma visita."
            )

        visita_existente = conn.execute("""
            SELECT id
            FROM visitas
            WHERE parceria_id = ?
        """, (parceria_id,)).fetchone()

        if visita_existente:
            raise ValueError(
                "Esta parceria já possui uma visita técnica registrada."
            )

        relatorio_path = None
        orcamento_path = None

        if relatorio_nome and relatorio_bytes:
            nome_seguro = Path(relatorio_nome).name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            destino = UPLOAD_DIR / (
                f"{parceria['codigo']}_relatorio_{timestamp}_{nome_seguro}"
            )
            destino.write_bytes(relatorio_bytes)
            relatorio_path = str(destino)

        if orcamento_nome and orcamento_bytes:
            nome_seguro = Path(orcamento_nome).name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            destino = UPLOAD_DIR / (
                f"{parceria['codigo']}_orcamento_{timestamp}_{nome_seguro}"
            )
            destino.write_bytes(orcamento_bytes)
            orcamento_path = str(destino)

        cursor = conn.execute("""
            INSERT INTO visitas (
                parceria_id,
                data_visita,
                responsavel,
                parecer,
                justificativa,
                orcamento_total,
                relatorio_nome,
                relatorio_path,
                orcamento_nome,
                orcamento_path,
                criado_em
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            parceria_id,
            data_visita,
            responsavel,
            parecer,
            justificativa,
            orcamento_total,
            Path(relatorio_nome).name if relatorio_nome else None,
            relatorio_path,
            Path(orcamento_nome).name if orcamento_nome else None,
            orcamento_path,
            agora
        ))

        visita_id = cursor.lastrowid

        for material in materiais:
            conn.execute("""
                INSERT INTO materiais_visita (
                    visita_id, tipo, diametro, quantidade, unidade
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                visita_id,
                material["tipo"],
                material.get("diametro"),
                material["quantidade"],
                material.get("unidade", "m")
            ))

        conn.execute("""
            UPDATE parcerias
            SET status = 'Visitada'
            WHERE id = ?
        """, (parceria_id,))

        conn.execute("""
            INSERT INTO historico (
                parceria_id, status, data_hora, observacao
            )
            VALUES (?, 'Visitada', ?, ?)
        """, (
            parceria_id,
            agora,
            f"Visita técnica registrada por {responsavel}. Parecer: {parecer}."
        ))

        return visita_id


def get_authorization_by_partnership(parceria_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT *
            FROM autorizacoes
            WHERE parceria_id = ?
        """, (parceria_id,)).fetchone()

        return dict(row) if row else None


def get_or_generate_authorization_summary(parceria_id):
    """Retorna o PDF resumo salvo ou o recria usando os dados registrados."""
    autorizacao = get_authorization_by_partnership(parceria_id)
    if not autorizacao:
        raise ValueError("Esta parceria ainda não possui autorização registrada.")

    caminho_salvo = autorizacao.get("resumo_path")
    if caminho_salvo and Path(caminho_salvo).is_file():
        return Path(caminho_salvo)

    with get_connection() as conn:
        parceria = conn.execute(
            "SELECT * FROM parcerias WHERE id = ?", (parceria_id,)
        ).fetchone()
        visita = conn.execute(
            "SELECT * FROM visitas WHERE parceria_id = ?", (parceria_id,)
        ).fetchone()

        if not parceria:
            raise ValueError("Parceria não encontrada para gerar o relatório.")
        if not visita:
            raise ValueError("A visita técnica não foi encontrada para gerar o relatório.")

        materiais = conn.execute(
            """SELECT tipo, diametro, quantidade, unidade
               FROM materiais_visita WHERE visita_id = ? ORDER BY id""",
            (visita["id"],),
        ).fetchall()

    dados = dict(parceria)
    dados["visita"] = dict(visita)
    dados["materiais"] = [dict(material) for material in materiais]
    dados["autorizado_por"] = autorizacao["autorizado_por"]
    dados["data_autorizacao"] = autorizacao["data_autorizacao"]
    dados["materiais_liberados"] = autorizacao.get("materiais_liberados")

    caminho_pdf = generate_summary_pdf(dados)

    with get_connection() as conn:
        conn.execute(
            """UPDATE autorizacoes
               SET resumo_nome = ?, resumo_path = ?
               WHERE parceria_id = ?""",
            (caminho_pdf.name, str(caminho_pdf), parceria_id),
        )

    return caminho_pdf


def authorize_partnership(
    parceria_id, autorizado_por, materiais_liberados=None,
    nota_fiscal_nome=None, nota_fiscal_bytes=None
):
    autorizado_por = autorizado_por.strip()

    if not autorizado_por:
        raise ValueError("Informe quem está autorizando a parceria.")

    with get_connection() as conn:
        parceria = conn.execute("""
            SELECT *
            FROM parcerias
            WHERE id = ?
        """, (parceria_id,)).fetchone()

        if not parceria:
            raise ValueError("Parceria não encontrada.")

        if parceria["status"] != "Visitada":
            raise ValueError(
                "A parceria precisa estar com status Visitada."
            )

        visita = conn.execute("""
            SELECT *
            FROM visitas
            WHERE parceria_id = ?
        """, (parceria_id,)).fetchone()

        if not visita:
            raise ValueError("A parceria ainda não possui visita técnica.")

        if visita["parecer"] not in (
            "Viável",
            "Viável com ressalvas"
        ):
            raise ValueError(
                "Somente pareceres Viável ou Viável com ressalvas "
                "podem ser autorizados."
            )

        existente = conn.execute("""
            SELECT id
            FROM autorizacoes
            WHERE parceria_id = ?
        """, (parceria_id,)).fetchone()

        if existente:
            raise ValueError("Esta parceria já foi autorizada.")

        materiais = conn.execute("""
            SELECT tipo, diametro, quantidade, unidade
            FROM materiais_visita
            WHERE visita_id = ?
            ORDER BY id
        """, (visita["id"],)).fetchall()

        agora = datetime.now().isoformat(timespec="seconds")

        nota_fiscal_path = None
        if nota_fiscal_nome and nota_fiscal_bytes:
            nome_seguro = Path(nota_fiscal_nome).name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            destino = UPLOAD_DIR / (
                f"{parceria['codigo']}_nota_fiscal_{timestamp}_{nome_seguro}"
            )
            destino.write_bytes(nota_fiscal_bytes)
            nota_fiscal_path = str(destino)

        conn.execute("""
            INSERT INTO autorizacoes
            (parceria_id, autorizado_por, data_autorizacao,
             materiais_liberados, nota_fiscal_nome, nota_fiscal_path)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            parceria_id, autorizado_por, agora,
            (materiais_liberados or "").strip() or None,
            Path(nota_fiscal_nome).name if nota_fiscal_nome else None,
            nota_fiscal_path,
        ))

        conn.execute("""
            UPDATE parcerias
            SET status = 'Autorizada'
            WHERE id = ?
        """, (parceria_id,))

        conn.execute("""
            INSERT INTO historico
            (parceria_id, status, data_hora, observacao)
            VALUES (?, 'Autorizada', ?, ?)
        """, (
            parceria_id,
            agora,
            f"Parceria autorizada por {autorizado_por}."
        ))

        dados = dict(parceria)
        dados["visita"] = dict(visita)
        dados["materiais"] = [
            dict(material) for material in materiais
        ]
        dados["autorizado_por"] = autorizado_por
        dados["data_autorizacao"] = agora
        dados["materiais_liberados"] = (materiais_liberados or "").strip() or None

    caminho_pdf = generate_summary_pdf(dados)

    with get_connection() as conn:
        conn.execute("""
            UPDATE autorizacoes
            SET resumo_nome = ?, resumo_path = ?
            WHERE parceria_id = ?
        """, (
            caminho_pdf.name,
            str(caminho_pdf),
            parceria_id
        ))

    return caminho_pdf


def generate_summary_pdf(dados):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle
    )

    parceria = dados
    visita = dados["visita"]

    nome_arquivo = (
        f"Resumo_Parceria_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.pdf"
    )

    caminho = UPLOAD_DIR / nome_arquivo

    documento = SimpleDocTemplate(
        str(caminho),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm
    )

    estilos = getSampleStyleSheet()

    titulo = ParagraphStyle(
        "TituloGPR",
        parent=estilos["Title"],
        alignment=TA_CENTER,
        fontSize=16,
        spaceAfter=16
    )

    secao = ParagraphStyle(
        "SecaoGPR",
        parent=estilos["Heading2"],
        fontSize=11,
        spaceBefore=12,
        spaceAfter=6
    )

    texto = estilos["BodyText"]

    conteudo = [
        Paragraph("RELATÓRIO RESUMO DA PARCERIA", titulo),
        Paragraph("1. IDENTIFICAÇÃO DA SOLICITAÇÃO", secao)
    ]

    identificacao = [
        ["Bacia", parceria["bacia"]],
        ["Município", parceria["municipio"]],
        ["Comunidade", parceria["comunidade"]],
        ["Origem", parceria["origem"]],
        ["Data de recebimento", parceria["data_recebimento"]],
        [
            "Número de famílias",
            str(parceria["familias"] or "Não informado")
        ]
    ]

    tabela = Table(
        identificacao,
        colWidths=[5 * cm, 11 * cm]
    )

    tabela.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 7)
    ]))

    conteudo.extend([
        tabela,
        Paragraph("2. VISITA TÉCNICA", secao)
    ])

    valor = visita["orcamento_total"]

    if valor is not None:
        valor_formatado = (
            f"R$ {float(valor):,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
    else:
        valor_formatado = "Não informado"

    visita_dados = [
        ["Data da visita", visita["data_visita"]],
        ["Responsável pela visita", visita["responsavel"]],
        ["Parecer técnico", visita["parecer"]],
        [
            "Justificativa / ressalvas",
            visita["justificativa"] or "Não informada"
        ],
        ["Orçamento total estimado", valor_formatado]
    ]

    tabela = Table(
        visita_dados,
        colWidths=[5 * cm, 11 * cm]
    )

    tabela.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 7)
    ]))

    conteudo.extend([
        tabela,
        Paragraph("3. MATERIAIS PREVISTOS", secao)
    ])

    linhas = [
        ["Material", "Diâmetro", "Quantidade", "Unidade"]
    ]

    for material in dados["materiais"]:
        linhas.append([
            material["tipo"],
            material["diametro"] or "-",
            str(material["quantidade"]),
            material["unidade"]
        ])

    if len(linhas) == 1:
        linhas.append([
            "Nenhum material informado",
            "-",
            "-",
            "-"
        ])

    tabela = Table(
        linhas,
        colWidths=[6 * cm, 3 * cm, 3 * cm, 4 * cm],
        repeatRows=1
    )

    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP")
    ]))

    conteudo.extend([
        tabela,
        Paragraph("4. AUTORIZAÇÃO DA PARCERIA", secao),
        Paragraph(
            f"Decisão: AUTORIZADA<br/>"
            f"Responsável pela autorização: {dados['autorizado_por']}<br/>"
            f"Data da autorização: {dados['data_autorizacao']}<br/>"
            f"Materiais efetivamente liberados: "
            f"{dados.get('materiais_liberados') or 'Não informado'}",
            texto
        ),
        Spacer(1, 20),
        Paragraph(
            "Documento gerado automaticamente pelo sistema GPR.",
            ParagraphStyle(
                "RodapeGPR",
                parent=texto,
                alignment=TA_CENTER,
                fontSize=8
            )
        )
    ])

    documento.build(conteudo)

    return caminho


# =====================================================================
# MÓDULO DE EXECUÇÃO
# =====================================================================

def iniciar_execucao(parceria_id, responsavel, data_inicio):
    responsavel = responsavel.strip()

    if not responsavel:
        raise ValueError("Informe o responsável pela execução.")

    agora = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        parceria = conn.execute("""
            SELECT id, codigo, status
            FROM parcerias
            WHERE id = ?
        """, (parceria_id,)).fetchone()

        if not parceria:
            raise ValueError("Parceria não encontrada.")

        if parceria["status"] != "Autorizada":
            raise ValueError(
                "Somente parcerias autorizadas podem iniciar a execução."
            )

        existente = conn.execute("""
            SELECT id
            FROM execucoes
            WHERE parceria_id = ?
        """, (parceria_id,)).fetchone()

        if existente:
            raise ValueError("Esta parceria já possui uma execução cadastrada.")

        cursor = conn.execute("""
            INSERT INTO execucoes (
                parceria_id,
                data_inicio,
                responsavel,
                status,
                criado_em,
                atualizado_em
            )
            VALUES (?, ?, ?, 'Iniciada', ?, ?)
        """, (
            parceria_id,
            data_inicio,
            responsavel,
            agora,
            agora
        ))

        execucao_id = cursor.lastrowid

        conn.execute("""
            INSERT INTO registros_execucao (
                execucao_id,
                tipo,
                data_registro,
                responsavel,
                observacao
            )
            VALUES (?, 'Iniciada', ?, ?, ?)
        """, (
            execucao_id,
            data_inicio,
            responsavel,
            "Início da execução da parceria."
        ))

        conn.execute("""
            UPDATE parcerias
            SET status = 'Iniciada'
            WHERE id = ?
        """, (parceria_id,))

        conn.execute("""
            INSERT INTO historico (
                parceria_id, status, data_hora, observacao
            )
            VALUES (?, 'Iniciada', ?, ?)
        """, (
            parceria_id,
            agora,
            f"Execução iniciada por {responsavel}."
        ))

        return execucao_id


def get_execution_by_partnership(parceria_id):
    with get_connection() as conn:
        execucao = conn.execute("""
            SELECT *
            FROM execucoes
            WHERE parceria_id = ?
        """, (parceria_id,)).fetchone()

        if not execucao:
            return None

        resultado = dict(execucao)

        registros = conn.execute("""
            SELECT *
            FROM registros_execucao
            WHERE execucao_id = ?
            ORDER BY data_registro, id
        """, (execucao["id"],)).fetchall()

        resultado["registros"] = []

        for registro in registros:
            registro_dict = dict(registro)

            arquivos = conn.execute("""
                SELECT *
                FROM arquivos_execucao
                WHERE registro_id = ?
                ORDER BY id
            """, (registro["id"],)).fetchall()

            registro_dict["arquivos"] = [
                dict(arquivo) for arquivo in arquivos
            ]

            resultado["registros"].append(registro_dict)

        return resultado


def registrar_atualizacao_execucao(
    parceria_id,
    tipo,
    data_registro,
    responsavel,
    observacao=None,
    motivo_paralisacao=None,
    previsao_retorno=None,
    arquivos=None
):
    responsavel = responsavel.strip()

    if not responsavel:
        raise ValueError("Informe o responsável pelo registro.")

    tipos_validos = [
        "Em execução",
        "Paralisada",
        "Retomada",
        "Concluída"
    ]

    if tipo not in tipos_validos:
        raise ValueError("Tipo de atualização inválido.")

    if tipo == "Paralisada" and not motivo_paralisacao:
        raise ValueError("Informe o motivo da paralisação.")

    agora = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        parceria = conn.execute("""
            SELECT id, codigo, status
            FROM parcerias
            WHERE id = ?
        """, (parceria_id,)).fetchone()

        if not parceria:
            raise ValueError("Parceria não encontrada.")

        execucao = conn.execute("""
            SELECT *
            FROM execucoes
            WHERE parceria_id = ?
        """, (parceria_id,)).fetchone()

        if not execucao:
            raise ValueError("A parceria ainda não possui execução iniciada.")

        status_atual = execucao["status"]

        if status_atual == "Concluída":
            raise ValueError(
                "Uma execução concluída não pode receber novas atualizações."
            )

        if tipo == "Retomada" and status_atual != "Paralisada":
            raise ValueError(
                "Só é possível registrar retomada de uma execução paralisada."
            )

        if tipo == "Paralisada" and status_atual == "Paralisada":
            raise ValueError("Esta execução já está paralisada.")

        if tipo == "Em execução" and status_atual == "Paralisada":
            raise ValueError(
                "Use o registro Retomada para reativar uma execução paralisada."
            )

        cursor = conn.execute("""
            INSERT INTO registros_execucao (
                execucao_id,
                tipo,
                data_registro,
                responsavel,
                observacao,
                motivo_paralisacao,
                previsao_retorno
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            execucao["id"],
            tipo,
            data_registro,
            responsavel,
            observacao,
            motivo_paralisacao,
            previsao_retorno
        ))

        registro_id = cursor.lastrowid

        for arquivo in (arquivos or []):
            nome_original = Path(arquivo["nome"]).name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            nome_salvo = (
                f"{parceria['codigo']}_execucao_"
                f"{timestamp}_{nome_original}"
            )

            caminho = UPLOAD_DIR / nome_salvo
            caminho.write_bytes(arquivo["bytes"])

            conn.execute("""
                INSERT INTO arquivos_execucao (
                    registro_id,
                    arquivo_nome,
                    arquivo_path,
                    tipo_arquivo
                )
                VALUES (?, ?, ?, ?)
            """, (
                registro_id,
                nome_original,
                str(caminho),
                arquivo.get("tipo", "Documento")
            ))

        if tipo == "Retomada" or tipo == "Em execução":
            novo_status = "Em execução"
        elif tipo == "Paralisada":
            novo_status = "Paralisada"
        else:
            novo_status = "Concluída"

        data_conclusao = (
            data_registro if novo_status == "Concluída" else None
        )

        conn.execute("""
            UPDATE execucoes
            SET status = ?,
                data_conclusao = COALESCE(?, data_conclusao),
                atualizado_em = ?
            WHERE id = ?
        """, (
            novo_status,
            data_conclusao,
            agora,
            execucao["id"]
        ))

        conn.execute("""
            UPDATE parcerias
            SET status = ?
            WHERE id = ?
        """, (novo_status, parceria_id))

        observacao_historico = (
            f"Atualização da execução: {tipo}. "
            f"Responsável: {responsavel}."
        )

        if motivo_paralisacao:
            observacao_historico += (
                f" Motivo da paralisação: {motivo_paralisacao}."
            )

        conn.execute("""
            INSERT INTO historico (
                parceria_id, status, data_hora, observacao
            )
            VALUES (?, ?, ?, ?)
        """, (
            parceria_id,
            novo_status,
            agora,
            observacao_historico
        ))

        return registro_id


# =====================================================================
# NOVO MÓDULO — ENTREGAS DE MATERIAIS
# =====================================================================

def get_materiais_previstos_com_saldo(parceria_id):
    """
    Retorna os materiais previstos na visita técnica,
    com total entregue e saldo pendente.
    """

    with get_connection() as conn:
        materiais = conn.execute("""
            SELECT
                mv.id AS material_id,
                mv.tipo,
                mv.diametro,
                mv.quantidade AS quantidade_prevista,
                mv.unidade,
                COALESCE(SUM(ie.quantidade), 0) AS quantidade_entregue
            FROM materiais_visita mv
            INNER JOIN visitas v
                ON v.id = mv.visita_id
            LEFT JOIN itens_entrega ie
                ON ie.material_visita_id = mv.id
            LEFT JOIN entregas_materiais em
                ON em.id = ie.entrega_id
            WHERE v.parceria_id = ?
            GROUP BY
                mv.id,
                mv.tipo,
                mv.diametro,
                mv.quantidade,
                mv.unidade
            ORDER BY mv.id
        """, (parceria_id,)).fetchall()

        resultado = []

        for material in materiais:
            item = dict(material)

            item["saldo_pendente"] = (
                float(item["quantidade_prevista"])
                - float(item["quantidade_entregue"])
            )

            item["percentual_entregue"] = (
                float(item["quantidade_entregue"])
                / float(item["quantidade_prevista"]) * 100
                if item["quantidade_prevista"] > 0
                else 0
            )

            resultado.append(item)

        return resultado


def registrar_entrega_materiais(
    parceria_id,
    data_entrega,
    responsavel,
    itens,
    observacao=None,
    comprovante_nome=None,
    comprovante_bytes=None
):
    """
    Registra uma entrega com um ou vários materiais.

    Cada item deve conter:
        material_id
        quantidade
        justificativa_excedente (obrigatória se ultrapassar o previsto)
    """

    responsavel = responsavel.strip()

    if not responsavel:
        raise ValueError("Informe o responsável pela entrega.")

    if not itens:
        raise ValueError("Adicione pelo menos um material à entrega.")

    agora = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        parceria = conn.execute("""
            SELECT id, codigo
            FROM parcerias
            WHERE id = ?
        """, (parceria_id,)).fetchone()

        if not parceria:
            raise ValueError("Parceria não encontrada.")

        # Validar os itens antes de gravar a entrega.
        itens_validados = []

        for item in itens:
            material_id = int(item["material_id"])
            quantidade = float(item["quantidade"])

            if quantidade <= 0:
                raise ValueError(
                    "A quantidade entregue deve ser maior que zero."
                )

            material = conn.execute("""
                SELECT
                    mv.id,
                    mv.tipo,
                    mv.diametro,
                    mv.quantidade,
                    mv.unidade
                FROM materiais_visita mv
                INNER JOIN visitas v
                    ON v.id = mv.visita_id
                WHERE mv.id = ?
                  AND v.parceria_id = ?
            """, (material_id, parceria_id)).fetchone()

            if not material:
                raise ValueError(
                    "Um dos materiais selecionados não pertence "
                    "à visita técnica desta parceria."
                )

            total_anterior = conn.execute("""
                SELECT COALESCE(SUM(ie.quantidade), 0) AS total
                FROM itens_entrega ie
                INNER JOIN entregas_materiais em
                    ON em.id = ie.entrega_id
                WHERE ie.material_visita_id = ?
            """, (material_id,)).fetchone()["total"]

            total_apos_entrega = (
                float(total_anterior) + quantidade
            )

            justificativa = (
                item.get("justificativa_excedente") or ""
            ).strip()

            if total_apos_entrega > float(material["quantidade"]):
                if not justificativa:
                    raise ValueError(
                        f"A entrega de {material['tipo']} "
                        f"ultrapassa a quantidade prevista. "
                        f"Informe uma justificativa para o excedente."
                    )

            itens_validados.append({
                "material_id": material_id,
                "quantidade": quantidade,
                "justificativa": justificativa
            })

        # Salvar comprovante, se houver.
        nome_salvo = None
        caminho_comprovante = None

        if comprovante_nome and comprovante_bytes:
            nome_original = Path(comprovante_nome).name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

            nome_salvo = (
                f"{parceria['codigo']}_comprovante_entrega_"
                f"{timestamp}_{nome_original}"
            )

            caminho = UPLOAD_DIR / nome_salvo
            caminho.write_bytes(comprovante_bytes)

            caminho_comprovante = str(caminho)

        # Criar registro principal da entrega.
        cursor = conn.execute("""
            INSERT INTO entregas_materiais (
                parceria_id,
                data_entrega,
                responsavel,
                observacao,
                comprovante_nome,
                comprovante_path,
                criado_em
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            parceria_id,
            data_entrega,
            responsavel,
            observacao,
            nome_salvo,
            caminho_comprovante,
            agora
        ))

        entrega_id = cursor.lastrowid

        # Salvar os materiais entregues.
        for item in itens_validados:
            conn.execute("""
                INSERT INTO itens_entrega (
                    entrega_id,
                    material_visita_id,
                    quantidade,
                    justificativa_excedente
                )
                VALUES (?, ?, ?, ?)
            """, (
                entrega_id,
                item["material_id"],
                item["quantidade"],
                item["justificativa"] or None
            ))

        # Registrar no histórico geral sem alterar o status da parceria.
        conn.execute("""
            INSERT INTO historico (
                parceria_id,
                status,
                data_hora,
                observacao
            )
            VALUES (?, ?, ?, ?)
        """, (
            parceria_id,
            "Entrega de materiais",
            agora,
            f"Entrega de materiais registrada por {responsavel}."
        ))

        return entrega_id


def get_entregas_materiais(parceria_id):
    """
    Retorna todas as entregas da parceria,
    incluindo os materiais de cada entrega e comprovantes.
    """

    with get_connection() as conn:
        entregas = conn.execute("""
            SELECT *
            FROM entregas_materiais
            WHERE parceria_id = ?
            ORDER BY data_entrega DESC, id DESC
        """, (parceria_id,)).fetchall()

        resultado = []

        for entrega in entregas:
            entrega_dict = dict(entrega)

            itens = conn.execute("""
                SELECT
                    ie.id,
                    ie.quantidade,
                    ie.justificativa_excedente,
                    mv.tipo,
                    mv.diametro,
                    mv.unidade,
                    mv.quantidade AS quantidade_prevista,
                    mv.id AS material_visita_id
                FROM itens_entrega ie
                INNER JOIN materiais_visita mv
                    ON mv.id = ie.material_visita_id
                WHERE ie.entrega_id = ?
                ORDER BY ie.id
            """, (entrega["id"],)).fetchall()

            entrega_dict["itens"] = [
                dict(item) for item in itens
            ]

            resultado.append(entrega_dict)

        return resultado


def get_entrega_material_by_id(entrega_id):
    """
    Retorna os detalhes de uma entrega específica.
    """

    with get_connection() as conn:
        entrega = conn.execute("""
            SELECT *
            FROM entregas_materiais
            WHERE id = ?
        """, (entrega_id,)).fetchone()

        if not entrega:
            return None

        resultado = dict(entrega)

        itens = conn.execute("""
            SELECT
                ie.id,
                ie.quantidade,
                ie.justificativa_excedente,
                mv.tipo,
                mv.diametro,
                mv.unidade,
                mv.quantidade AS quantidade_prevista,
                mv.id AS material_visita_id
            FROM itens_entrega ie
            INNER JOIN materiais_visita mv
                ON mv.id = ie.material_visita_id
            WHERE ie.entrega_id = ?
            ORDER BY ie.id
        """, (entrega_id,)).fetchall()

        resultado["itens"] = [
            dict(item) for item in itens
        ]

        return resultado
