import socket
import select
import sys
import threading
import json

# define a localizacao do servidor
HOST = '' # vazio indica que podera receber requisicoes a partir de qq interface de rede da maquina
PORT = 65432 # porta de acesso

# Banco de Dados  (não será necessário)
# IP_DADOS = 'localhost' 
# PORTA_DADOS = 65433

#define a lista de I/O de interesse (jah inclui a entrada padrao)
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

	# vincula a localizacao do servidor
	sock.bind((HOST, PORT))

	# coloca-se em modo de espera por conexoes
	sock.listen(5) 

	# configura o socket para o modo nao-bloqueante
	sock.setblocking(False)

	# inclui o socket principal na lista de entradas de interesse
	entradas.append(sock)
	
	print(f"Camada de Processamento pronta na porta {PORT}...")

	return sock

def aceitaConexao(sock):
	'''Aceita o pedido de conexao de um cliente
	Entrada: o socket do servidor
	Saida: o novo socket da conexao e o endereco do cliente'''

	# estabelece conexao com o proximo cliente
	clisock, endr = sock.accept()

	# registra a nova conexao
	lock.acquire()
	conexoes[clisock] = endr 
	lock.release() 

	return clisock, endr

def atendeRequisicoes(clisock, endr):
	'''Recebe mensagens e as envia de volta para o cliente (ate o cliente finalizar)
	Entrada: socket da conexao e endereco do cliente
	Saida: '''

	while True: 
		#recebe dados do cliente
		data = clisock.recv(1024).decode('utf-8')
		#formato da mensagem: JSON
		msg_decoded = json.loads(data)
		if not msg_decoded:
			print(str(endr) + '-> mensagem no formato inválido!')
			return
		if msg_decoded[operation] == 4:  #Cliente encerrou aplicação
			print(str(endr) + '-> encerrou')
			lock.acquire()
			del conexoes[clisock] #retira o cliente da lista de conexoes ativas
			lock.release()
			clisock.close() # encerra a conexao com o cliente
			return
		
		

		print(str(endr) + ': ' + str(data))
		arquivo, palavra = data.split(';')

		# --- Comunicação com a Camada de Dados ---
		try:
			with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s_dados:
				s_dados.connect((IP_DADOS, PORTA_DADOS))
				s_dados.sendall(arquivo.encode('utf-8'))
				conteudo = s_dados.recv(4096).decode('utf-8')
			
			# Lógica de Processamento
			if conteudo.startswith("ERRO:"):
				resposta = conteudo
			else:
				contagem = conteudo.count(palavra)
				resposta = str(contagem)
		except Exception as e:
			resposta = f"ERRO de conexão com camada de dados: {e}"

		clisock.sendall(resposta.encode('utf-8'))

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
