# GPR — Gestão de Parcerias Rurais

Pacote atualizado do protótipo GPR.

## Como executar no Windows

1. Instale Python 3.10 ou superior.
2. Extraia este ZIP em uma pasta do computador.
3. Abra a pasta `GPR` no VS Code.
4. Abra o terminal do VS Code e execute:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

5. O navegador abrirá o sistema localmente. Para encerrar, volte ao terminal e pressione `Ctrl + C`.

## Funcionalidades incluídas nesta versão

- Cadastro de novas solicitações de parceria.
- Seleção das oito bacias: BAJ, BPA, BME, BCL, BSA, BBA, BBJ e BAC.
- Município e comunidade digitados livremente.
- Número de famílias e ofício opcionais.
- Geração automática de código por bacia (ex.: `GPR-BAJ-0001`).
- Status inicial automático: `Não visitada`.
- Consulta, busca e filtros das parcerias cadastradas.
- Visualização dos detalhes de cada parceria e download do ofício, quando anexado.
- Painel geral com indicadores e consulta de registros.
- Banco SQLite criado automaticamente na primeira execução.

## Importante sobre seus dados

Este ZIP não inclui um banco `gpr.db` com dados de teste. Ao executar pela primeira vez, o sistema cria o banco local na pasta `GPR`.

Se você já possui cadastros no seu computador, **não substitua nem apague o arquivo `gpr.db` nem a pasta `documentos`** da sua instalação atual. Para atualizar o aplicativo, faça uma cópia de segurança desses itens e mantenha-os na pasta do projeto atualizado.

## Próximas etapas

O registro da visita técnica, parecer, materiais, orçamento, anexos do relatório e fluxo de autorização ainda serão implementados na próxima etapa. Esta versão não contém essas funções.

Para uso simultâneo por várias pessoas, ainda será necessário configurar hospedagem, banco PostgreSQL, armazenamento persistente de documentos, autenticação e permissões por perfil.
