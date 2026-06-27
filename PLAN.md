# Plano - Criação dos Templates das Regras do Workspace (Task 5)

Este plano descreve as etapas para criar os templates de regras do workspace (`CLAUDE.md.template` e `AGENTS.md.template`), adaptar o script de bootstrap e gerar os arquivos finais.

## Requisitos
1. **Sem Emojis ou Ícones**: Os templates e arquivos finais não devem conter nenhum emoji, ícone ou ornamento visual.
2. **Princípios do Humanizer**:
   - Escritos em Português claro, direto e profissional (tom humano).
   - Sem clichês comuns de IA ("delve", "leverage", "testament to", "feel free to", etc.).
   - Instrução explícita para que o agente escreva todas as saídas (commits, PRs, wiki, comentários) de forma natural, profissional e sem emojis/ícones.
3. **Competências de Especialistas**:
   - **Programming & Architecture**: TDD estrito, SOLID, design modular, contratos de design como limites, preservação de docstrings/comentários.
   - **Quantitative Trading & DRL/ML Engineer**:
     - Hipótese de Modelo: Sharpe ratio alvo, limite de Drawdown, Profit factor, restrições de latência/slippage, features/dataset, arquitetura do modelo.
     - Validação: Prevenção de overfitting, cross-validation, testes fora da amostra (out-of-sample). Zero vazamento de dados (data leakage).
     - Segurança: Validação de shapes de tensores, divisões por zero, overflow de floats.
   - **QA Specialist**: Testes unitários/integração mandatórios, mocks de chamadas de API, testes de backtesting.
   - **Scrum Master**: Instruções de uso do `scripts/scrum-master.sh` para issues/milestones.
   - **Code Reviewer**: Validação inicial de conformidade com a especificação, seguida pela qualidade do código.
4. **Ciclo de Vida do Workflow**:
   - Conception (criar issue via scrum-master.sh) -> Planning (criar PLAN.md) -> Execution (TDD) -> Verification -> Code Review -> Release & Wiki Sync (wiki-sync.sh).
5. **Variáveis de Interpolação**:
   - Uso de `{{PROJECT_NAME}}`, `{{TECH_STACK}}` e `{{GIT_REMOTE}}`.

## Etapas de Execução
- [ ] Atualizar `scripts/bootstrap-agent.sh` para também realizar a interpolação de `{{TECH_STACK}}` substituindo-a pelo valor de `TECHNOLOGIES`.
- [ ] Criar o diretório `templates/` no workspace se ainda não existir.
- [ ] Criar o template `templates/CLAUDE.md.template` seguindo estritamente os requisitos (Sem emojis, Português natural/profissional, Especialistas, Ciclo de Vida, Variáveis).
- [ ] Criar o template `templates/AGENTS.md.template` seguindo as mesmas diretrizes de formato, estilo e tom humano.
- [ ] Executar `./scripts/bootstrap-agent.sh` para atualizar e gerar os arquivos `CLAUDE.md` e `.agents/AGENTS.md` finais.
- [ ] Verificar o conteúdo gerado para garantir conformidade com os requisitos.
- [ ] Adicionar os templates criados e os arquivos gerados no git staging area.
- [ ] Realizar o commit com a mensagem: `feat: add core workspace rules templates and generate instructions`.
