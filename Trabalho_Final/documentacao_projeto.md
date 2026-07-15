# Documentação - Palavra Infiltrada

Este documento detalha os fundamentos teóricos de **Sistemas Distribuídos (SD)** do projeto **Palavra Infiltrada**. Ele serve como um roteiro de apresentação completo, organizado por assuntos na ordem lógica ideal do fluxo da apresentação acadêmica e da demonstração prática.

---

## 1. Conceito do Jogo e Estado Compartilhado
O jogo lida diretamente com o problema de **Estado Global Compartilhado Parcialmente Oculto** em um sistema distribuído.
*   **Problema de Consistência e Confidencialidade**: Cada processo (nó) possui visibilidade estritamente local do seu próprio estado (seu papel e sua palavra secreta). O estado global do jogo (quem é o infiltrado) é ocultado por questões de regras de negócio.
*   **Decisão de Segurança**: As palavras secretas são armazenadas no código e transmitidas na rede codificadas em **Base64**. Isso impede que um jogador malicioso inspecione a memória do processo ou fareje os pacotes de rede (sniffing) para trapacear.

---

## 2. Fluxo da Partida e Barreiras de Sincronização
A execução transiciona de forma síncrona por seis fases de negócio distintas:

1.  **Lobby**: Os jogadores entram na sala de chat comum. O primeiro nó a iniciar vira o coordenador (**Cérebro**) e assume a liderança do Lobby. Quando o Cérebro digita `/start`, a rodada começa.
2.  **Distribuição de Papéis**: O Cérebro seleciona aleatoriamente um par de palavras ocultas (codificadas em Base64). Sorteia quem será o Infiltrado e distribui as palavras de forma privada via canal unicast TCP para cada jogador.
3.  **Fase de Dicas**: Cada jogador deve enviar exatamente uma dica associada à sua palavra usando o comando `/dica [palavra]`. 
    *   *Sincronização*: O servidor utiliza uma **barreira de sincronização lógica** (aguarda até que todas as dicas tenham chegado) antes de compilar a lista unificada e transmiti-la por multicast a todos. Isso evita inconsistências causadas por latências de rede ou tempos de digitação diferentes entre os nós.
4.  **Fase de Chat (Discussão e Blefe)**: Abre-se um canal de debate livre no console. O chat é ordenado por **relógios vetoriais** para evitar que mensagens de discussões fiquem fora de ordem causal lógica devido a atrasos na rede.
5.  **Votação Final**: Quando todos os jogadores enviam o comando `/votar`, a discussão é fechada e a fase de voto secreto é aberta. Cada jogador acusa alguém pelo comando `/voto [nome]`.
6.  **Veredito e Pontuação**: O servidor apura os votos e aplica as regras de negócio:
    *   **Caso 1 (Eliminação correta)**: Se a maioria votou no infiltrado, ele é eliminado e os inocentes ganham 1 ponto.
    *   **Caso 2 (Acusação errada)**: Se a maioria votou em um inocente, o infiltrado ganha 2 pontos.
    *   **Caso 3 (Empate)**: Empates favorecem o infiltrado pela ausência de consenso. O infiltrado ganha 2 pontos.
    *   Após a pontuação, o servidor notifica a tabela atualizada, reverte o estado para `LOBBY` e aguarda o próximo `/start`.

---

## 3. Estilo Arquitetural Híbrido
O sistema transita dinamicamente entre dois estilos arquiteturais para conciliar simplicidade de desenvolvimento e resiliência:

*   **Fase Descentralizada (Peer-to-Peer - P2P)**: Ocorre na inicialização ou após a falha do líder. Todos os nós operam com papéis simétricos, sem hierarquia, para realizar a coordenação da eleição. 
    *   *Justificativa*: A arquitetura P2P elimina o ponto único de falha (*Single Point of Failure*). Se o líder morre, a rede se auto-organiza de forma autônoma.
*   **Fase Centralizada (Cliente-Servidor com Estado - Stateful Server)**: Uma vez concluída a eleição e determinado o Host, o nó eleito passa a ser o servidor central e os demais operam como clientes.
    *   *Justificativa*: Manter a consistência de uma partida com estados mutáveis frequentes (votos, dicas, turnos) em uma rede P2P exigiria algoritmos de consenso complexos (ex: Raft) com alto tráfego de mensagens na rede. Centralizar o estado temporariamente no Cérebro simplifica a consistência e a validação de regras de negócios.

### 🙋 Perguntas Potenciais da Banca:
*   **Pergunta**: *"Por que não manter a arquitetura puramente P2P durante o jogo todo, usando consenso para cada ação?"*
    *   *Resposta*: *"Porque o custo de mensagens seria muito alto. Em uma rede P2P com $N$ nós, um algoritmo de consenso típico exige complexidade de mensagens de $O(N^2)$ para cada transição de estado. No modelo híbrido com servidor centralizado, as transições ocorrem com complexidade $O(N)$ (mensagens Unicast para o servidor e Multicast de retorno), o que otimiza significativamente o uso de banda da rede."*
*   **Pergunta**: *"A centralização no Cérebro não gera um Ponto Único de Falha (Single Point of Failure)?"*
    *   *Resposta*: *"Sim, gera durante a rodada de jogo. Mas a nossa fase P2P de eleição distribuída resolve exatamente essa fraqueza: se o ponto central falhar, a rede entra em modo P2P instantaneamente, elege um novo ponto central e recupera o estado em menos de 5 segundos. Isso torna o sistema altamente resiliente."*

---

## 4. Protocolos de Transporte e Modelos de Comunicação
O projeto adota decisões bem demarcadas nas camadas de transporte da pilha TCP/IP, utilizando sockets para finalidades distintas:

*   **TCP (`SOCK_STREAM`)**: Escolhido para o jogo por ser orientado a conexão e garantir a **entrega confiável e ordenada** de pacotes. Qualquer perda de dados acarretaria em inconsistência no estado do jogo.
*   **UDP (`SOCK_DGRAM`)**: Escolhido para o discovery LAN por ser leve e permitir **Broadcast**. O descarte de pacotes é tolerado devido à periodicidade dos pings de anúncio.
*   **Unicast**: Comunicação 1-para-1 direta do cliente ao Cérebro (ex: dicas e votos).
*   **Broadcast**: Comunicação 1-para-todos na rede local física (pings de descoberta UDP).
*   **Multicast Lógico**: O Cérebro simula o multicast de mensagens de chat e fases, iterando sobre o conjunto de conexões TCP ativas e disparando cópias individuais de pacotes Unicast na camada de aplicação. Não usamos multicast IP nativo, pois switches/roteadores de laboratórios acadêmicos costumam bloquear esse tráfego por segurança.

### 🙋 Perguntas Potenciais da Banca:
*   **Pergunta**: *"O uso de UDP na descoberta garante que todos os nós serão encontrados?"*
    *   *Resposta*: *"O UDP é não-confiável e pode perder pacotes. Porém, como a nossa thread de discovery LAN envia pings repetidamente a cada 0.5s, a perda de um pacote individual é inofensiva. A periodicidade compensa a não-confiabilidade do transporte."*
*   **Pergunta**: *"Por que vocês não usaram IP Multicast nativo com endereços da classe D (224.0.0.0/4)?"*
    *   *Resposta*: *"Porque o IP Multicast nativo depende do suporte de hardware e de protocolos como IGMP nos switches e roteadores da rede física. A maioria dos roteadores Wi-Fi domésticos e de laboratórios acadêmicos bloqueia o tráfego de multicast IP por questões de segurança. O multicast lógico na camada de aplicação garante portabilidade completa."*

---

## 5. Protocolo de Aplicação e Enquadramento (Framing)
O protocolo de aplicação opera em texto plano (UTF-8) com delimitadores lógicos no formato: `COMANDO|ATRIBUTO1:VALOR1|ATRIBUTO2:VALOR2`.

*   **O Problema do Byte-Stream**: O TCP entrega dados de forma contínua, sem delimitar o início e o fim de mensagens individuais. Se duas mensagens forem enviadas de forma rápida, elas podem se fundir no buffer do receptor.
*   **Nossa Solução (Framing por Delimitador)**: Usamos o caractere `\n` como delimitador de fim de pacote. A camada de recepção (`LeitorSocket`) retém os dados em memória e usa o caractere `\n` para quebrar as strings e extrair comandos inteiros e íntegros da rede.

### Tabela de Mensagens do Protocolo
Todas as mensagens utilizam codificação em texto plano UTF-8 estruturadas por pipes (`|`):

| Comando | Origem ➔ Destino | Formato do Pacote | Descrição e Ação |
| :--- | :--- | :--- | :--- |
| **`JOIN`** | Cliente ➔ Servidor | `JOIN\|NAME:<nome>\|CEREBRO:<bool>\|PTS:<pts>` | Registro inicial de apelido, flag de líder e recuperação de placar local. |
| **`REJECT`** | Servidor ➔ Cliente | `REJECT\|MSG:<texto>` | Recusa de entrada do cliente (nome duplicado ou jogo em andamento). |
| **`SYS`** | Servidor ➔ Cliente | `SYS\|MSG:<texto>` | Notificações informativas do sistema impressas no terminal. |
| **`ROLE`** | Servidor ➔ Cliente | `ROLE\|ROLE:<papel>\|WORD:<palavra>` | Envio confidencial do papel de jogo e da palavra secreta codificada. |
| **`TIP_REQ`** | Servidor ➔ Cliente | `TIP_REQ\|MSG:<texto>` | Solicitação multicast para que os clientes enviem suas dicas. |
| **`TIP`** | Cliente ➔ Servidor | `TIP\|WORD:<dica>` | Envio da dica secreta do jogador obtida via `/dica [palavra]`. |
| **`ALL_TIPS`** | Servidor ➔ Cliente | `ALL_TIPS\|LIST:<dicas>` | Multicast consolidado de todas as dicas dos jogadores (separadas por `&&`). |
| **`CHAT_START`** | Servidor ➔ Cliente | `CHAT_START\|MSG:<texto>` | Abertura do chat livre. Limpa e reinicia o vetor de timestamps local do cliente. |
| **`CHAT_MSG`** | Cliente ➔ Servidor | `CHAT_MSG\|VT:<vetor>\|MSG:<texto>` | Envio de mensagem de chat contendo o relógio lógico causal do nó. |
| **`CHAT_MSG` (/start)** | Cliente ➔ Servidor | `CHAT_MSG\|MSG:/start` | Comando do Host para iniciar a rodada (Lobby ➔ Dicas). |
| **`CHAT_MSG` (/votar)** | Cliente ➔ Servidor | `CHAT_MSG\|MSG:/votar` | Declaração de desejo do jogador de ir à votação (Chat ➔ Voto). |
| **`CHAT`** | Servidor ➔ Cliente | `CHAT\|FROM:<nome>\|VT:<vetor/NULL>\|MSG:<texto>` | Retransmissão multicast de chat. Se `VT` for `NULL`, exibe imediatamente. |
| **`CHAT_END`** | Servidor ➔ Cliente | `CHAT_END\|MSG:<texto>` | Notificação multicast que encerra a discussão do chat livre. |
| **`VOTE`** | Cliente ➔ Servidor | `VOTE\|TARGET:<nome>` | Voto secreto contra um jogador emitido via `/voto [nome]`. |
| **`SCORE_UPDATE`** | Servidor ➔ Cliente | `SCORE_UPDATE\|PTS:<pontos>` | Envio privado para persistência local de pontos no cliente. |
| **`ROUND_END`** | Servidor ➔ Cliente | `ROUND_END\|RESULT:<texto>` | Envio multicast do veredito e encerramento da rodada. |
| **`REQ_SCORE`** | Cliente ➔ Servidor | `REQ_SCORE\|MSG:null` | Solicitação multicast disparada pelo cliente ao digitar `/placar`. |

### 🙋 Perguntas Potenciais da Banca:
*   **Pergunta**: *"O que acontece se um jogador malicioso digitar o caractere de quebra de linha `\n` ou pipe `|` no meio de uma mensagem de chat?"*
    *   *Resposta*: *"O terminal sanitiza e limpa a string digitada pelo usuário antes de empacotar e enviar na rede, garantindo que caracteres reservados do protocolo não causem injeção de pacotes ou quebras no parse do interpretador."*

---

## 6. Concorrência e Multitarefa (Threads)
Como E/S de console e rede são operações bloqueantes, o paralelismo é alcançado por threads de SO:

*   **Threads Worker no Servidor**: O servidor usa uma thread principal (dispatcher) apenas para escutar novas conexões de rede e criar (despachar) threads filhas (workers) para cada cliente. Isso garante o isolamento: se a conexão de um cliente oscilar ou travar, apenas a thread dedicada a ele fica bloqueada, sem degradar a experiência dos outros jogadores.
*   **Multitarefa no Cliente**: O cliente opera com threads paralelas para processar o teclado (teclas digitadas), a escuta da rede (mensagens recebidas) e a descoberta de IPs (UDP). Isso permite o processamento assíncrono em tempo real.
*   **Thread do Respondedor Bully (`responder_pings_bully`)**: Thread à parte que mantém o socket bully ativo (porta `5556` na LAN ou `5001-5005` no Local) para responder pings de presença de outros nós rodando eleições.

### 🙋 Perguntas Potenciais da Banca:
*   **Pergunta**: *"Quais são as desvantagens do modelo de uma thread dedicada por cliente no servidor?"*
    *   *Resposta*: *"A desvantagem é o consumo de recursos do sistema operacional. Cada thread consome memória para sua pilha de execução e gera custo de processamento com troca de contexto. Para salas de jogo de tamanho pequeno (ex: até 10 jogadores), esse modelo é perfeitamente viável. Para milhares de conexões, o ideal seria usar multiplexação baseada em eventos (E/S Não-Bloqueante com laço de eventos)."*

---

## 7. Sincronização Lógica e Chat Causal (Locks e Relógios Vetoriais)

### A. Ordenação Causal e Relógios Vetoriais
Para garantir a relação de causa-efeito (ordenação causal), implementamos o **Algoritmo de Raynal**:
*   Cada processo mantém seu vetor lógico local $V$. Ao transmitir uma mensagem, o remetente $P_j$ incrementa seu relógio: $V[j] = V[j] + 1$ e anexa o vetor na mensagem.
*   Ao receber o vetor $V_{msg}$ de uma mensagem de $P_j$, o receptor $P_i$ a retém no buffer de retenção e só a imprime se:
    1.  $\text{VT}_{\text{msg}}[j] == \text{VT}_{\text{local}}[j] + 1$ (é a mensagem imediatamente seguinte de $P_j$).
    2.  $\forall k \neq j, \quad \text{VT}_{\text{msg}}[k] \le \text{VT}_{\text{local}}[k]$ (o receptor já viu todas as mensagens que o remetente conhecia antes de enviar).
*   **Propriedade de Auto-Envio**: O nó remetente de uma mensagem já possui toda a sua história causal satisfeita. As mensagens do próprio nó bypassam a verificação de Raynal no retorno do servidor e são exibidas imediatamente.

### B. Locks de Exclusão Mútua
O acesso concorrente a variáveis compartilhadas em memória por múltiplas threads exige a garantia de exclusão mútua:
*   **Servidor (`self.estado_lock = threading.RLock()`)**: Lock reentrante que protege o dicionário `self.jogadores` contra condições de corrida entre as diferentes worker threads de clientes.
*   **Cliente (`self.vt_lock = threading.Lock()`)**: Protege o vetor de relógio lógico local e o buffer de mensagens, pois a thread de input do teclado e a thread de rede que recebe dados paralelos no socket atualizam esses dados concorrentemente.
*   **Console (`BUFFER_LOCK = threading.Lock()`)** *(Apenas Windows)*: Garante acesso exclusivo e atômico ao buffer de digitação da tela para evitar colisões entre a thread de rede que redesenha a tela e a thread de leitura de teclado caractere por caractere.

### 🙋 Perguntas Potenciais da Banca:
*   **Pergunta**: *"Por que a sua própria mensagem não passa pela verificação do algoritmo de Raynal ao voltar do servidor?"*
    *   *Resposta*: *"Porque o remetente incrementa seu relógio lógico no momento do envio. Ao retornar, o relógio local já está igualado ao vetor da mensagem. Se passasse por Raynal, a condição 1 falharia (pois ela espera encontrar um vetor local menor). Como a causalidade de uma mensagem em relação ao próprio emissor é intrínseca, ela é impressa imediatamente."*
*   **Pergunta**: *"O que acontece se uma mensagem enviada por Alice ficar retida no buffer de Bob para sempre por causa de uma mensagem de Carlos que se perdeu na rede?"*
    *   *Resposta*: *"Como usamos sockets TCP confiáveis para o chat, mensagens físicas não são perdidas no nível de transporte. O buffer de retenção causal só atua para ordenar mensagens que chegam fora de ordem devido à latência ou caminhos diferentes de roteamento, mas o TCP garante que a mensagem pendente acabará chegando, liberando o buffer."*

---

## 8. Coordenação e Algoritmo de Eleição Bully
A coordenação de consenso para a eleição do coordenador utiliza uma adaptação do **Algoritmo Bully (Garcia-Molina)**:
*   **Espaço de Endereçamento de IDs**: Usamos portas TCP exclusivas no modo local e endereços IPv4 físicos no modo LAN.
*   **Prevenção de Split-Brain (Varredura Preventiva)**: Antes de iniciar o Bully, o nó tenta se conectar na porta de jogo `5555` de todos os IPs conhecidos. Se um servidor já estiver rodando, ele descarta a eleição e conecta-se como cliente. Isso impede o "efeito valentão" original do Bully.
*   **Jitter (Sincronização por Atraso)**: A introdução de um atraso aleatório (`3.0 + random(0.1, 1.0)`) faz com que o nó sobrevivente de maior ID tenda a acordar primeiro da falha, concluir sua varredura e iniciar o servidor na porta `5555`. Quando os nós menores acordarem do seu jitter, eles apenas detectam o novo servidor ativo e se conectam.

### 🙋 Perguntas Potenciais da Banca:
*   **Pergunta**: *"O algoritmo Bully original exige que o nó de maior ID assuma a liderança. Por que vocês usam a varredura preventiva na porta 5555 que impede isso caso o jogo já tenha começado?"*
    *   *Resposta*: *"Em um jogo com estado ativo, a mudança de liderança no meio de uma rodada apenas porque um nó de maior IP entrou destruiria o progresso da partida. Por isso, implementamos uma varredura preventiva de jogo ativo: a prioridade do sistema é manter a consistência da partida em andamento."*
*   **Pergunta**: *"Como o Bully resolve empates se dois nós tiverem IDs iguais?"*
    *   *Resposta*: *"Não há empates. No modo local, o bind do socket impede que duas instâncias usem a mesma porta física. Na LAN, cada computador possui um endereço IP exclusivo na sub-rede. Como os IDs são estritamente exclusivos, a eleição sempre converge."*

---

## 9. Tolerância a Falhas e Recuperação de Estado
O sistema foi construído sob o modelo de **Tolerância a Falhas Parciais**, distinguindo entre a falha de um nó comum e a falha do líder:

*   **Queda de um Jogador Inocente (Normal)**: O sumiço de um inocente altera o quórum de votação e deixa dicas órfãs na rodada. O Cérebro detecta a queda do socket TCP e, se a partida estiver em andamento, aborta a rodada atual imediatamente, remove o nó da lista de ativos, zera o progresso e retorna todos os sobreviventes ao Lobby para garantir a **consistência lógica**.
*   **Queda do Jogador Infiltrado**: O Infiltrado é o alvo central do jogo. Se ele cair, os inocentes não têm mais quem caçar. O Cérebro detecta a queda do socket do infiltrado, aborta a rodada e redireciona todos os jogadores sobreviventes de volta ao Lobby, garantindo a propriedade de **liveness** (vivacidade) da partida.
*   **Queda do Cérebro (Líder / Servidor)**: O servidor inteiro sai do ar. Os clientes detectam o silêncio do servidor por meio de um timeout de `2.0` segundos no socket. Ao estourar, as conexões são encerradas e todos os clientes entram em **Jitter** e disparam a reeleição Bully.
*   **Recuperação de Estado Cooperativa**: O novo líder abre o `ServidorCerebro`. Os clientes sobreviventes se conectam a ele e enviam o valor persistido na variável `MEUS_PONTOS_GLOBAIS` no pacote `JOIN`, permitindo a reconstrução cooperativa do placar acumulado sem perdas.

### 🙋 Perguntas Potenciais da Banca:
*   **Pergunta**: *"Se as pontuações são guardadas nos clientes e reenviadas, um cliente malicioso não poderia forjar sua própria pontuação ao se reconectar?"*
    *   *Resposta*: *"Sim, em um ambiente de produção real isso seria uma vulnerabilidade de segurança. Para o escopo acadêmico do projeto, priorizamos a resiliência a falhas físicas com baixo overhead de rede. Em um cenário real, a integridade do dado seria mantida usando assinaturas criptográficas nos pacotes de pontuação gerados pelo antigo servidor, ou mantendo replicação de estado ativa via Paxos/Raft."*
*   **Pergunta**: *"Por que o timeout de falha do servidor foi definido em 2.0 segundos? Esse valor não é muito baixo?"*
    *   *Resposta*: *"Sim, 2.0 segundos é um valor agressivo escolhido especificamente para tornar a demonstração prática do failover rápida durante a apresentação. Em uma implantação real, esse timeout seria configurado com uma margem maior (ex: 5.0 a 10.0 segundos) para tolerar picos normais de latência sem disparar eleições redundantes."*

---

## 10. Roteiro para Demonstração Prática

### A. Preparação no Windows / Linux
1.  **Rede Local**: Certifique-se de que os computadores conseguem se comunicar (via `ping`). Se a rede Wi-Fi local bloquear broadcast (isolamento de AP), use a função de **Fallback Manual** digitando os IPs de destino no menu inicial.
2.  **Firewall**: Garanta que as portas `5555`, `5556` e `5557` (TCP e UDP) estão liberadas.

### B. Roteiro de Demonstração
1.  **Descoberta**: Abrir o jogo em 3 terminais e apontar a descoberta automática.
2.  **Bully Inicial**: Mostrar que o nó de maior ID virou o Cérebro e as conexões TCP foram abertas.
3.  **Partida**: Digitar dicas, enviar mensagens no chat e votar para exibir a apuração de pontuação.
4.  **Falha de Cérebro**: Derrubar o Cérebro com `Ctrl+C`. Mostrar os nós sobreviventes detectando a falha, rodando a eleição Bully, definindo o novo Cérebro e reatando o placar acumulado automaticamente.
5.  **Falha de Cliente**: Fechar um dos clientes e mostrar o Cérebro derrubando a rodada de forma limpa para retornar todos ao Lobby com segurança.

### 🙋 Perguntas Potenciais da Banca:
*   **Pergunta**: *"Como vocês demonstram que os relógios vetoriais estão realmente ordenando as mensagens causais?"*
    *   *Resposta*: *"Para fins de demonstração, podemos injetar um pequeno atraso artificial em um dos nós clientes antes de imprimir. Isso simula uma latência de rede extrema. Mostraremos que mesmo que a resposta de Bob chegue fisicamente antes da pergunta de Alice em Carlos, o terminal de Carlos segura a resposta e só a exibe após a pergunta ser processada, provando a consistência lógica do algoritmo."*
