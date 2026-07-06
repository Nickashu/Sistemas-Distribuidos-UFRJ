# Documentação de Arquitetura de Sistemas Distribuídos: "A Palavra Infiltrada"

Este documento detalha as decisões arquiteturais, os protocolos de comunicação e os algoritmos distribuídos utilizados no desenvolvimento do jogo **Palavra Infiltrada**.

---

## 1. Estilos Arquiteturais (Híbrido: P2P e Cliente-Servidor)

O sistema foi estruturado sobre um modelo arquitetural **híbrido**, que transita entre redes descentralizadas (Peer-to-Peer) e centralizadas (Cliente-Servidor) para resolver a coordenação e a tolerância a falhas:

*   **Fase Descentralizada (Peer-to-Peer)**: Quando a partida inicia ou quando ocorre a queda do servidor principal, os nós operam de forma simétrica (P2P). Não há um ponto único de autoridade; todos os processos ativos coordenam-se de forma direta para rodar o **Algoritmo de Eleição Bully** e estabelecer o líder.
*   **Fase Centralizada (Cliente-Servidor)**: Uma vez definido o líder, o estilo arquitetural migra para o modelo clássico **Cliente-Servidor com Estado (Stateful Server)**.
    *   *Justificativa*: Gerenciar o estado global de uma partida (cofre de pontuações, palavra secreta de cada jogador, controle de turnos de envio de dicas, sincronismo de votos) de forma puramente descentralizada geraria um overhead excessivo de mensagens de consenso. Centralizar o estado temporariamente no nó **Cérebro** simplifica drasticamente a validação de regras de negócios e a ordenação de turnos.

---

## 2. Protocolos de Transporte e Comunicação

O projeto adota decisões bem demarcadas nas camadas de transporte da pilha TCP/IP, utilizando sockets para finalidades distintas:

### A. Camada de Transporte Confiável (Sockets TCP)
Para o fluxo do jogo (Lobby, Dicas, Chat e Votação) e a eleição distribuída, o protocolo adotado é o **TCP (`socket.SOCK_STREAM`)**.
*   *Justificativa*: A dinâmica de um jogo de dedução social exige entrega garantida e em ordem de pacotes. Se um pacote contendo um voto ou uma dica for perdido ou duplicado, a integridade da partida é destruída. O TCP garante controle de fluxo, retransmissão de pacotes perdidos e entrega ordenada no nível de transporte.

### B. Camada de Transporte Não-Confiável (Sockets UDP com Broadcast)
Para a fase de auto-descoberta dinâmica de jogadores na LAN, o protocolo adotado é o **UDP (`socket.SOCK_DGRAM`)**.
*   *Justificativa*: Sockets UDP não possuem overhead de estabelecimento de conexão (handshake) e suportam **IP Broadcast (`255.255.255.255`)**. Isso permite que um processo anuncie seu IP para todas as máquinas da sub-rede local simultaneamente. A perda ocasional de um ping de descoberta é inofensiva, pois o envio é executado de forma contínua em segundo plano.

### C. Modelos de Comunicação: Unicast, Multicast e Broadcast
O sistema de comunicação do projeto faz uso explícito de três estratégias distintas de envio de dados na rede:
1.  **Unicast (TCP)**: Comunicação um-para-um direta. Utilizado quando um cliente envia comandos ao servidor (ex: `/dica` e `/voto`) ou quando o servidor envia respostas privadas para conexões individuais (ex: `ROLE` com a palavra secreta ou `SCORE_UPDATE` com a pontuação privada).
2.  **Multicast em Nível de Aplicação (TCP)**: Comunicação um-para-muitos. Utilizado para a distribuição de mensagens de chat causal, dicas compiladas (`ALL_TIPS`), travamento de fases (`CHAT_END`) e resultados de rodadas (`ROUND_END`). É implementado em estrela através do método `enviar_multicast` do `ServidorCerebro`, que itera sobre o conjunto de conexões ativas enviando a cópia dos dados.
3.  **Broadcast IP (UDP)**: Comunicação um-para-todos na sub-rede. Utilizado no serviço de auto-descoberta na LAN. A thread em segundo plano envia pacotes UDP para o IP de broadcast limitado `255.255.255.255` na porta `5557`, permitindo que todas as máquinas na mesma rede física descubram as outras dinamicamente sem precisar de um servidor de registro ou digitação manual.

### D. Protocolo de Aplicação Inventado e Enquadramento (Framing)
O protocolo de aplicação opera em texto plano (UTF-8) com delimitadores lógicos:
*   **Formato Geral**: `COMANDO|ATRIBUTO1:VALOR1|ATRIBUTO2:VALOR2`
*   **Problema da Coalescência de Bytes do TCP**: Sockets TCP operam como fluxos de bytes contínuos (*byte-streams*) e não possuem limites de mensagens nativos. Se o servidor enviar duas mensagens seguidas rapidamente, o TCP pode agrupá-las no buffer, entregando-as juntas ao receptor (ex: `SCORE_UPDATE|...ROUND_END|...`), o que causa erros de parse.
*   **Solução (Delimitação por Quebra de Linha)**: Cada mensagem enviada via helper `enviar_msg` termina estritamente com `\n`. O receptor utiliza a classe `LeitorSocket` para reter os dados em um buffer em memória e só expor strings inteiras quando um caractere `\n` é detectado.

---

## 3. Concorrência e Multitarefa (Threads)

A implementação de concorrência foi estruturada de forma assíncrona usando threads de sistema operacional (`threading.Thread` no Python) tanto no cliente quanto no servidor:

### A. Servidor Concorrente (Dispatcher-Worker)
O `ServidorCerebro` utiliza um modelo de thread dispatcher com worker threads:
1.  A thread dispatcher fica bloqueada no loop `accept()` aguardando novas conexões TCP na porta `5555`.
2.  Ao aceitar uma conexão, ela despacha o socket para uma nova thread dedicada que executará o laço `tratar_cliente(conn, addr)`.
3.  Isso impede que uma chamada de sistema bloqueante (como aguardar a dica ou o voto de um cliente lento) congele o servidor para os demais jogadores ativos.

### B. Cliente Concorrente
O `ClienteJogador` mantém três threads ativas simultaneamente:
1.  **Thread Principal (Lógica/Interface)**: Fica bloqueada na fila local capturando o que o usuário digitou e transmitindo as mensagens/comandos formatados para o servidor.
2.  **Thread de Leitura de Teclado**: Roda em loop eterno executando `sys.stdin.readline()`. Como ler do console no terminal é uma operação bloqueante de E/S, ela precisa de uma thread separada para evitar que o congelamento do terminal trave o recebimento de mensagens vindas da rede.
3.  **Thread de Escuta do Socket**: Roda o laço `ler_mensagens_iter()` aguardando mensagens vindas do servidor para exibi-las instantaneamente no terminal.

---

## 4. Coordenação, Algoritmo Bully e Prevenção de Split-Brain

A eleição do líder é realizada através de uma adaptação do **Algoritmo de Eleição Bully**. 

### A. ID e Espaço de Endereçamento
*   **Local**: O ID do processo é representado pelo número da porta TCP (`5001` a `5005`) vinculado na máquina. Para evitar o bug do Windows em que múltiplos processos ativos se ligavam à mesma porta local via `SO_REUSEADDR`, removemos essa flag do socket bully local, forçando o bind a falhar de forma nativa e garantindo a unicidade de portas como IDs.
*   **LAN**: O ID do processo é representado numericamente pelo seu endereço IP (ordenado via comparação de sockets raw).

### B. Prevenção de Split-Brain e Jitter Aleatório
Em redes descentralizadas, o fenômeno de *split-brain* ocorre quando um grupo se divide e elege múltiplos coordenadores simultaneamente. Tratamos isso em dois níveis:

1.  **Varredura Preventiva de Jogo Ativo**: Antes de iniciar a eleição tradicional de IPs, o processo varre todos os IPs participantes na porta de jogo `5555`. Se algum jogo já estiver ativo, o IP dele é retornado imediatamente como o líder. Isso protege partidas em andamento e impede que novos nós com IPs maiores que entram na rede se declarem líderes indevidamente.
2.  **Jitter Aleatório (Atraso com Ruído)**: Quando o Cérebro cai, os clientes detectam a perda de conexão. Em vez de iniciarem a eleição ao mesmo tempo, introduzimos jitter aleatório:
    $$\text{Tempo de Espera} = 3.0 + \text{random}(0.1, 1.0) \text{ segundos}$$
    O nó de maior ID tende a acordar primeiro, rodar a eleição Bully, declarar-se líder e inicializar o `ServidorCerebro` na porta `5555`. Quando os nós menores acordarem do jitter, eles detectarão a porta `5555` ativa no líder e se conectarão de forma limpa como clientes, sem precisar disparar varreduras bully redundantes e concorrentes na rede.

---

## 5. Sincronização Lógica e Chat Causal

Para garantir a lógica de discussões distribuídas (onde perguntas nunca devem aparecer após as respostas por conta de atrasos de transmissão), o chat do jogo implementa **Relógios Vetoriais (Vector Timestamps)**.

```
Jogador A: "Quem é o Infiltrado?" [A:1] (latência física)
Jogador B: Recebe [A:1], responde: "É o Carlos!" [A:1, B:1]
Carlos: Recebe msg de Bob [A:1, B:1] antes da msg de Alice
Carlos compara relógios: Carlos local [A:0, B:0] vs Mensagem [A:1, B:1]
Carlos não viu Alice=1 ainda. Mensagem de Bob é retida.
Carlos recebe msg de Alice [A:1] ➔ Imprime Alice ➔ Libera msg de Bob ➔ Imprime Bob.
```

### A. Incremento e Transmissão
Cada processo de jogador mantém um dicionário `self.vt` que mapeia o nome de cada jogador conhecido ao seu relógio lógico.
*   Ao digitar uma mensagem de chat no terminal, o cliente incrementa seu relógio local:
    $$\text{VT}_{\text{local}}[\text{meu\_nome}] = \text{VT}_{\text{local}}[\text{meu\_nome}] + 1$$
*   A mensagem é encapsulada com o vetor formatado: `CHAT_MSG|VT:Alice=1;Bob=0|MSG:Mensagem` e enviada ao servidor.

### B. Entrega Causal
Ao receber um multicast de chat com um vetor $\text{VT}_{\text{msg}}$ associado ao remetente $r$, o cliente retém a mensagem no buffer `self.buffer_msgs` e avalia as condições de entrega:
1.  **Condição 1 (Ordem Direta)**: O relógio do remetente na mensagem é exatamente igual ao relógio local do remetente + 1:
    $$\text{VT}_{\text{msg}}[r] == \text{VT}_{\text{local}}[r] + 1$$
2.  **Condição 2 (Histórico Causal)**: Para qualquer outro jogador $k$, o receptor já entregou todas as mensagens que o remetente $r$ já havia entregue antes de transmitir a mensagem atual:
    $$\forall k \neq r, \quad \text{VT}_{\text{msg}}[k] \le \text{VT}_{\text{local}}[k]$$

A mensagem é impressa na tela assim que ambas as condições forem atendidas. O relógio local é então incrementado ($\text{VT}_{\text{local}}[r] = \text{VT}_{\text{local}}[r] + 1$) e o buffer é reavaliado recursivamente.

---

## 6. Sincronização de Dados (Locks)

Como os sockets e as threads operam de forma concorrente em memória compartilhada, a consistência de dados é mantida com locks estruturados:
*   **Servidor**: Um lock de exclusão mútua protege todas as leituras e mutações do dicionário de conexões dos jogadores e transições da máquina de estados do jogo. Isso evita corrupções de estado se dois jogadores enviarem dicas ou votos no mesmo milésimo de segundo.
*   **Cliente**: Impede que a thread de input (que incrementa o vetor ao enviar dados do console) e a thread de rede (que altera o vetor ao entregar mensagens ordenadas) corrompam o estado do dicionário.

---

## 7. Tolerância a Falhas e Recuperação de Placar

O sistema implementa tolerância a falhas utilizando replicação de dados baseada em clientes:
1.  A pontuação acumulada do jogo é armazenada localmente em cada cliente ativo através do cache `MEUS_PONTOS_GLOBAIS`.
2.  Quando o Cérebro cai, os clientes detectam a perda de conexão, reelegem um novo líder, que por sua vez inicializa um novo `ServidorCerebro`.
3.  Ao conectar no novo servidor, o pacote `JOIN` carrega consigo o valor de `MEUS_PONTOS_GLOBAIS`.
4.  O novo servidor recupera o estado consolidado da pontuação acumulada de todos os clientes no lobby, reiniciando o jogo sem perdas do placar original.

---

## 8. Protocolo de Aplicação Criado (Especificação de Mensagens)

Para a troca de dados estruturados na camada de aplicação sob o enquadramento de quebra de linha (`\n`), projetamos e implementamos o seguinte protocolo:

| Comando / Mensagem | Direção | Formato do Pacote (String UTF-8) | Descrição e Gatilho |
| :--- | :--- | :--- | :--- |
| **`JOIN`** | Cliente ➔ Servidor | `JOIN\|NAME:<apelido>\|CEREBRO:<true/false>\|PTS:<pontos>` | Enviado após o estabelecimento da conexão TCP para registro do apelido do jogador, envio da sua flag de liderança (`is_cerebro`) e recuperação de pontuação acumulada (`MEUS_PONTOS_GLOBAIS`). |
| **`REJECT`** | Servidor ➔ Cliente | `REJECT\|MSG:<texto>` | Enviado se o jogo já estiver em andamento (fase diferente de Lobby) ou se o apelido escolhido já estiver em uso. |
| **`SYS`** | Servidor ➔ Cliente | `SYS\|MSG:<texto>` | Encapsula mensagens globais e informativas do sistema enviadas pelo servidor (ex: lobby, notificações de votação, placares). |
| **`ROLE`** | Servidor ➔ Cliente | `ROLE\|ROLE:<papel>\|WORD:<palavra>` | Mensagem unicast privada com o papel (`INOCENTE` ou `INFILTRADO`) e a palavra secreta sorteada para a rodada. |
| **`TIP_REQ`** | Servidor ➔ Cliente | `TIP_REQ\|MSG:<texto>` | Notificação em multicast convocando os jogadores a enviarem suas dicas iniciais. |
| **`TIP`** | Cliente ➔ Servidor | `TIP\|WORD:<dica>` | Enviado pelo jogador contendo sua dica secreta digitada via `/dica [palavra]`. |
| **`ALL_TIPS`** | Servidor ➔ Cliente | `ALL_TIPS\|LIST:<lista_dicas>` | Retransmissão multicast da lista de dicas unificada de todos os jogadores (separadas pelo delimitador `&&`). |
| **`CHAT_START`** | Servidor ➔ Cliente | `CHAT_START\|MSG:<texto>` | Notificação multicast avisando a abertura do chat livre. Limpa as instâncias locais do vetor de timestamps do cliente. |
| **`CHAT_MSG`** | Cliente ➔ Servidor | `CHAT_MSG\|VT:<vetor>\|MSG:<texto>` | Mensagem de chat digitada pelo usuário, contendo o estado atualizado do relógio lógico causal do nó (ex: `Alice=1;Bob=0`). |
| **`CHAT_MSG` (Start)** | Cliente ➔ Servidor | `CHAT_MSG\|MSG:/start` | Mensagem enviada pelo Host do jogo para transicionar a partida do `LOBBY` para `DICAS`. |
| **`CHAT_MSG` (Votar)** | Cliente ➔ Servidor | `CHAT_MSG\|MSG:/votar` | Mensagem que indica ao servidor o desejo do jogador de pular a fase de chat e transicionar para o voto secreto. |
| **`CHAT`** | Servidor ➔ Cliente | `CHAT\|FROM:<remetente>\|VT:<vetor/NULL>\|MSG:<texto>` | Retransmissão multicast das mensagens de chat. Se o vetor for `NULL` (Lobby), o cliente exibe a mensagem de imediato; caso contrário, processa a ordenação causal. |
| **`CHAT_END`** | Servidor ➔ Cliente | `CHAT_END\|MSG:<texto>` | Notificação multicast que encerra a discussão do chat livre e bloqueia o canal de escrita comum dos clientes. |
| **`VOTE`** | Cliente ➔ Servidor | `VOTE\|TARGET:<nome>` | Voto secreto contra um jogador suspeito de ser o infiltrado, emitido via `/voto [nome]`. |
| **`SCORE_UPDATE`** | Servidor ➔ Cliente | `SCORE_UPDATE\|PTS:<pontos>` | Mensagem privada de fim de rodada usada para sincronizar e persistir no cache local do cliente seu total de pontos acumulados. |
| **`ROUND_END`** | Servidor ➔ Cliente | `ROUND_END\|RESULT:<texto>` | Notificação multicast contendo o veredito final da rodada de jogo. |
| **`REQ_SCORE`** | Cliente ➔ Servidor | `REQ_SCORE\|MSG:null` | Requisição enviada quando o jogador digita `/placar` no lobby para obter a lista de pontos. |

