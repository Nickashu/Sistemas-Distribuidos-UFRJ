# Manual e Documentação de Arquitetura: "A Palavra Infiltrada"

Este documento serve como guia completo de engenharia e arquitetura para o projeto **A Palavra Infiltrada**, um jogo multiplayer distribuído de dedução social projetado para a disciplina de **Sistemas Distribuídos**.

---

## 1. Visão Geral do Jogo

O jogo é inspirado no clássico board game *Undercover*.
*   **Os Inocentes**: A maioria dos jogadores recebe uma palavra secreta em comum (ex: "Praia").
*   **O Infiltrado**: Um jogador sorteado secretamente recebe uma palavra muito semelhante, mas ligeiramente diferente (ex: "Piscina").
*   **Objetivo**: Os jogadores devem enviar dicas de uma palavra, discutir via chat causal e votar para eliminar quem eles suspeitam ser o infiltrado. O infiltrado deve se passar por inocente e induzir o grupo ao erro.

---

## 2. Arquitetura do Sistema

O sistema adota uma **Arquitetura Híbrida**:
1.  **Fase Descentralizada (Peer-to-Peer - P2P)**: Quando os processos iniciam ou quando o servidor central cai, todos os nós são considerados iguais. Eles se comunicam de forma pareada para executar o **Algoritmo de Eleição Bully** e determinar quem assumirá o papel de coordenador.
2.  **Fase Centralizada (Cliente-Servidor - C/S)**: Assim que um líder é eleito, ele inicializa o componente `ServidorCerebro` (Stateful Server) que gerencia o estado da partida, as rodadas, a contagem de votos e as pontuações. Os demais nós instanciam o `ClienteJogador` e conectam-se a ele.

```mermaid
graph TD
    subgraph Inicialização / Eleição P2P
        N1[Jogador 1] <-->|Bully TCP| N2[Jogador 2]
        N2 <-->|Bully TCP| N3[Jogador 3]
        N3 <-->|Bully TCP| N1
    end
    
    subgraph Partida C/S (Líder Eleito)
        Lider[Jogador Eleito / Cérebro]
        C1[Cliente Jogador 1] -->|Conexão TCP Port 5555| Lider
        C2[Cliente Jogador 2] -->|Conexão TCP Port 5555| Lider
    end
```

---

## 3. Conceitos de Sistemas Distribuídos Implementados

### A. Sockets TCP e Enquadramento de Aplicação (Framing)
A comunicação ocorre sobre sockets TCP. Como o TCP opera como um fluxo contínuo de bytes (*byte-stream*), implementamos um protocolo estruturado de aplicação para evitar a **coalescência de mensagens** (agrupamento indesejado de pacotes):
*   **Delimitação**: Cada mensagem de aplicação termina estritamente com um caractere de quebra de linha (`\n`).
*   **Helper `enviar_msg`**: Garante que o texto seja enviado por completo (`sendall`) com o sufixo `\n`.
*   **Classe `LeitorSocket`**: Mantém um buffer interno de strings por conexão. Ele lê bytes do socket e apenas entrega mensagens completas à aplicação quando encontra o delimitador `\n`, tratando timeouts de forma transparente.

### B. Eleição de Líder (Algoritmo Bully)
O líder da partida é eleito dinamicamente:
*   **Modo Local**: Utiliza portas TCP sequenciais (`5001` a `5005`) como IDs de processos. O nó tenta se conectar às portas maiores que a sua. Se nenhuma estiver ativa, ele assume a liderança.
*   **Modo LAN (Prevenção de Split-Brain)**:
    1.  **Etapa 1**: O processo realiza uma varredura tentando conectar-se na porta do jogo (`PORTA_JOGO = 5555`) em todos os IPs participantes. Se um jogo já estiver ativo em alguma máquina, esse IP é mantido como coordenador (evitando que a entrada de um nó com IP maior quebre a partida atual).
    2.  **Etapa 2**: Se não houver servidor rodando, o maior IP vivo na rede (verificado via conexões na porta de presença `5556`) vence a eleição e inicia o `ServidorCerebro`.

### C. Concorrência e Segurança de Threads (Locks)
Ambos os lados do sistema são multi-threaded e blindados contra condições de corrida:
*   **No Servidor**: A thread principal aceita conexões (`accept()`) e dispara uma thread de execução para cada cliente. O acesso a variáveis críticas (como dicionário de conexões `self.jogadores` e `self.estado_jogo`) é protegido por um lock reentrante (`self.estado_lock`).
*   **No Cliente**: Uma thread separada captura o teclado em loop, e outra escuta a rede. O vetor de timestamps (`self.vt`) e o buffer de entrega causal do chat são protegidos por um lock de dados local (`self.vt_lock`) para evitar inconsistências durante escritas concorrentes das duas threads.

### D. Ordenação Causal (Vetor de Timestamps)
Para garantir que mensagens de chat cheguem em ordem de causa e efeito, cada cliente mantém um relógio lógico baseado em **Vetores de Timestamps**:
1.  Ao enviar uma mensagem, o cliente incrementa seu próprio relógio no vetor e envia o estado do vetor serializado (ex: `Alice=1;Bob=2`).
2.  Ao receber uma mensagem, o receptor a coloca em uma fila e avalia as condições de Raynal:
    *   $\text{V}_{\text{msg}}[sender] == \text{V}_{\text{local}}[sender] + 1$ (é a mensagem imediatamente consecutiva deste remetente).
    *   $\text{V}_{\text{msg}}[k] \le \text{V}_{\text{local}}[k]$ para todo $k \neq sender$ (o receptor já entregou todas as mensagens de outros nós que o remetente havia visto).
3.  A mensagem só é exibida na tela quando as duas condições são atendidas, garantindo a ordem lógica da conversa.

---

## 4. Fluxo da Rodada (Passo a Passo)

```
[ LOBBY ] ──(Host digita /start)──> [ DICAS ] ──(Todos enviam dicas)──> [ CHAT CAUSAL ]
                                                                             │
    [ LOBBY ] <──(Resultado e Placar)── [ VOTACAO ] <──(Todos /votar)────────┘
```

1.  **Fase de Lobby**: Jogadores conectam-se ao coordenador e podem usar o chat livre. O Host digita `/start` para começar.
2.  **Fase de Dicas**: O servidor sorteia os papéis e palavras. Cada jogador digita `/dica [palavra]` relacionada ao seu termo.
3.  **Fase de Chat**: O servidor agrupa as dicas, faz o multicast para todos e abre o chat causal.
4.  **Barreira de Sincronização**: Para avançar, os jogadores devem digitar `/votar`. Quando todos os participantes ativos derem skip no chat, a barreira é liberada.
5.  **Fase de Votação**: O chat é bloqueado. Os jogadores digitam `/voto [nome]`.
6.  **Veredito**: O servidor contabiliza os votos:
    *   Empates ou erro na eliminação: O infiltrado ganha 2 pontos.
    *   Eliminação correta: Os inocentes ganham 1 ponto cada.
    *   O estado do jogo retorna para `LOBBY`.

---

## 5. Tolerância a Falhas e Recuperação de Estado

### Queda de Jogador Comum / Infiltrado
*   O servidor detecta a desconexão no laço de leitura de socket.
*   O cérebro limpa o estado do socket caído sob proteção de lock, reduz a contagem de ativos, define o estado do jogo para `LOBBY` e avisa a todos via multicast que a partida foi interrompida, retornando os jogadores restantes ao Lobby para reiniciar.

### Queda do Servidor ("Cérebro")
1.  Os clientes detectam que a conexão TCP foi encerrada abruptamente ou falhou no timeout de 2 segundos.
2.  Os processos clientes entram no modo de eleição Bully e reconfiguram quem será o novo líder em 3 segundos.
3.  O novo líder sobe o `ServidorCerebro` em sua máquina.
4.  Os clientes conectam-se ao novo servidor e enviam um pacote especial `JOIN` contendo sua pontuação acumulada que estava guardada localmente (`MEUS_PONTOS_GLOBAIS`).
5.  O novo servidor reconstrói o placar em memória a partir dos dados consolidados dos clientes. O placar geral é preservado e a rodada reinicia no Lobby.



## Lista de Mensagens do Protocolo de Aplicação

JOIN|NAME:<n>|CEREBRO:<c>|PTS:<p>	Cliente ➔ Servidor	Enviada imediatamente após conectar para registrar o jogador e recuperar seus pontos.

REJECT|MSG:<texto>	Servidor ➔ Cliente	Enviada se o jogador tenta entrar em um jogo que já iniciou (fora da fase de lobby).

SYS|MSG:<texto>	Servidor ➔ Cliente	Mensagens informativas do sistema (ex: "Fulano entrou", tabelas de pontuação).

ROLE|ROLE:<papel>|WORD:<palavra>	Servidor ➔ Cliente	Enviada privadamente no início da partida para dar a palavra e a função (Inocente/Infiltrado).

TIP_REQ|MSG:<texto>	Servidor ➔ Cliente	Notificação multicast avisando que a fase de dicas começou.

TIP|WORD:<dica>	Cliente ➔ Servidor	Enviada quando o jogador digita /dica [palavra].

ALL_TIPS|LIST:<lista_dicas>	Servidor ➔ Cliente	Envia a lista compilada contendo a dica de todos os jogadores ativos.

CHAT_START|MSG:<texto>	Servidor ➔ Cliente	Notificação multicast que limpa os vetores e avisa que o chat está aberto.

CHAT_MSG|VT:<vetor>|MSG:<texto>	Cliente ➔ Servidor	Envia uma mensagem comum de chat contendo o vetor de timestamps para ordenação causal.

CHAT_MSG|MSG:/start	Cliente ➔ Servidor	Comando enviado pelo Host para iniciar o jogo.

CHAT_MSG|MSG:/votar	Cliente ➔ Servidor	Comando enviado pelo jogador que quer pular a fase de chat e ir para a votação.

CHAT|FROM:<r>|VT:<vetor/NULL>|MSG:<texto>	Servidor ➔ Cliente	Retransmissão (multicast) do chat para que todos os clientes recebam a mensagem.

CHAT_END|MSG:<texto>	Servidor ➔ Cliente	Notificação multicast que bloqueia o chat e avisa que a fase de votos começou.

VOTE|TARGET:<nome>	Cliente ➔ Servidor	Enviada quando o jogador vota em alguém com /voto [nome].

SCORE_UPDATE|PTS:<pontos>	Servidor ➔ Cliente	Enviada no fim da rodada para que o cliente atualize seu cache local de pontos.

ROUND_END|RESULT:<texto>	Servidor ➔ Cliente	Notificação multicast contendo o veredito final da rodada.

REQ_SCORE|MSG:null	Cliente ➔ Servidor	Enviada quando o jogador digita /placar.