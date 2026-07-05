import socket
import threading
import time
import random
import sys
import queue 

# ==============================================================================
# CONFIGURAÇÕES GLOBAIS DA REDE
# ==============================================================================
HOST = '127.0.0.1' 
PORTA_JOGO = 5555       
PORTAS_BULLY = [5001, 5002, 5003, 5004, 5005] 
BUFFER = 1024      

PARES_DE_PALAVRAS = [
    ("Praia", "Piscina"),
    ("Cachorro", "Lobo"),
    ("Violão", "Baixo"),
    ("Avião", "Helicóptero")
]

# Variável Global de Persistência (O Cliente faz backup do seu estado)
MEUS_PONTOS_GLOBAIS = 0

# ==============================================================================
# CLASSE DO SERVIDOR (O "CÉREBRO") -> Módulo 3: Servidor Stateful e Concorrente
# ==============================================================================
class ServidorCerebro:
    def __init__(self):
        self.jogadores = {}
        self.estado_jogo = 'LOBBY' 
        self.rodada_encerrada = False
        self.estado_lock = threading.RLock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((HOST, PORTA_JOGO))

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
        try:
            msg_inicial = conn.recv(BUFFER).decode('utf-8')
            if msg_inicial.startswith("JOIN"):
                partes = msg_inicial.split("|")
                nome = partes[1].split(":", 1)[1]
                is_host = (partes[2].split(":", 1)[1] == "True")
                
                # [MÓDULO 3] RECUPERAÇÃO DE ESTADO DISTRIBUÍDO: Lê os pontos do cliente
                pontos_recuperados = int(partes[3].split(":", 1)[1])
                
                if self.estado_jogo != 'LOBBY':
                    conn.send("REJECT|MSG:Partida em andamento! Acesso negado.".encode('utf-8'))
                    conn.close()
                    return 

                # Instancia o jogador no servidor com os pontos que ele já tinha
                self.jogadores[conn] = {
                    'nome': nome, 'papel': '', 'palavra': '', 
                    'dica': '', 'quer_votar': False, 'voto': '',
                    'pontos': pontos_recuperados, 
                    'is_host': is_host
                }
                
                self.enviar_multicast(f"SYS|MSG:{nome} entrou! (Total: {len(self.jogadores)})")
                
                if is_host:
                    time.sleep(0.1)
                    conn.send("SYS|MSG:Você é o HOST! Digite /start para iniciar a rodada.".encode('utf-8'))

            while True:
                msg = conn.recv(BUFFER).decode('utf-8').strip()
                if not msg: break 
                nome_remetente = self.jogadores[conn]['nome']

                # --- MAQUINA DE ESTADOS DO SERVIDOR ---
                if self.estado_jogo == 'LOBBY':
                    if msg == "CHAT_MSG|MSG:/start":
                        if self.jogadores[conn]['is_host']:
                            self.iniciar_partida()
                        else:
                            conn.send("SYS|MSG:Acesso negado. Somente o Host pode dar /start.".encode('utf-8'))
                    
                    elif msg == "REQ_SCORE|MSG:null":
                        placar_msg = "\\n📊 --- PLACAR ATUAL ---"
                        for j in self.jogadores.values():
                            placar_msg += f"\\n   🔹 {j['nome']}: {j['pontos']} pts"
                        placar_msg += "\\n-----------------------"
                        conn.send(f"SYS|MSG:{placar_msg}".encode('utf-8'))
                        
                    elif msg.startswith("CHAT_MSG"):
                        # [CORREÇÃO] Se o cliente mandou um comando tipo /votar no lobby,
                        # ele vem em 2 partes. Se for chat normal, vem em 3 partes (com o VT).
                        partes = msg.split("|")
                        if len(partes) >= 3:
                            texto = partes[2].split(":", 1)[1]
                        else:
                            # Se for o /votar no lobby, extrai da posição 1
                            texto = partes[1].split(":", 1)[1]
                        
                        # Avisa que esse comando não tem efeito no Lobby ou repassa o texto normal
                        if texto == "/votar":
                            conn.send("SYS|MSG:O comando /votar só tem efeito durante a fase de chat.".encode('utf-8'))
                        else:
                            self.enviar_multicast(f"CHAT|FROM:{nome_remetente}|VT:NULL|MSG:{texto}")

                elif self.estado_jogo == 'DICAS':
                    if msg.startswith("TIP"):
                        if self.jogadores[conn]['dica'] == '':
                            dica = msg.split("|")[1].split(":", 1)[1]
                            self.jogadores[conn]['dica'] = dica 
                            self.enviar_multicast(f"SYS|MSG:{nome_remetente} enviou sua dica!")
                            self.checar_todas_as_dicas()
                        else:
                            conn.send("SYS|MSG:Você já enviou sua dica!".encode('utf-8'))
                    else:
                        conn.send("SYS|MSG:Digite /dica [palavra] para prosseguir.".encode('utf-8'))

                elif self.estado_jogo == 'CHAT':
                    if self.jogadores[conn]['quer_votar']:
                        conn.send("SYS|MSG:Aguarde os outros terminarem.".encode('utf-8'))
                        continue 
                        
                    if msg == "CHAT_MSG|MSG:/votar":
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

                elif self.estado_jogo == 'VOTACAO':
                    if msg.startswith("VOTE"):
                        if self.jogadores[conn]['voto'] == '':
                            voto_alvo = msg.split("|")[1].split(":", 1)[1].strip()
                            lista_nomes = [j['nome'].lower() for j in self.jogadores.values()]
                            if voto_alvo.lower() in lista_nomes:
                                self.jogadores[conn]['voto'] = voto_alvo
                                self.enviar_multicast(f"SYS|MSG:{nome_remetente} votou!")
                                time.sleep(0.2) 
                                self.checar_todos_votos()
                            else:
                                conn.send(f"SYS|MSG:Voto inválido! Nome não encontrado.".encode('utf-8'))
                        else:
                            conn.send("SYS|MSG:Você já votou!".encode('utf-8'))
                    else:
                        conn.send("SYS|MSG:Discussão fechada! Digite /voto [nome].".encode('utf-8'))

        except Exception as e:
            pass
        finally:
            if conn in self.jogadores:
                nome_caiu = self.jogadores[conn]['nome']
                del self.jogadores[conn]
                self.enviar_multicast(f"SYS|MSG:{nome_caiu} caiu. Total ativo: {len(self.jogadores)}")
                if self.estado_jogo != 'LOBBY':
                    self.estado_jogo = 'LOBBY'
                    self.enviar_multicast("SYS|MSG:Partida interrompida por queda. Retornando ao Lobby!")
            conn.close()

    def enviar_multicast(self, mensagem):
        for cliente in list(self.jogadores.keys()):
            try:
                cliente.send(mensagem.encode('utf-8'))
            except:
                pass

    def iniciar_partida(self):
        with self.estado_lock:
            if len(self.jogadores) < 3: 
                self.enviar_multicast("SYS|MSG:Mínimo de 3 jogadores necessários para iniciar!")
                return
                
            self.estado_jogo = 'DICAS'
            self.rodada_encerrada = False
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
                conn.send(msg.encode('utf-8'))

        time.sleep(0.5)
        self.enviar_multicast("TIP_REQ|MSG:Rodada começou! Digite /dica [palavra]")

    def checar_todas_as_dicas(self):
        with self.estado_lock:
            if self.estado_jogo != 'DICAS' or self.rodada_encerrada:
                return
            if not all(j['dica'] != '' for j in self.jogadores.values()):
                return
            lista_dicas = "&&".join([f"{j['nome']} disse: '{j['dica']}'" for j in self.jogadores.values()])
            self.estado_jogo = 'CHAT'

        self.enviar_multicast(f"ALL_TIPS|LIST:{lista_dicas}")
        time.sleep(0.5)
        self.enviar_multicast("CHAT_START|MSG:[CHAT ABERTO] Quem é o Infiltrado? Digite /votar para pular o chat.")

    def iniciar_votacao(self):
        with self.estado_lock:
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
                resultado = f"Deu EMPATE! Sem consenso, o INFILTRADO ({nome_infiltrado}) escapou e ganhou 2 pontos!"
                for conn in self.jogadores:
                    if self.jogadores[conn]['papel'] == 'INFILTRADO':
                        self.jogadores[conn]['pontos'] += 2 
            else:
                mais_votado = mais_votados[0]
                if mais_votado.lower() == nome_infiltrado.lower():
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
            placar_msg = "\\n📊 --- TABELA DE PONTUAÇÃO ---"
            for j in self.jogadores.values():
                placar_msg += f"\\n   🔹 {j['nome']}: {j['pontos']} pts"
            placar_msg += "\\n-------------------------------"
            self.estado_jogo = 'LOBBY'

        # Entrega fora do lock para não prender outras mensagens durante I/O de rede
        for conn_jogador, pontos in pontos_atualizados:
            try: 
                conn_jogador.send(f"SCORE_UPDATE|PTS:{pontos}".encode('utf-8'))
            except: pass
                
        time.sleep(0.3) # Timeout de segurança TCP
        self.enviar_multicast(f"ROUND_END|RESULT:{resultado}")
        
        time.sleep(0.5)
        self.enviar_multicast(f"SYS|MSG:{placar_msg}")
        self.enviar_multicast("SYS|MSG:Lobby Aberto! O Host pode dar /start novamente.")


# ==============================================================================
# CLASSE DO CLIENTE E SINCRONIZAÇÃO CAUSAL (MÓDULO 6)
# ==============================================================================
class ClienteJogador:
    def __init__(self, fila_global): 
        self.socket = None
        self.conectado = False
        self.meu_nome = ""
        self.vt = {} 
        self.buffer_msgs = []
        
        self.rejeitado = False
        self.queda_silenciosa = False
        self.fila_inputs = fila_global 

    def conectar(self, nome, is_cerebro):
        self.meu_nome = nome
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.fila_inputs.queue.clear() 
        
        tentativas = 0
        while tentativas < 5:
            try:
                self.socket.connect((HOST, PORTA_JOGO))
                self.conectado = True
                break
            except:
                time.sleep(1) 
                tentativas += 1

        if not self.conectado:
            print("[!] Não encontramos o Cérebro ativo na rede.")
            return

        thread_ouvir = threading.Thread(target=self.ouvir_servidor)
        thread_ouvir.daemon = True 
        thread_ouvir.start()
        
        time.sleep(0.1)
        # [MÓDULO 3] Backup Local: Envia para o Cérebro a quantidade de pontos que possui globalmente
        global MEUS_PONTOS_GLOBAIS
        self.socket.send(f"JOIN|NAME:{nome}|CEREBRO:{is_cerebro}|PTS:{MEUS_PONTOS_GLOBAIS}".encode('utf-8'))
        self.processar_inputs()

    def ouvir_servidor(self):
        self.socket.settimeout(2.0)
        while self.conectado:
            try:
                msg = self.socket.recv(BUFFER).decode('utf-8')
                if not msg: break
                
                # Desempacota atualizações silenciosas do Servidor
                if msg.startswith("SCORE_UPDATE"):
                    global MEUS_PONTOS_GLOBAIS
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
                    
            except socket.timeout:
                continue 
            except Exception as e:
                break 
        
        if not self.rejeitado:
            print("\n🚨 [ALERTA DE FALHA] O Cérebro caiu ou reiniciou!")
            print(">>> Reconfigurando o barramento via Algoritmo Bully em 3 segundos...")
            self.queda_silenciosa = True
            time.sleep(3) 
            
        self.conectado = False

    def processar_entrega_causal(self, remetente, vt_str, texto):
        vt_msg = {}
        if vt_str:
            for par in vt_str.split(";"):
                k, v = par.split("=")
                vt_msg[k] = int(v)

        if remetente not in self.vt: self.vt[remetente] = 0
        for k in vt_msg:
            if k not in self.vt: self.vt[k] = 0

        self.buffer_msgs.append({'r': remetente, 'v': vt_msg, 't': texto})

        entregou = True
        while entregou:
            entregou = False
            for m in self.buffer_msgs:
                r = m['r']
                v_m = m['v']
                
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
        while self.conectado:
            try:
                texto = self.fila_inputs.get(timeout=0.5)
            except queue.Empty:
                continue 
            
            if texto.startswith("/dica "): pacote = f"TIP|WORD:{texto.replace('/dica ', '', 1).strip()}"
            elif texto.startswith("/voto "): pacote = f"VOTE|TARGET:{texto.replace('/voto ', '', 1).strip()}"
            elif texto == "/start": pacote = "CHAT_MSG|MSG:/start"
            elif texto == "/votar": pacote = "CHAT_MSG|MSG:/votar"
            elif texto == "/placar": pacote = "REQ_SCORE|MSG:null"
            else:
                self.vt[self.meu_nome] = self.vt.get(self.meu_nome, 0) + 1
                vt_formatado = ";".join([f"{k}={v}" for k, v in self.vt.items()])
                if not vt_formatado: vt_formatado = f"{self.meu_nome}={self.vt[self.meu_nome]}"
                pacote = f"CHAT_MSG|VT:{vt_formatado}|MSG:{texto}"
                
            try: self.socket.send(pacote.encode('utf-8'))
            except: break


# ==============================================================================
# ALGORITMO BULLY NÃO-PREEMPTIVO
# ==============================================================================
def responder_pings_bully(meu_socket):
    while True:
        try:
            conn, _ = meu_socket.accept()
            conn.close() 
        except:
            break

def executar_eleicao_bully(meu_id):
    try:
        teste_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        teste_conn.settimeout(0.3)
        teste_conn.connect((HOST, PORTA_JOGO))
        teste_conn.close()
        return False 
    except:
        pass 

    print(f"🔍 [BULLY] Identidade local {meu_id}. Varrendo IDs maiores...")
    alguem_maior_vivo = False
    
    for porta_alvo in range(meu_id + 1, PORTAS_BULLY[-1] + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2) 
            s.connect((HOST, porta_alvo))
            alguem_maior_vivo = True
            s.close()
            break 
        except:
            pass 
            
    if not alguem_maior_vivo:
        return True 
    else:
        print(f"⏳ [BULLY] Nó superior ativo. Aguardando servidor...")
        time.sleep(2) 
        return False

# ==============================================================================
# LEITOR GLOBAL DE TECLADO
# ==============================================================================
def capturar_teclado(fila):
    while True:
        try:
            texto = sys.stdin.readline().strip()
            if texto: fila.put(texto)
        except: pass

# ==============================================================================
# INÍCIO DO PROGRAMA (MAIN)
# ==============================================================================
if __name__ == "__main__":
    print("--- A PALAVRA INFILTRADA ---")
    nome_jogador = input("Escolha seu codinome: ").strip()
    while not nome_jogador:
        nome_jogador = input("Escolha um codinome: ").strip()
    
    meu_id = 0
    meu_socket_bully = None
    
    for porta in PORTAS_BULLY:
        try:
            tentativa_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tentativa_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            tentativa_socket.bind((HOST, porta))
            tentativa_socket.listen()
            meu_id = porta
            meu_socket_bully = tentativa_socket
            break 
        except OSError:
            tentativa_socket.close()
            continue
            
    if meu_id == 0:
        print("Limite máximo de 5 jogadores locais atingido.")
        sys.exit()

    threading.Thread(target=responder_pings_bully, args=(meu_socket_bully,), daemon=True).start()

    fila_de_teclado = queue.Queue()
    threading.Thread(target=capturar_teclado, args=(fila_de_teclado,), daemon=True).start()

    servidor_ativo = False
    
    while True:
        sou_lider = executar_eleicao_bully(meu_id)
        
        if sou_lider and not servidor_ativo:
            cerebro = ServidorCerebro()
            threading.Thread(target=cerebro.iniciar, daemon=True).start()
            servidor_ativo = True
            time.sleep(1) 
            
        jogador = ClienteJogador(fila_de_teclado)
        jogador.conectar(nome_jogador, is_cerebro=sou_lider)
        
        if jogador.rejeitado:
            sys.exit()
            
        if jogador.queda_silenciosa:
            try:
                jogador.socket.close()
            except:
                pass
            time.sleep(1) 
            continue