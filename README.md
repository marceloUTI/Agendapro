# AgendaPro — MVP web responsivo

Projeto acadêmico de gestão de serviços domésticos. Implementação das 6 telas do protótipo: login, dashboard, clientes, agendamentos, orçamentos e financeiro. O Figma original é mobile; a interface se adapta a desktop com barra lateral.

## Requisitos

- Python 3.10+ instalado
- MySQL Server 8+ e MySQL Workbench (opcional)
- VS Code ou terminal

## Como executar no Windows

1. Extraia o ZIP e abra a pasta `AgendaPro_MVP` no VS Code.
2. Abra o MySQL Workbench, conecte-se ao servidor e execute **todo** o arquivo `schema.sql` (botão raio). Isso cria o banco e as tabelas.
3. Na pasta do projeto, copie `.env.example` e renomeie a cópia para `.env`. Edite `MYSQL_USER`, `MYSQL_PASSWORD` e `SECRET_KEY` com os dados do seu MySQL. Não compartilhe `.env` no GitHub.
4. No terminal do VS Code, execute:

   ```powershell
      py -m venv .venv
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      .\.venv\Scripts\Activate.ps1
      python -m pip install -r requirements.txt
      python app.py
git --version
5. Abra `http://127.0.0.1:5000` no navegador. Clique em **Cadastre-se**, crie uma conta e entre.
6. Cadastre primeiro um cliente; depois crie agendamentos, orçamentos e pagamentos. Os indicadores são calculados com os dados reais da conta.

Se o PowerShell bloquear a ativação, use `.venv\Scripts\python.exe -m pip install -r requirements.txt` e `.venv\Scripts\python.exe app.py` sem ativar o ambiente.

## Estrutura

- `app.py`: rotas, autenticação, CRUD, relatórios e conexão MySQL
- `schema.sql`: banco de dados e relacionamentos
- `templates/`: telas HTML e formulários
- `static/style.css`: layout responsivo
- `static/app.js`: menu, modais, busca e calendário
- `.env.example`: modelo de configuração (não contém senha real)

## Funcionalidades desta versão

- Cadastro e login com hash de senha e sessão
- Clientes: cadastrar, pesquisar, editar, excluir
- Agendamentos: cadastrar, listar, alterar status, excluir, visualizar mês no calendário
- Orçamentos: cadastrar, listar, alterar status, excluir, baixar PDF, abrir mensagem pré-preenchida no WhatsApp
- Financeiro: registrar pagamento, alterar status, excluir e ver indicadores
- Dashboard: indicadores dinâmicos e próximos agendamentos
- Layout mobile e desktop

## Limitações e próximos passos

- O botão WhatsApp **não anexa automaticamente o PDF**: baixe o arquivo e anexe manualmente no WhatsApp.
- Não há recuperação de senha por e-mail, edição de agendamentos, rotas de mapa, notificações, CSRF token ou deploy de produção.
- O calendário mostra indicadores de dias com agendamento; a lista exibe os registros.
- Não há dados de exemplo: a conta começa vazia.
- **Não use em produção com `debug=True`**. Esta versão é para desenvolvimento local e apresentação acadêmica. Antes de publicar, adicionar proteção CSRF, validação mais completa, migrações, testes automatizados e configuração segura.
- Ao excluir cliente, os registros associados também são apagados; confirme antes de excluir.

## Demonstração sugerida

Criar conta → cadastrar cliente → marcar serviço → gerar orçamento em PDF → compartilhar texto no WhatsApp → registrar pagamento → mostrar indicadores atualizados.
