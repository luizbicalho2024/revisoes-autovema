# Dealer Hub — Revisões Autovema

MVP em **Python + Streamlit + MongoDB Atlas** para consolidar a base de clientes e veículos das Autovemas, acompanhar a jornada de revisões e medir retenção/evasão do pós-venda.

## Escopo implementado

- Login com senhas em hash `bcrypt`.
- Níveis de acesso: **Superadministrador, Administrador, Gestor, Operador e Consulta**.
- Restrição opcional por código de empresa/concessionária.
- Importação do relatório `REL_VEICULOSVENDIDOSPORPERIODO` em `.xlsx`.
- Atualização idempotente (upsert) de clientes, veículos e vendas, evitando duplicidade.
- Chaves de consolidação:
  - Cliente: CPF/CNPJ; fallback para código da pessoa + empresa.
  - Veículo: chassi; fallback para código do veículo + empresa.
  - Venda: código da nota fiscal + empresa.
- Histórico de importações com SHA-256 do arquivo.
- Jornada da 1ª à 5ª revisão.
- Registro de revisão realizada, agendada, pendente, evasão e demais estados.
- Regras de prazo/quilometragem configuráveis, sem assumir periodicidade universal.
- Programa **Recompra Garantida Fidelidade**:
  - 3ª revisão completa: 1% de bônus.
  - 4ª revisão completa: 2% de bônus.
  - 5ª revisão ou mais: 3% de bônus.
  - qualquer revisão marcada como realizada fora/evasão cancela a elegibilidade.
- Dashboard com base consolidada, retenção por revisão, elegibilidade e vendas por mês.
- Cadastro/edição de usuários e escopo de acesso.
- Auditoria de login, importação, revisão, usuários e configurações.
- Exportações analíticas em CSV.

> A documentação do projeto contém uma inconsistência textual no exemplo da 5ª revisão, citando 10%, enquanto a tabela da regra define 3% como máximo. Este MVP utiliza a regra tabulada: **3%**.

## Coleções MongoDB

- `users`
- `customers`
- `vehicles`
- `sales`
- `journeys`
- `revisions`
- `import_jobs`
- `audit_logs`
- `settings`

Os índices necessários são criados automaticamente ao iniciar a aplicação.

## Configuração do MongoDB Atlas

1. Crie um cluster no MongoDB Atlas.
2. Crie um usuário de banco com acesso ao database escolhido.
3. Em **Network Access**, permita acesso do Streamlit Cloud. Como os IPs do Streamlit podem variar, algumas implantações usam `0.0.0.0/0`; se fizer isso, use senha longa/aleatória e usuário exclusivo com o menor privilégio possível.
4. Copie a connection string `mongodb+srv://...`.

## Deploy no Streamlit Community Cloud

No Streamlit Cloud:

- Repositório: `luizbicalho2024/revisoes-autovema`
- Branch: `main`
- Main file: `app.py`

Em **Settings → Secrets**, configure:

```toml
[mongo]
uri = "mongodb+srv://USUARIO:SENHA@SEU-CLUSTER.mongodb.net/?retryWrites=true&w=majority"
database = "dealer_hub"

[auth]
bootstrap_name = "Administrador Dealer Hub"
bootstrap_email = "seu.email@empresa.com.br"
bootstrap_password = "SENHA-INICIAL-FORTE"

[app]
timezone = "America/Porto_Velho"
session_timeout_hours = 8
```

No primeiro start, se `users` estiver vazia, o sistema cria o superadministrador usando os valores de `auth.bootstrap_*`. Depois do login, altere a senha em **Minha Conta**.

## Importação do REL_VEICULOS

Use a página **Importar REL_VEICULOS** e envie o `.xlsx` gerado no mesmo padrão do relatório utilizado na implantação.

A importação não apaga dados já existentes. Ela atualiza registros pelas chaves estáveis e cria somente o que ainda não existe. Reimportar a mesma planilha é seguro.

Dados operacionais e planilhas não devem ser versionados no GitHub. O `.gitignore` bloqueia `xlsx`, `xls`, `csv`, `parquet` e `jsonl`.

## Jornada de revisões

A documentação determina que a revisão siga o manual do fabricante por tempo ou quilometragem. Por isso o projeto não grava periodicidades inventadas.

Após o primeiro login administrativo:

1. Acesse **Configurações**.
2. Preencha meses após a venda e/ou quilometragem para a 1ª à 5ª revisão conforme regra homologada pela operação.
3. Clique em **Recalcular planos**.
4. Acesse **Jornada de Revisões** para registrar os eventos.

## Desenvolvimento local

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
mkdir -p .streamlit
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
streamlit run app.py
```

No Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .\.streamlit\secrets.example.toml .\.streamlit\secrets.toml
streamlit run app.py
```

## Segurança

- Não versione `secrets.toml`.
- Não versione planilhas contendo CPF/CNPJ, telefone, e-mail, chassi ou outros dados pessoais.
- Use usuário exclusivo do MongoDB para a aplicação.
- Revogue o bootstrap password após criar e validar o primeiro administrador, ou substitua por um valor aleatório forte.
- Perfis com escopo de empresa vazio enxergam todas as empresas.

## Próximas integrações previstas pelo desenho do projeto

A arquitetura já deixa separadas as camadas para futuras integrações de CRM/Syonet, WhatsApp oficial, NPS/CSAT, ordens de serviço e dados automáticos de revisões. Essas integrações não foram simuladas neste MVP porque os respectivos contratos de API e fontes de dados não estavam presentes na documentação fornecida.
