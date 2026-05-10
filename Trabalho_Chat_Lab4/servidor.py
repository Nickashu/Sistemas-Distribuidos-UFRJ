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
    # cria o socket
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
	"""Recebe mensagens e atende requisições do cliente
	Entrada: socket da conexao e endereco do cliente
	Saida: """

	while True:
		data = clisock.recv(1024).decode('utf-8')  # recebe dados do cliente
		if not data:
			# remove conexao e encerra
			lock.acquire()
			if clisock in conexoes:
				del conexoes[clisock]
			lock.release()
			print(str(endr) + '-> desconectou')
			break
		try:
			msg_decoded = json.loads(data)  # formato da mensagem: JSON
		except Exception:
			# mensagem inválida
			print(str(endr) + '-> mensagem no formato inválido!')
			return

		# Códigos de mensagem:
		# -1 - Requisitar lista de usuários ativos
		# 0 - Informar nome do usuário e estabelecer conexão
		# 1 - Mudar status
		# 2 - Iniciar conversa
		# 3 - Encerrar aplicação

		if msg_decoded.get("operation") == 3:  # Cliente encerrou aplicação
			print(f'{conexoes[clisock].get("username", "Usuário desconhecido")} ({str(endr)}) -> encerrou')
			lock.acquire()
			if clisock in conexoes:
				del conexoes[clisock]  # retira o cliente da lista de conexoes ativas
			lock.release()
			break

		if msg_decoded.get("operation") == 0:  # Cliente informando nome de usuário e estabelecendo conexão
			username = msg_decoded.get('username')
			resposta = ''

			if any(conn_info["username"] == username for conn_info in conexoes.values()):
				resposta = f"ERRO: O nome de usuário '{username}' já está em uso. Conexão não estabelecida."
				print(f"[REGISTRO] Tentativa de duplicação: '{username}' de {endr}")
				try:
					clisock.sendall(resposta.encode('utf-8'))
				except Exception:
					pass
				return
			else:
				lock.acquire()
				conexoes[clisock] = {"endereco": endr, "username": username, "status": "Ativo"}
				lock.release()
				resposta = f"Bem-vindo, {username}! Seu status inicial é Ativo."
				print(f"[REGISTRO] Usuário '{username}' conectado de {endr} | Total: {len(conexoes)}")

			clisock.sendall(resposta.encode('utf-8'))

		elif msg_decoded.get("operation") == -1:  # Cliente solicitando lista de usuários ativos
			resposta = 'Lista de Usuários Ativos:\n'
			resposta += '\n'.join([f"{conn_info['username']} - {conn_info['status']}" for conn_info in conexoes.values()])
			print(f"[LISTA] {msg_decoded.get('username')} solicitou lista de usuários ativos")
			clisock.sendall(resposta.encode('utf-8'))

		elif msg_decoded.get("operation") == 1:  # Cliente solicitando mudança de status
			novo_status = msg_decoded.get('status')
			if novo_status in ["Ativo", "Inativo"]:
				lock.acquire()
				usuario_nome = ''
				if clisock in conexoes:
					usuario_nome = conexoes[clisock]['username']
					conexoes[clisock]['status'] = novo_status
				lock.release()
				print(f"[STATUS] '{usuario_nome}' mudou status para '{novo_status}'")
				resposta = f"Status de {usuario_nome} atualizado para {novo_status} com sucesso!"
			else:
				resposta = f"ERRO: Status '{novo_status}' é inválido. Status não atualizado."
			clisock.sendall(resposta.encode('utf-8'))

		elif msg_decoded.get("operation") == 2:  # Cliente solicitando iniciar conversa
			try:
				remetente = conexoes[clisock]["username"]
				dados = json.loads(msg_decoded["body"])
				destinatario = dados["to"]
				conteudo_msg = dados["data"]

				# Procura se o destinatário existe e está ativo
				socket_destinatario = None
				lock.acquire()
				for sock, info in conexoes.items():
					if info.get("username") == destinatario:
						socket_destinatario = sock
						break
				lock.release()

				if socket_destinatario:
					# Destinatário está ativo, envia a mensagem direto, em formato JSON: {"from": remetente, "data": conteudo_msg}
					msg_json = json.dumps({"from": remetente, "data": conteudo_msg})
					try:
						socket_destinatario.sendall(msg_json.encode('utf-8'))
						resposta = f"Mensagem enviada para {destinatario}."
						msg_preview = conteudo_msg[:50] if len(conteudo_msg) > 50 else conteudo_msg
						print(f"[MENSAGEM] '{remetente}' → '{destinatario}': {msg_preview}")
					except Exception as e:
						resposta = f"Erro ao enviar mensagem: {e}"
						print(f"[ERRO] Falha ao enviar de '{remetente}' para '{destinatario}': {e}")
				else:
					resposta = f"Não foi possível estabelecer comunicacao com {destinatario}."
					print(f"[OFFLINE] '{remetente}' tentou enviar para '{destinatario}', mas não está online")

			except Exception as e:
				resposta = f"ERRO ao processar mensagem: {e}"

			clisock.sendall(resposta.encode('utf-8'))

	clisock.close()  # encerra a conexao com o cliente


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
