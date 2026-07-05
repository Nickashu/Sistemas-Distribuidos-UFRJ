# Documentação Detalhada dos Arquivos do Projeto: "A Palavra Infiltrada"

Este documento apresenta uma análise técnica minuciosa de cada um dos três arquivos Python que compõem o sistema distribuído do jogo: **rede.py**, **game_core.py** e **jogo.py**.

---

## 1. [rede.py](file:///c:/Users/Usu%C3%A1rio/Desktop/sistemas_distribuidos/Trabalho_Final/rede.py)

O arquivo `rede.py` define a infraestrutura de baixo nível da comunicação por rede, constantes de portas/endereços, enquadramento de mensagens e os algoritmos distribuídos para eleição de líder.

### Constantes e Parâmetros de Rede
*   `HOST_LOCAL = '127.0.0.1'`: IP de loopback local.
*   `HOST_LAN = '0.0.0.0'`: Endereço curinga para escutar em todas as placas de rede do computador.
*   `PORTA_JOGO = 5555`: Porta TCP onde roda o servidor do jogo (`ServidorCerebro`).
*   `PORTA_BULLY_LAN = 5556`: Porta TCP de presença em rede local para a eleição distribuída.
*   `PORTAS_BULLY = [5001, 5002, 5003, 5004, 5005]`: IDs lógicos representados por portas TCP locais.
*   `BUFFER = 1024`: Tamanho máximo de leitura de bytes no socket.
*   `PARES_DE_PALAVRAS`: Lista de tuplas contendo pares de palavras para inocentes e infiltrados.

### Enquadramento de Mensagens (Framing TCP)
*   `enviar_msg(sock, texto)`: Garante o envio completo do pacote (`sendall`) com o sufixo `\n`. Isso previne a coalescência de pacotes (mensagens consecutivas agrupando-se em uma única string).
*   `LeitorSocket(sock)`:
    *   Mantém um buffer local de strings.
    *   `ler_mensagem()`: Lê bytes do socket até encontrar um `\n`. Em caso de estouro de timeout de socket (2.0s), retorna `""` para manter a thread ativa. Se a conexão cair, retorna `None`. Ao encontrar `\n`, divide o buffer, retorna a mensagem limpa e armazena os caracteres restantes.

### Algoritmos e Funções
*   `responder_pings_bully(meu_socket)`: Loop executado em thread separada que aceita conexões rápidas e as fecha imediatamente, servindo como ping de presença do nó.
*   `executar_eleicao_bully(meu_id, host_jogo)` (Local):
    *   Tenta conectar na porta do jogo (`5555`). Se o jogo já estiver rodando, aborta retornando `False`.
    *   Varre portas de ID maior (`meu_id + 1` até `5005`). Se conseguir abrir conexão TCP em alguma, aborta retornando `False`.
    *   Se nenhuma porta maior responder, retorna `True` (e o nó vira o líder).
*   `normalizar_lista_ips(texto_ips)`: Trata a entrada de texto de IPs, valida-os, remove duplicatas e os ordena numericamente.
*   `executar_eleicao_bully_lan(meu_ip, ips_participantes)` (LAN):
    *   **Passo 1**: Verifica ativamente se já há algum servidor de jogo rodando na porta `5555` em algum IP da lista. Se sim, retorna esse IP de imediato para evitar Split-Brain.
    *   **Passo 2**: Ordena os IPs de forma decrescente. Varre a lista tentando conexões na porta de presença (`5556`). O primeiro IP a responder é eleito líder (por ser o maior IP vivo).

---

## 2. [game_core.py](file:///c:/Users/Usu%C3%A1rio/Desktop/sistemas_distribuidos/Trabalho_Final/game_core.py)

O arquivo `game_core.py` implementa a máquina de estados do servidor e a interface de lógica de rede do cliente, além do controle causal do chat.

### Variável Global de Persistência
*   `MEUS_PONTOS_GLOBAIS = 0`: Armazena a pontuação acumulada do jogador local. Permite a restauração do placar quando o cliente reconectar a um novo líder após uma falha.

### Classe `ServidorCerebro` (O Servidor)
Gerencia o estado e as regras da rodada da partida.
*   `self.jogadores = {}`: Dicionário que mapeia conexões TCP aos dados de jogo de cada um.
*   `self.estado_jogo`: String que armazena a fase da partida (`'LOBBY'`, `'DICAS'`, `'CHAT'`, `'VOTACAO'`).
*   `self.estado_lock = threading.RLock()`: Lock que garante exclusão mútua sobre as variáveis compartilhadas do servidor (acessadas por múltiplas worker threads).
*   `tratar_cliente(conn, addr)`:
    *   Lê o primeiro pacote `JOIN`. Registra o jogador sob lock e inicia a escuta.
    *   Itera nas mensagens recebidas. Dependendo da fase do jogo, valida dicas (`TIP`), skips de chat (`CHAT_MSG|MSG:/votar`) e votos (`VOTE`).
    *   Em caso de desconexão (bloco `finally`), remove o jogador de forma segura, reduz a barreira e volta a partida para o Lobby.
*   `enviar_multicast(mensagem)`: Transmite mensagens simultaneamente a todos os jogadores conectados.
*   `iniciar_partida()`: Sorteia as palavras, define o infiltrado e dispara as regras.
*   `checar_todas_as_dicas()`: Se todas as dicas foram recebidas, envia o agrupamento a todos e libera o chat causal.
*   `iniciar_votacao()`: Trava o chat e abre o canal de votos secretos.
*   `checar_todos_votos()`: Avalia empates e eliminações, atribui os pontos e atualiza o placar.

### Classe `ClienteJogador` (O Cliente)
*   `self.vt = {}`: Vetor de timestamps lógicos do nó.
*   `self.buffer_msgs = []`: Mensagens represadas que aguardam resolução causal.
*   `self.vt_lock = threading.Lock()`: Lock para sincronizar a thread de input e a de recepção no acesso ao vetor de timestamps.
*   `conectar(nome, is_cerebro, host_jogo)`: Conecta o socket ao servidor, inicia a thread de recepção e inicia a leitura de teclado.
*   `ouvir_servidor()`: Loop de leitura de pacotes recebidos do cérebro. Se o socket fechar, adiciona um **atraso com jitter aleatório** (3 a 4 segundos) antes de disparar a flag `queda_silenciosa`, evitando que todos iniciem a eleição distribuída no exato mesmo instante.
*   `processar_entrega_causal(remetente, vt_str, texto)`: Implementa o algoritmo de Raynal. Uma mensagem só sai do buffer local para a tela se o receptor já tiver entregue todas as dependências dela.
*   `processar_inputs()`: Lê inputs da fila de teclado. Se for mensagem de chat comum, incrementa o relógio lógico local, anexa o vetor formatado à string e a envia.

---

## 3. [jogo.py](file:///c:/Users/Usu%C3%A1rio/Desktop/sistemas_distribuidos/Trabalho_Final/jogo.py)

O arquivo `jogo.py` serve de ponto de entrada. Ele orquestra os modos de inicialização do programa e o loop de tolerância a falhas.

### Inicialização e Escolha de Rede
*   Configura o codinome do jogador e escolhe se roda em modo LAN ou modo local.
*   **Ligação de Sockets de Presença**:
    *   No modo local, varre e tenta fazer `bind` nas portas `5001` a `5005` (removido o `SO_REUSEADDR` para garantir exclusividade de ID no Windows). Inicia a thread de liveness.
    *   No modo LAN, faz bind na porta padrão `5556` de presença local e inicia a thread de liveness.

### Loop de Reconfiguração e Tolerância a Falhas (`while True:`)
O loop principal que permite ao jogo sobreviver à queda do líder:
1.  **Chama a Eleição**: Executa a rotina Bully local ou LAN para descobrir quem é o atual `host_jogo`.
2.  **Inicia Servidor**: Se o nó descobriu ser o líder da eleição e seu servidor ainda não está rodando localmente, inicia a thread do `ServidorCerebro`.
3.  **Estabelece Conexão**: Instancia o `ClienteJogador` e chama o laço bloqueante `.conectar()`.
4.  **Recuperação**: Se o cliente desconectar (servidor caiu), o fluxo avança para `jogador.queda_silenciosa`, define `servidor_ativo = False`, dorme 1 segundo e volta ao início do laço (Passo 1), executando um novo Bully e reconectando as pontuações no servidor novo.
