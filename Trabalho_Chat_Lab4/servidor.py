import socket
import select
import sys
import threading
import json

# define a localizacao do servidor
HOST = ''  # vazio indica que podera receber requisicoes a partir de qq interface de rede da maquina
PORT = 65432  # porta de acesso

entradas = [sys.stdin]   # define a lista de I/O de interesse (ja inclui a entrada padrao)
conexoes = {}  # armazena as conexoes completadas
lock = threading.Lock()  # lock para acesso do dicionario 'conexoes'

def iniciaServidor():
    """Cria um socket de servidor e o coloca em modo de espera por conexoes"""
    #Cria o socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Internet( IPv4 + TCP)
    sock.bind((HOST, PORT))  # vincula a localizacao do servidor
    sock.listen(5)  # coloca-se em modo de espera por conexoes
    sock.setblocking(False)  # configura o socket para o modo nao-bloqueante
    entradas.append(sock)  # inclui o socket principal na lista de entradas de interesse
    print(f"Camada de Processamento pronta na porta {PORT}...")

    return sock


def aceitaConexao(sock):
    """Aceita o pedido de conexao de um cliente
    Entrada: o socket do servidor
    Saida: o novo socket da conexao e o endereco do cliente"""

    clisock, endr = sock.accept()  # estabelece conexao com o proximo cliente

    return clisock, endr


def atendeRequisicoes(clisock, endr):
    """Recebe mensagens e atende requisições do cliente"""

    buffer = ""   # Acumulador para lidar com o fluxo TCP

    while True:
        try: data = clisock.recv(4096).decode('utf-8')
        except Exception: break

        if not data:
            #Remove conexao e encerra
            lock.acquire()
            if clisock in conexoes:
                del conexoes[clisock]
            lock.release()
            print(str(endr) + ' -> desconectou abruptamente')
            break

        buffer += data  #Usando a mesma estratégia de buffer da thread de escuta do cliente, para lidar com mensagens que podem chegar em partes ou múltiplas mensagens de uma vez

        while '\n' in buffer:  #Separa a primeira mensagem completa e guarda o resto
            msg_completa, buffer = buffer.split('\n', 1)

            if not msg_completa.strip():
                continue

            try:
                msg_decoded = json.loads(msg_completa)
            except Exception:
                print(str(endr) + ' -> mensagem no formato inválido!')
                continue

            # Códigos de mensagem:
            # "list_user" - Requisitar lista de usuários ativos
            # "connection" - Estabelecer conexão
            # "change_status" - Mudar status
            # "send_message" - Enviar mensagem
            # "disconnect" - Encerrar aplicação

            op = msg_decoded.get("operation")

            if op == "disconnect":  #Cliente encerrou aplicação
                print(f'{conexoes[clisock].get("username", "Usuário desconhecido")} ({str(endr)}) -> encerrou')
                lock.acquire()
                if clisock in conexoes:
                    del conexoes[clisock]  # retira o cliente da lista de conexoes ativas
                lock.release()

                #Manda a última mensagem e fecha o socket aqui mesmo
                resposta = {"type": "disconnect", "data": "Usuário desconectado do servidor de processamento."}
                try: clisock.sendall(f"{json.dumps(resposta)}\n".encode('utf-8'))
                except Exception: pass
                clisock.close()
                return

            if op == "connection":  #Cliente informando nome de usuário e estabelecendo conexão
                username = msg_decoded.get('username')
                resposta = {}
                lock.acquire()
                username_existe = any(conn_info["username"] == username for conn_info in conexoes.values())
                lock.release()
                if username_existe:
                    resposta = {"type": "connection", "data": f"ERRO: O nome de usuário '{username}' já está em uso. Conexão não estabelecida."}
                    print(f"[REGISTRO] Tentativa de duplicação: '{username}' de {endr}")
                    try: clisock.sendall(f"{json.dumps(resposta)}\n".encode('utf-8'))
                    except Exception: pass
                    clisock.close()
                    return
                else:
                    lock.acquire()
                    conexoes[clisock] = {"endereco": endr, "username": username, "status": "Ativo"}
                    lock.release()
                    resposta = {"type": "connection", "data": f"Bem-vindo(a), {username}! Seu status inicial é Ativo."}
                    print(f"[REGISTRO] Usuário '{username}' conectado de {endr} | Total: {len(conexoes)}")

                clisock.sendall(f"{json.dumps(resposta)}\n".encode('utf-8'))

            elif op == "list_user":  #Cliente solicitando lista de usuários ativos
                resposta_data = 'Lista de Usuários:\n'
                lock.acquire()
                resposta_data += '\n'.join([f"{conn_info['username']} - {conn_info['status']}" for conn_info in conexoes.values()])
                lock.release()
                resposta = {"type": "list_user", "data": resposta_data}
                print(f"[LISTA] {msg_decoded.get('username')} solicitou lista de usuários ativos")
                try: clisock.sendall(f"{json.dumps(resposta)}\n".encode('utf-8'))
                except Exception: pass

            elif op == "change_status":  #Cliente solicitando mudança de status
                novo_status = msg_decoded.get('status')
                if novo_status in ["Ativo", "Inativo"]:
                    lock.acquire()
                    usuario_nome = ''
                    if clisock in conexoes:
                        usuario_nome = conexoes[clisock]['username']
                        conexoes[clisock]['status'] = novo_status
                    lock.release()
                    print(f"[STATUS] '{usuario_nome}' mudou status para '{novo_status}'")
                    resposta = {"type": "change_status", "data": f"Status de {usuario_nome} atualizado para {novo_status} com sucesso!"}
                else:
                    resposta = {"type": "change_status", "data": f"ERRO: Status '{novo_status}' é inválido. Status não atualizado."}
                try: clisock.sendall(f"{json.dumps(resposta)}\n".encode('utf-8'))
                except Exception: pass

            elif op == "send_message":  #Cliente solicitando iniciar conversa
                try:
                    remetente = conexoes[clisock]["username"]
                    dados = json.loads(msg_decoded["body"])
                    destinatario = dados["to"]
                    conteudo_msg = dados["data"]

                    #Verifica se o destinatário existe e está ativo
                    socket_destinatario = None
                    lock.acquire()
                    for sock, info in conexoes.items():
                        if info.get("username") == destinatario and info.get("status") == "Ativo" and sock != clisock:   #Se encontrar o destinatário e ele estiver ativo, guarda o socket para enviar a mensagem
                            socket_destinatario = sock
                            break
                    lock.release()

                    if socket_destinatario:
                        #Destinatário está ativo, envia a mensagem direto, em formato JSON: {"from": remetente, "data": conteudo_msg}
                        msg_json = json.dumps({"from": remetente, "data": conteudo_msg})
                        try:
                            socket_destinatario.sendall(f"{msg_json}\n".encode('utf-8'))
                            resposta = {"type": "send_message", "data": f"Mensagem enviada para {destinatario}."}
                            msg_preview = conteudo_msg[:50] if len(conteudo_msg) > 50 else conteudo_msg
                            print(f"[MENSAGEM] '{remetente}' → '{destinatario}': {msg_preview}")
                        except Exception as e:
                            resposta = {"type": "send_message", "data": f"Erro ao enviar mensagem: {e}"}
                            print(f"[ERRO] Falha ao enviar de '{remetente}' para '{destinatario}': {e}")
                    else:
                        resposta = {"type": "send_message", "data": f"Não foi possível estabelecer comunicacao com {destinatario}."}
                        print(f"'{remetente}' tentou enviar para '{destinatario}', mas não foi possível estabelecer comunicação.")

                except Exception as e:
                    resposta = {"type": "send_message", "data": f"ERRO ao processar mensagem: {e}"}

                try: clisock.sendall(f"{json.dumps(resposta)}\n".encode('utf-8'))
                except Exception: pass

    clisock.close()


def main():
    '''Inicializa e implementa o loop principal (infinito) do servidor'''
    sock = iniciaServidor()
    print("Pronto para receber conexoes...")
    while True:
        #espera por qualquer entrada de interesse
        leitura, escrita, excecao = select.select(entradas, [], [])
        #tratar todas as entradas prontas
        for pronto in leitura:
            if pronto == sock:  #pedido novo de conexao
                clisock, endr = aceitaConexao(sock)
                print ('Conectado com: ', endr)
                #cria nova thread para atender o cliente
                cliente = threading.Thread(target=atendeRequisicoes, args=(clisock,endr))
                cliente.start()
                #atendeRequisicoes(clisock, endr)
            elif pronto == sys.stdin: #entrada padrao
                cmd = input()
                if cmd == 'fim': #solicitacao de finalizacao do servidor
                    if not conexoes: #somente termina quando nao houver clientes ativos
                        sock.close()
                        sys.exit()
                    else: print("ha conexoes ativas")
                elif cmd == 'hist': #outro exemplo de comando para o servidor
                    print(str(conexoes.values()))

main()
