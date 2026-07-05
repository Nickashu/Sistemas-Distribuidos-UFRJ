import queue
import random
import socket
import sys
import threading
import time

from rede import BUFFER, HOST_LAN, HOST_LOCAL, PARES_DE_PALAVRAS, PORTA_JOGO, enviar_msg, LeitorSocket

# Guarda o placar entre reinícios do cliente na mesma máquina.
MEUS_PONTOS_GLOBAIS = 0


class ServidorCerebro:
    def __init__(self, host_bind=HOST_LOCAL):
        # O servidor central mantém toda a evolução da partida em memória.
        self.jogadores = {}
        self.estado_jogo = 'LOBBY'
        self.rodada_encerrada = False
        self.estado_lock = threading.RLock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((host_bind, PORTA_JOGO))

    def iniciar(self):
        self.server_socket.listen()
        print(f"👑 [SISTEMA] Eleição concluída! Cérebro ativo na porta {PORTA_JOGO}.")

        while True:
            try:
                conn, addr = self.server_socket.accept()
                threading.Thread(target=self.tratar_cliente, args=(conn, addr)).start()
            except:
                break

    def tratar_cliente(self, conn, addr):
        leitor = LeitorSocket(conn)
        try:
            # Primeiro pacote do cliente: nome, se é host e pontos anteriores.
            msg_inicial = leitor.ler_mensagem()
            if not msg_inicial:
                conn.close()
                return

            if msg_inicial.startswith("JOIN"):
                partes = msg_inicial.split("|")
                nome = partes[1].split(":", 1)[1]
                is_host = (partes[2].split(":", 1)[1] == "True")
                pontos_recuperados = int(partes[3].split(":", 1)[1])

                with self.estado_lock:
                    if self.estado_jogo != 'LOBBY':
                        enviar_msg(conn, "REJECT|MSG:Partida em andamento! Acesso negado.")
                        conn.close()
                        return

                    # Cada jogador é guardado com o estado mínimo necessário da rodada.
                    self.jogadores[conn] = {
                        'nome': nome,
                        'papel': '',
                        'palavra': '',
                        'dica': '',
                        'quer_votar': False,
                        'voto': '',
                        'pontos': pontos_recuperados,
                        'is_host': is_host,
                    }
                    total_jogadores = len(self.jogadores)

                self.enviar_multicast(f"SYS|MSG:{nome} entrou! (Total: {total_jogadores})")

                if is_host:
                    enviar_msg(conn, "SYS|MSG:Você é o HOST! Digite /start para iniciar a rodada.")

            for msg in leitor.ler_mensagens_iter():
                with self.estado_lock:
                    if conn not in self.jogadores:
                        break
                    nome_remetente = self.jogadores[conn]['nome']
                    is_host_remetente = self.jogadores[conn]['is_host']
                    dica_remetente = self.jogadores[conn]['dica']
                    quer_votar_remetente = self.jogadores[conn]['quer_votar']
                    voto_remetente = self.jogadores[conn]['voto']
                    estado_atual = self.estado_jogo

                if estado_atual == 'LOBBY':
                    # No lobby só aceitamos iniciar partida, pedir placar ou chat livre.
                    if msg == "CHAT_MSG|MSG:/start":
                        if is_host_remetente:
                            self.iniciar_partida()
                        else:
                            enviar_msg(conn, "SYS|MSG:Acesso negado. Somente o Host pode dar /start.")
                    elif msg == "REQ_SCORE|MSG:null":
                        with self.estado_lock:
                            jogadores_snapshot = list(self.jogadores.values())
                        placar_msg = "\\n📊 --- PLACAR ATUAL ---"
                        for j in jogadores_snapshot:
                            placar_msg += f"\\n   🔹 {j['nome']}: {j['pontos']} pts"
                        placar_msg += "\\n-----------------------"
                        enviar_msg(conn, f"SYS|MSG:{placar_msg}")
                    elif msg.startswith("CHAT_MSG"):
                        partes = msg.split("|")
                        if len(partes) >= 3:
                            texto = partes[2].split(":", 1)[1]
                        else:
                            texto = partes[1].split(":", 1)[1]

                        if texto == "/votar":
                            enviar_msg(conn, "SYS|MSG:O comando /votar só tem efeito durante a fase de chat.")
                        else:
                            self.enviar_multicast(f"CHAT|FROM:{nome_remetente}|VT:NULL|MSG:{texto}")

                elif estado_atual == 'DICAS':
                    # Nesta fase cada jogador envia exatamente uma dica.
                    if msg.startswith("TIP"):
                        pode_enviar = False
                        with self.estado_lock:
                            if conn in self.jogadores and self.jogadores[conn]['dica'] == '':
                                dica = msg.split("|")[1].split(":", 1)[1]
                                self.jogadores[conn]['dica'] = dica
                                pode_enviar = True

                        if pode_enviar:
                            self.enviar_multicast(f"SYS|MSG:{nome_remetente} enviou sua dica!")
                            self.checar_todas_as_dicas()
                        else:
                            enviar_msg(conn, "SYS|MSG:Você já enviou sua dica!")
                    else:
                        enviar_msg(conn, "SYS|MSG:Digite /dica [palavra] para prosseguir.")

                elif estado_atual == 'CHAT':
                    # O chat usa o comando /votar para avançar para a votação.
                    if quer_votar_remetente:
                        enviar_msg(conn, "SYS|MSG:Aguarde os outros terminarem.")
                        continue

                    if msg == "CHAT_MSG|MSG:/votar":
                        with self.estado_lock:
                            if conn in self.jogadores:
                                self.jogadores[conn]['quer_votar'] = True
                                votos_skip = sum(1 for j in self.jogadores.values() if j['quer_votar'])
                                total = len(self.jogadores)
                        self.enviar_multicast(f"SYS|MSG:{nome_remetente} quer ir para a votação ({votos_skip}/{total})")
                        if votos_skip == total:
                            self.iniciar_votacao()
                    elif msg.startswith("CHAT_MSG"):
                        partes = msg.split("|", 2)
                        if len(partes) >= 3:
                            bloco_vt = partes[1]
                            bloco_texto = partes[2]
                            self.enviar_multicast(f"CHAT|FROM:{nome_remetente}|{bloco_vt}|{bloco_texto}")

                elif estado_atual == 'VOTACAO':
                    # Na votação, cada jogador pode enviar apenas um voto.
                    if msg.startswith("VOTE"):
                        if voto_remetente == '':
                            voto_alvo = msg.split("|")[1].split(":", 1)[1].strip()
                            with self.estado_lock:
                                lista_nomes = [j['nome'].lower() for j in self.jogadores.values()]
                                e_valido = voto_alvo.lower() in lista_nomes
                                if e_valido:
                                    self.jogadores[conn]['voto'] = voto_alvo
                            
                            if e_valido:
                                self.enviar_multicast(f"SYS|MSG:{nome_remetente} votou!")
                                self.checar_todos_votos()
                            else:
                                enviar_msg(conn, "SYS|MSG:Voto inválido! Nome não encontrado.")
                        else:
                            enviar_msg(conn, "SYS|MSG:Você já votou!")
                    else:
                        enviar_msg(conn, "SYS|MSG:Discussão fechada! Digite /voto [nome].")

        except Exception:
            pass
        finally:
            nome_caiu = None
            ja_era_lobby = True
            total_ativo = 0
            with self.estado_lock:
                if conn in self.jogadores:
                    nome_caiu = self.jogadores[conn]['nome']
                    del self.jogadores[conn]
                    total_ativo = len(self.jogadores)
                    ja_era_lobby = (self.estado_jogo == 'LOBBY')
                    if not ja_era_lobby:
                        self.estado_jogo = 'LOBBY'

            if nome_caiu:
                self.enviar_multicast(f"SYS|MSG:{nome_caiu} caiu. Total ativo: {total_ativo}")
                if not ja_era_lobby:
                    self.enviar_multicast("SYS|MSG:Partida interrompida por queda. Retornando ao Lobby!")
            try:
                conn.close()
            except:
                pass

    def enviar_multicast(self, mensagem):
        with self.estado_lock:
            clientes = list(self.jogadores.keys())
        for cliente in clientes:
            try:
                enviar_msg(cliente, mensagem)
            except:
                pass

    def iniciar_partida(self):
        with self.estado_lock:
            # O jogo só começa com pelo menos três jogadores conectados.
            if len(self.jogadores) < 3:
                self.enviar_multicast("SYS|MSG:Mínimo de 3 jogadores necessários para iniciar!")
                return

            self.estado_jogo = 'DICAS'
            self.rodada_encerrada = False
            # Um jogador recebe a palavra diferente e vira o infiltrado.
            p_inoc, p_inf = random.choice(PARES_DE_PALAVRAS)
            conexoes = list(self.jogadores.keys())
            inf_conn = random.choice(conexoes)

            for conn in conexoes:
                self.jogadores[conn]['dica'] = ''
                self.jogadores[conn]['quer_votar'] = False
                self.jogadores[conn]['voto'] = ''

                if conn == inf_conn:
                    self.jogadores[conn]['papel'] = 'INFILTRADO'
                    self.jogadores[conn]['palavra'] = p_inf
                else:
                    self.jogadores[conn]['papel'] = 'INOCENTE'
                    self.jogadores[conn]['palavra'] = p_inoc

                msg = f"ROLE|ROLE:{self.jogadores[conn]['papel']}|WORD:{self.jogadores[conn]['palavra']}"
                try:
                    enviar_msg(conn, msg)
                except:
                    pass

        self.enviar_multicast("TIP_REQ|MSG:Rodada começou! Digite /dica [palavra]")

    def checar_todas_as_dicas(self):
        with self.estado_lock:
            # Só troca de fase quando todos já enviaram sua dica.
            if self.estado_jogo != 'DICAS' or self.rodada_encerrada:
                return
            if not all(j['dica'] != '' for j in self.jogadores.values()):
                return
            lista_dicas = "&&".join([f"{j['nome']} disse: '{j['dica']}'" for j in self.jogadores.values()])
            self.estado_jogo = 'CHAT'

        self.enviar_multicast(f"ALL_TIPS|LIST:{lista_dicas}")
        self.enviar_multicast("CHAT_START|MSG:[CHAT ABERTO] Quem é o Infiltrado? Digite /votar para pular o chat.")

    def iniciar_votacao(self):
        with self.estado_lock:
            # A votação só abre depois do chat coletivo.
            if self.estado_jogo != 'CHAT' or self.rodada_encerrada:
                return
            self.estado_jogo = 'VOTACAO'
        self.enviar_multicast("CHAT_END|MSG:[VOTAÇÃO] Chat bloqueado! Digite /voto [nome].")

    def __get_infiltrador_name(self):
        for j in self.jogadores.values():
            if j['papel'] == 'INFILTRADO':
                return j['nome']
        return "Desconhecido"

    def checar_todos_votos(self):
        with self.estado_lock:
            # Fecha a rodada uma única vez, mesmo com threads chegando juntas.
            if self.estado_jogo != 'VOTACAO' or self.rodada_encerrada:
                return
            if not all(j['voto'] != '' for j in self.jogadores.values()):
                return

            self.rodada_encerrada = True
            contagem = {}
            for j in self.jogadores.values():
                voto = j['voto'].lower()
                contagem[voto] = contagem.get(voto, 0) + 1

            max_votos = max(contagem.values())
            mais_votados = [nome for nome, qtd in contagem.items() if qtd == max_votos]
            nome_infiltrado = self.__get_infiltrador_name()

            if len(mais_votados) > 1:
                # Empate favorece o infiltrado.
                resultado = f"Deu EMPATE! Sem consenso, o INFILTRADO ({nome_infiltrado}) escapou e ganhou 2 pontos!"
                for conn in self.jogadores:
                    if self.jogadores[conn]['papel'] == 'INFILTRADO':
                        self.jogadores[conn]['pontos'] += 2
            else:
                mais_votado = mais_votados[0]
                mais_votado_lower = mais_votado.lower()
                if mais_votado_lower == nome_infiltrado.lower():
                    resultado = f"Os INOCENTES acertaram e eliminaram o Infiltrado ({nome_infiltrado})."
                    for conn in self.jogadores:
                        if self.jogadores[conn]['papel'] == 'INOCENTE':
                            self.jogadores[conn]['pontos'] += 1
                else:
                    resultado = f"O INFILTRADO venceu! Acusaram '{mais_votado}' erroneamente. O culpado era {nome_infiltrado}."
                    for conn in self.jogadores:
                        if self.jogadores[conn]['papel'] == 'INFILTRADO':
                            self.jogadores[conn]['pontos'] += 2

            pontos_atualizados = [(conn_jogador, dados['pontos']) for conn_jogador, dados in self.jogadores.items()]
            # Monta o texto do placar antes de sair do lock.
            placar_msg = "\\n📊 --- TABELA DE PONTUAÇÃO ---"
            for j in self.jogadores.values():
                placar_msg += f"\\n   🔹 {j['nome']}: {j['pontos']} pts"
            placar_msg += "\\n-------------------------------"
            self.estado_jogo = 'LOBBY'

        for conn_jogador, pontos in pontos_atualizados:
            try:
                enviar_msg(conn_jogador, f"SCORE_UPDATE|PTS:{pontos}")
            except:
                pass

        self.enviar_multicast(f"ROUND_END|RESULT:{resultado}")
        self.enviar_multicast(f"SYS|MSG:{placar_msg}")
        self.enviar_multicast("SYS|MSG:Lobby Aberto! O Host pode dar /start novamente.")


class ClienteJogador:
    def __init__(self, fila_global):
        # O cliente conversa com o servidor e também cuida da entrada do teclado.
        self.socket = None
        self.conectado = False
        self.meu_nome = ""
        self.vt = {}
        self.buffer_msgs = []

        self.rejeitado = False
        self.queda_silenciosa = False
        self.fila_inputs = fila_global
        self.vt_lock = threading.Lock()

    def conectar(self, nome, is_cerebro, host_jogo):
        global MEUS_PONTOS_GLOBAIS
        self.meu_nome = nome
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Limpa comandos antigos antes de conectar de novo.
        self.fila_inputs.queue.clear()

        tentativas = 0
        while tentativas < 5:
            try:
                self.socket.connect((host_jogo, PORTA_JOGO))
                self.conectado = True
                break
            except:
                time.sleep(1)
                tentativas += 1

        if not self.conectado:
            print("[!] Não encontramos o Cérebro ativo na rede.")
            return

        # O cliente precisa ouvir mensagens e ler comandos ao mesmo tempo.
        thread_ouvir = threading.Thread(target=self.ouvir_servidor)
        thread_ouvir.daemon = True
        thread_ouvir.start()

        enviar_msg(self.socket, f"JOIN|NAME:{nome}|CEREBRO:{is_cerebro}|PTS:{MEUS_PONTOS_GLOBAIS}")
        self.processar_inputs()

    def ouvir_servidor(self):
        global MEUS_PONTOS_GLOBAIS
        self.socket.settimeout(2.0)
        leitor = LeitorSocket(self.socket)
        for msg in leitor.ler_mensagens_iter():
            if not self.conectado:
                break
            if not msg:
                continue

            try:
                if msg.startswith("SCORE_UPDATE"):
                    # Ajuste silencioso do placar persistido localmente.
                    MEUS_PONTOS_GLOBAIS = int(msg.split("|")[1].split(":", 1)[1])
                    continue

                if msg.startswith("REJECT"):
                    texto = msg.split("|")[1].split(":", 1)[1]
                    print(f"\n❌ [ACESSO NEGADO] {texto}")
                    self.conectado = False
                    self.rejeitado = True
                    break

                elif msg.startswith("SYS"):
                    texto = msg.split("|")[1].split(":", 1)[1].replace("\\n", "\n")
                    print(f"\n[SISTEMA] {texto}")

                elif msg.startswith("CHAT|"):
                    # O chat pode chegar com ordem causal ou como mensagem simples.
                    partes = msg.split("|", 3)
                    remetente = partes[1].split(":", 1)[1]
                    vt_str = partes[2].split(":", 1)[1]
                    texto = partes[3].split(":", 1)[1]

                    if vt_str == "NULL":
                        print(f"[{remetente}]: {texto}")
                    else:
                        self.processar_entrega_causal(remetente, vt_str, texto)

                elif msg.startswith("ROLE"):
                    papel = msg.split("|")[1].split(":", 1)[1]
                    palavra = msg.split("|")[2].split(":", 1)[1]
                    print(f"\n🕵️ SEU PAPEL: {papel} | 🔑 SUA PALAVRA: {palavra}")

                elif msg.startswith("CHAT_START"):
                    with self.vt_lock:
                        self.vt.clear()
                        self.buffer_msgs.clear()
                    print(f"\n📢 {msg.split('|')[-1].split(':', 1)[1]}")

                elif msg.startswith("TIP_REQ") or msg.startswith("CHAT_END"):
                    print(f"\n📢 {msg.split('|')[-1].split(':', 1)[1]}")

                elif msg.startswith("ALL_TIPS"):
                    print("\n💡 --- DICAS DO GRUPO ---")
                    for d in msg.split("|")[1].split(":", 1)[1].split("&&"):
                        print(f"   • {d}")

                elif msg.startswith("ROUND_END"):
                    print(f"\n🏁 {msg.split('|')[1].split(':', 1)[1]}")

            except Exception:
                break

        if not self.rejeitado:
            print("\n🚨 [ALERTA DE FALHA] O Cérebro caiu ou reiniciou!")
            # Introduz jitter aleatório para que os nós não entrem na eleição ao mesmo tempo
            delay_aleatorio = 3.0 + random.uniform(0.1, 1.0)
            print(f">>> Reconfigurando o barramento via Algoritmo Bully em {delay_aleatorio:.2f} segundos...")
            self.queda_silenciosa = True
            time.sleep(delay_aleatorio)

        self.conectado = False

    def processar_entrega_causal(self, remetente, vt_str, texto):
        # Reconstrói o vetor lógico recebido na mensagem.
        vt_msg = {}
        if vt_str:
            for par in vt_str.split(";"):
                k, v = par.split("=")
                vt_msg[k] = int(v)

        with self.vt_lock:
            if remetente not in self.vt:
                self.vt[remetente] = 0
            for k in vt_msg:
                if k not in self.vt:
                    self.vt[k] = 0

            self.buffer_msgs.append({'r': remetente, 'v': vt_msg, 't': texto})

            entregou = True
            while entregou:
                entregou = False
                for m in self.buffer_msgs:
                    r = m['r']
                    v_m = m['v']

                    # A mensagem só pode sair do buffer se todas as dependências já chegaram.
                    cond1 = v_m.get(r, 1) == self.vt[r] + 1
                    cond2 = True
                    for k, v in v_m.items():
                        if k != r and v > self.vt.get(k, 0):
                            cond2 = False
                            break

                    if cond1 and cond2:
                        print(f"[{r}]: {m['t']}")
                        self.vt[r] += 1
                        self.buffer_msgs.remove(m)
                        entregou = True
                        break

    def processar_inputs(self):
        # Converte comandos do jogador no protocolo interno do jogo.
        while self.conectado:
            try:
                texto = self.fila_inputs.get(timeout=0.5)
            except queue.Empty:
                continue

            if texto.startswith("/dica "):
                pacote = f"TIP|WORD:{texto.replace('/dica ', '', 1).strip()}"
            elif texto.startswith("/voto "):
                pacote = f"VOTE|TARGET:{texto.replace('/voto ', '', 1).strip()}"
            elif texto == "/start":
                pacote = "CHAT_MSG|MSG:/start"
            elif texto == "/votar":
                pacote = "CHAT_MSG|MSG:/votar"
            elif texto == "/placar":
                pacote = "REQ_SCORE|MSG:null"
            else:
                # Mensagem normal de chat: incrementa o vetor lógico local.
                with self.vt_lock:
                    self.vt[self.meu_nome] = self.vt.get(self.meu_nome, 0) + 1
                    vt_formatado = ";".join([f"{k}={v}" for k, v in self.vt.items()])
                    meu_vt_val = self.vt[self.meu_nome]
                if not vt_formatado:
                    vt_formatado = f"{self.meu_nome}={meu_vt_val}"
                pacote = f"CHAT_MSG|VT:{vt_formatado}|MSG:{texto}"

            try:
                enviar_msg(self.socket, pacote)
            except:
                break


def capturar_teclado(fila):
    # Thread dedicada para não travar a leitura da rede enquanto o usuário digita.
    while True:
        try:
            texto = sys.stdin.readline().strip()
            if texto:
                fila.put(texto)
        except:
            pass
