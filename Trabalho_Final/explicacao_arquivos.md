# Documentação Técnica dos Arquivos do Jogo: "A Palavra Infiltrada"

Este documento descreve detalhadamente a estrutura, variáveis, métodos, fluxos lógicos e interações de rede presentes em cada arquivo do projeto: **rede.py**, **game_core.py** e **jogo.py**.

---

## 1. [rede.py]

O arquivo `rede.py` atua como a camada de transporte e infraestrutura de baixo nível. Ele define os parâmetros de conexão, o protocolo de enquadramento de mensagens (*message framing*) e os algoritmos distribuídos de eleição e auto-descoberta.

### Parâmetros de Configuração
*   `HOST_LOCAL = '127.0.0.1'`: Endereço para simulações na mesma máquina.
*   `HOST_LAN = '0.0.0.0'`: Vincula sockets para escutar em todas as placas de rede do sistema.
*   `PORTA_JOGO = 5555`: Porta TCP onde roda o servidor da partida.
*   `PORTA_BULLY_LAN = 5556`: Porta TCP de presença/liveness usada no algoritmo Bully em LAN.
*   `PORTA_DISCOVERY = 5557`: Porta UDP usada para a auto-descoberta por broadcast.
*   `PORTAS_BULLY = [5001, 5002, 5003, 5004, 5005]`: IDs lógicos (portas) para a eleição Bully local.
*   `BUFFER = 1024`: Tamanho máximo de leitura de dados de rede por bloco.
*   `PARES_DE_PALAVRAS`: Lista contendo pares de palavras secretas sorteáveis.

### Enquadramento de Sockets (Framing)
*   `enviar_msg(sock, texto)`: Função utilitária que adiciona `\n` ao final do texto e o transmite via `sendall()`, evitando a fusão de mensagens consecutivas no TCP.
*   `LeitorSocket`: Classe que encapsula o socket e mantém um buffer de strings (`self.buffer`).
    *   `ler_mensagem()`: Executa leituras constantes de 1024 bytes. Se a conexão cair, retorna `None`. Se estourar o timeout, retorna `""` (mantendo a thread ativa). Se achar `\n`, recorta e retorna a mensagem limpa, retendo o restante no buffer.
    *   `ler_mensagens_iter()`: Gerador (`yield`) que permite iterar sobre novas mensagens recebidas de forma transparente no loop de eventos.

### Lógica de Eleição e Presença
*   `responder_pings_bully(meu_socket)`: Thread que fica executando `accept()` na porta bully e fechando a conexão na sequência. Funciona como um sinalizador de que o nó está online.
*   `executar_eleicao_bully(meu_id, host_jogo)` (Local):
    *   Tenta conectar na porta `5555`. Se o jogo já estiver rodando, retorna `False`.
    *   Varre portas maiores que a dele. Se conectar a alguma, abre mão da eleição (`alguem_maior_vivo = True`), aguarda 2 segundos e retorna `False`. Se nenhuma porta maior responder, retorna `True`.
*   `iniciar_discovery_lan(meu_ip)` (LAN):
    *   **Auto-Descoberta Contínua**: Inicia uma thread de background que envia em loop pacotes UDP Broadcast contendo o próprio IP para `255.255.255.255:5557` a cada 0.5s, e escuta respostas.
    *   **Set Compartilhado**: Adiciona novos IPs descobertos em um set compartilhado com controle de concorrência (`ips_lock`), eliminando a necessidade de digitar os IPs dos computadores manualmente.
*   `executar_eleicao_bully_lan(meu_ip, ips_participantes)` (LAN):
    *   **Etapa 1**: Escaneia a porta de jogo `5555` em todos os IPs descobertos. Se um jogo já estiver rodando, retorna esse IP de imediato como líder para prevenir split-brain.
    *   **Etapa 2**: Se não houver jogo ativo, ordena os IPs decrescentemente e conecta na porta bully `5556`. O maior IP vivo a responder vira o líder.

---

## 2. [game_core.py]

O arquivo `game_core.py` contém as regras lógicas da partida, a máquina de estados do servidor e a interface de manipulação de relógios lógicos causais do cliente.

### Classe `ServidorCerebro` (O Servidor)
Gerencia o estado e coordena o envio de mensagens para os clientes.
*   `self.estado_lock`: Lock reentrante (`threading.RLock`) que garante a consistência das operações concorrentes efetuadas pelas worker threads no estado do jogo.
*   `tratar_cliente(conn, addr)`:
    *   Recebe o pacote `JOIN` com o nome e placar acumulado.
    *   **Bloqueio de Nomes Duplicados**: Varre `self.jogadores` e verifica se o apelido já está em uso (case-insensitive). Se sim, envia `REJECT` e encerra a conexão.
    *   Loop de mensagens do cliente: processa `/start`, `/dica [palavra]`, `/voto [nome]` e `/votar` (skip) conforme a fase atual do jogo (`LOBBY`, `DICAS`, `CHAT`, `VOTACAO`).
    *   `finally`: Garante a remoção limpa do jogador que desconectar (por comando ou queda), reduz a contagem sob lock e anula a rodada retornando todos ao lobby.
*   `enviar_multicast(mensagem)`: Envia mensagens para todos os jogadores ativos copiando a lista de clientes de forma segura sob lock rápido.
*   `iniciar_partida()`: Sorteia as palavras da rodada e despacha-as privadamente aos clientes.
*   `checar_todas_as_dicas()`: Valida se todos enviaram dicas e libera a discussão.
*   `iniciar_votacao()`: Transiciona para a fase de voto secreto, travando o chat de texto.
*   `checar_todos_votos()`: Computa a contagem de votos. Empates ou erros de eliminação pontuam o infiltrado (2 pts); eliminação bem-sucedida pontua os inocentes (1 pt cada). Reseta o estado para `LOBBY` e envia o placar atualizado.

### Classe `ClienteJogador` (O Cliente)
Representa a lógica local e a ordenação de dados do terminal do jogador.
*   `self.vt_lock`: Lock local para proteger acessos ao vetor lógico `self.vt` e buffer causal.
*   `conectar(nome, is_cerebro, host_jogo)`: Conecta o socket ao servidor e inicia as threads.
*   `ouvir_servidor()`:
    *   Thread que recebe mensagens e comandos do servidor.
    *   **Jitter no Failover**: Em caso de queda do socket, aguarda um tempo aleatório (`3.0 + random.uniform(0.1, 1.0)`) antes de disparar a eleição, mitigando o risco de colisões e split-brain na eleição simultânea de nós sobreviventes.
*   `processar_entrega_causal(remetente, vt_str, texto)`: Compara o vetor lógico recebido ($\text{VT}_{\text{msg}}$) com o relógio local do cliente ($\text{VT}_{\text{local}}$) usando o algoritmo de Raynal. Retém no buffer até que as dependências sejam entregues e exibe as mensagens ordenadamente.
*   `processar_inputs()`: Captura inputs da fila. Remove silenciosamente qualquer caractere `|` para evitar corrupções no parser de comandos do protocolo. Se for chat comum, incrementa o relógio de timestamp local, serializa o vetor e envia o pacote.

---

## 3. [jogo.py]

O arquivo `jogo.py` orquestra a inicialização e controla a tolerância a falhas através do loop de failover.

### Inicialização e Cadastro de IDs
*   Cadastra o apelido do jogador e realiza a sanitização do caractere `|`.
*   **Configuração de Redes**:
    *   **Modo Local**: Varre sequencialmente as portas `5001` a `5005` e tenta fazer o `bind`. A primeira porta livre vira o ID exclusivo do processo local. **Não usa `SO_REUSEADDR`**, o que impede que múltiplos processos locais compartilhem a mesma porta no Windows, garantindo IDs de eleição únicos.
    *   **Modo LAN**: Inicia a thread contínua de descoberta UDP em segundo plano (`iniciar_discovery_lan`) que atualiza dinamicamente a lista de participantes.

### Loop de Execução e Failover (`while True:`)
1.  **Chama a Eleição**: Executa a rotina Bully local ou LAN para encontrar o `host_jogo`. No modo LAN, passa a lista de IPs de participantes coletados dinamicamente no snapshot de discovery.
2.  **Sobe o Cérebro**: Se for o líder da eleição e o servidor ainda estiver inativo, inicia o `ServidorCerebro` em uma nova thread.
3.  **Bloqueio de Jogo**: Instancia o `ClienteJogador` e entra na chamada bloqueante `.conectar()`. O processo fica represado ali capturando inputs e aguardando eventos do jogo.
4.  **Recuperação**: Se o servidor cair, o controle retorna ao `jogo.py`, desliga a flag do servidor, aguarda 1 segundo e executa o `continue` para voltar ao topo do laço, elegendo um novo líder de forma transparente.
