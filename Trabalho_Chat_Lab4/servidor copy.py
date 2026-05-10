import socket
import select
import sys
import threading
import json

# define a localizacao do servidor
HOST = '' # vazio indica que podera receber requisicoes a partir de qq interface de rede da maquina
PORT = 65432 # porta de acesso

#define a lista de I/O de interesse (ja inclui a entrada padrao)
entradas = [sys.stdin]
#armazena as conexoes completadas
conexoes = {}
#lock para acesso do dicionario 'conexoes'
lock = threading.Lock()

def iniciaServidor():
	'''Cria um socket de servidor e o coloca em modo de espera por conexoes
	Saida: o socket criado'''
	# cria o socket 
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) #Internet( IPv4 + TCP) 
	sock.bind((HOST, PORT))  # vincula a localizacao do servidor
	sock.listen(5)   # coloca-se em modo de espera por conexoes
	sock.setblocking(False)  # configura o socket para o modo nao-bloqueante
	entradas.append(sock)  # inclui o socket principal na lista de entradas de interesse
	print(f"Camada de Processamento pronta na porta {PORT}...")

	return sock

def aceitaConexao(sock):
	'''Aceita o pedido de conexao de um cliente
	Entrada: o socket do servidor
	Saida: o novo socket da conexao e o endereco do cliente'''

	clisock, endr = sock.accept()  # estabelece conexao com o proximo cliente

	# registra a nova conexao
	#lock.acquire()
	#conexoes[clisock] = endr 
	#lock.release() 

	return clisock, endr

def atendeRequisicoes(clisock, endr):
	'''Recebe mensagens e as envia de volta para o cliente (ate o cliente finalizar)
	Entrada: socket da conexao e endereco do cliente
	Saida: '''

	while True:
		data = clisock.recv(1024).decode('utf-8')  #recebe dados do cliente
		msg_decoded = json.loads(data)  #formato da mensagem: JSON
		if not msg_decoded:
			print(str(endr) + '-> mensagem no formato inválido!')
			return
		#Códigos de mensagem: 
		# -1 - Requisitar lista de usuários ativos
		# 0 - Informar nome do usuário e estabelecer conexão
		# 1 - Mudar status
		# 2 - Iniciar conversa
		# 3 - Encerrar aplicação
		if msg_decoded["operation"] == 3:  #Cliente encerrou aplicação
			print(str(endr) + '-> encerrou')
			lock.acquire()
			del conexoes[clisock] #retira o cliente da lista de conexoes ativas
			lock.release()
			break

		if msg_decoded["operation"] == 0:  #Cliente informando nome de usuário e estabelecendo conexão
			#O dicionário 'conexoes' armazena essas informações: conexoes[clisock] = {"endereco": endr, "username": msg_decoded['body']['name'], "status": "Ativo"}
			#Se o username já existir, deve retornar uma mensagem de erro e não estabelecer a conexão
			username = msg_decoded['username']
			resposta = ''

			if any(conn_info["username"] == username for conn_info in conexoes.values()):
				resposta = f"ERRO: O nome de usuário '{username}' já está em uso. Conexão não estabelecida."
				clisock.close() #Encerra a conexao com o cliente
			else:
				lock.acquire()
				conexoes[clisock] = {"endereco": endr, "username": msg_decoded['username'], "status": "Ativo"}
				lock.release()
				resposta = f"Bem-vindo, {msg_decoded['username']}! Seu status inicial é Ativo."
				print(f"Usuário '{username}' conectado com o endereço {endr}.")

			clisock.sendall(resposta.encode('utf-8'))

		elif msg_decoded["operation"] == -1:  #Cliente solicitando lista de usuários ativos
			#A resposta deve ser uma lista dos usuários ativos, incluindo seus nomes e status
			resposta = 'Lista de Usuários Ativos:\n'
			resposta += '\n'.join([f"{conn_info['username']} - {conn_info['status']}" for conn_info in conexoes.values()])
			clisock.sendall(resposta.encode('utf-8'))

		elif msg_decoded["operation"] == 1:  #Cliente solicitando mudança de status
			novo_status = msg_decoded['body']['status']
			if novo_status in ["Ativo", "Inativo"]:
				lock.acquire()
				conexoes[clisock]['status'] = novo_status
				lock.release()
				resposta = f"Status de {conexoes[clisock]['username']} atualizado para {novo_status} com sucesso!"
				#print(f"Usuário '{conexoes[clisock]['username']}' mudou status para {novo_status}.")
			else:
				resposta = f"ERRO: Status '{novo_status}' é inválido. Status não atualizado."
			clisock.sendall(resposta.encode('utf-8'))

		elif msg_decoded["operation"] == 2:  #Cliente solicitando iniciar conversa
			#O corpo da mensagem deve conter o identificador do usuário com quem deseja conversar e a mensagem a ser enviada


		#print(str(endr) + ': ' + str(data))
		#arquivo, palavra = data.split(';')

		# --- Comunicação com a Camada de Dados ---
		#try:
		#	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s_dados:
		#		s_dados.connect((IP_DADOS, PORTA_DADOS))
		#		s_dados.sendall(arquivo.encode('utf-8'))
		#		conteudo = s_dados.recv(4096).decode('utf-8')

			# Lógica de Processamento
		#	if conteudo.startswith("ERRO:"):
		#		resposta = conteudo
		#	else:
		#		contagem = conteudo.count(palavra)
		#		resposta = str(contagem)
		#except Exception as e:
		#	resposta = f"ERRO de conexão com camada de dados: {e}"

		#clisock.sendall(resposta.encode('utf-8'))

	clisock.close() # encerra a conexao com o cliente


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
