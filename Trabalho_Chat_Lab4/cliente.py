import socket
import json
import subprocess
import os
import threading
import queue

fila_respostas = queue.Queue()  #Fila thread-safe para o servidor responder à thread principal

def escuta_mensagens(s, NOME_USUARIO):   #A ideia aqui é que apenas a thread_escuta faça s.recv(), para evitar problemas de concorrência. Toda mensagem recebida é processada e, se for uma mensagem de outro usuário, é salva em um arquivo local. Se for uma resposta do servidor a um comando local, é colocada em uma fila para a thread principal ler e mostrar para o usuário.
    buffer = "" # Acumulador de dados que chegam do servidor, para lidar com mensagens que podem chegar em partes. A thread vai juntando o que chega nesse buffer até encontrar um \n, que indica o fim de uma mensagem completa. Assim, mesmo que uma mensagem chegue em partes, ela só será processada quando estiver completa. E se chegar mais de uma mensagem de uma vez, o loop while vai processar todas elas.
    
    while True:
        try:
            msg = s.recv(4096).decode('utf-8')
            if not msg: break
            
            buffer += msg  #Junta o que chegou com o que já tínhamos
            while '\n' in buffer:
                # Divide o buffer no primeiro \n que encontrar. msg recebe a mensagem completa, e o buffer fica com o resto.
                msg, buffer = buffer.split('\n', 1) 
                
                if not msg.strip(): continue
                
                try: msg_decoded = json.loads(msg)
                except json.JSONDecodeError: continue

                #Verifica se é uma mensagem de outro usuário
                if 'from' in msg_decoded:
                    remetente = msg_decoded.get('from')
                    conteudo = msg_decoded.get('data')
                    try:
                        with open(f"{NOME_USUARIO}_messages.txt", "a", encoding="utf-8") as f:
                            f.write(f"De: {remetente}\nMensagem: {conteudo}\n" + "-" * 40 + "\n")
                    except Exception:
                        pass
                else:
                    # Se não for mensagem de usuário, é uma resposta do servidor a algum comando local. Coloca na fila para a thread principal ler.
                    fila_respostas.put(msg_decoded)
                
        except Exception as e:
            print(f"Thread de escuta encerrada: {e}") 
            break

def clear_terminal():
    subprocess.run(["cls" if os.name == 'nt' else "clear"], shell=True)  #'nt' for Windows, 'posix' is for Linux/macOS

def aguardar_resposta_do_servidor(tipo_esperado):   #Vai ficar lendo a fila até encontrar uma resposta com o 'type' esperado.
    while True:
        resposta = fila_respostas.get()
        if resposta.get('type') == tipo_esperado:
            return resposta.get('data', 'Operação realizada!')   #Retorna o dicionário completo e sai da função
        else:
            print(f"\n[Aviso do Servidor]: {resposta}")  #Lida com mensagens inesperadas que chegaram na hora errada

def main():
    IP_PROCESSAMENTO = '127.0.0.1'
    PORTA_PROCESSAMENTO = 65432
    STATUS_USUARIO = 1
    NOME_USUARIO = input("Digite seu nome de usuário: ")
    msg_retorno = ''

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((IP_PROCESSAMENTO, PORTA_PROCESSAMENTO))
        msg = {"operation": "connection", "username": NOME_USUARIO}
        msg_json = json.dumps(msg)
        s.sendall(f"{msg_json}\n".encode('utf-8'))

        thread_escuta = threading.Thread(target=escuta_mensagens, args=(s, NOME_USUARIO), daemon=True)
        thread_escuta.start()

        resultado = aguardar_resposta_do_servidor("connection")
        msg_retorno += f"Conectado ao servidor de processamento!\n{resultado}"
    except Exception as e:
        print(f"Erro ao conectar ao servidor de processamento: {e}")
        return

    while True:
        clear_terminal()
        if len(msg_retorno) > 0:
            print(f"{msg_retorno}\n\n")
            msg_retorno = ''
        print("======APLICAÇÃO DE CHAT======")
        print(f"Status: {'Ativo' if STATUS_USUARIO == 1 else 'Inativo'}")
        op_str = input(f"\n1 - Mudar status para {'Inativo' if STATUS_USUARIO == 1 else 'Ativo'}\n2 - Iniciar conversa\n3 - Visualizar mensagens recebidas\n4 - Encerrar aplicação\nEscolha uma opção: ").strip()
        op = -1
        try:
            op = int(op_str)
            if op > 4 or op < 1:
                raise Exception("Escolha inválida")
        except:
            msg_retorno += "Erro ao processar escolha. Tente novamente."
            continue
        
        data = ''
        id_user = ''
        status = 'Ativo' if STATUS_USUARIO == 1 else 'Inativo'
        
        if op == 1:  #Se quiser mudar status, só precisa enviar a nova informação de status ao servidor de processamento
            status = 'Inativo' if STATUS_USUARIO == 1 else 'Ativo'
            op = "change_status"
            
        elif op == 2:  #Se quiser começar uma conversa, vai precisar primeiro ver lista de usuarios ativos
            try:
                msg = {"operation": "list_user", "username": NOME_USUARIO}   #Apenas para requisitar a lista e usuários ativos ao servidor
                msg_json = json.dumps(msg)  #Convert to JSON string
                s.sendall(f"{msg_json}\n".encode('utf-8'))
                
                resultado = aguardar_resposta_do_servidor("list_user")
                id_user = input(f"{resultado}\nInforme o usuário para iniciar a conversa: ")
                data = input(f"Agora digite a mensagem: ")
                op = "send_message"
            except Exception as e:
                msg_retorno += f"Erro ao contactar servidor de processamento: {e}"
        
        elif op == 3:  
            try:
                with open(f"{NOME_USUARIO}_messages.txt", "r", encoding="utf-8") as f:
                    conteudo = f.read()
                    
                    if conteudo.strip(): #Verifica se o arquivo não está apenas com espaços em branco
                        msg_retorno += f"--- SUAS MENSAGENS ---\n\n{conteudo}"
                    else:
                        msg_retorno += "Sua caixa de mensagens está vazia."
                        
            except FileNotFoundError: msg_retorno += "Nenhuma mensagem recebida ainda. O histórico está vazio."  #Se o arquivo não existe, ninguém mandou mensagem ainda
            except Exception as e: msg_retorno += f"Erro desconhecido ao ler mensagens: {e}"
                
            continue

        if op == 4:  #Encerrar
            op = "disconnect"
        
        msg_data = {"to": id_user, "data": data}
        msg_data_json = json.dumps(msg_data)  #Convert to JSON string
        msg = {"operation": op, "username": NOME_USUARIO, "status": status, "body": msg_data_json}
        msg_json = json.dumps(msg)  #Convert to JSON string

        try:
            s.sendall(f"{msg_json}\n".encode('utf-8'))
            resultado = aguardar_resposta_do_servidor(op)
            msg_retorno += resultado
            STATUS_USUARIO = 1 if status == 'Ativo' else 0
            if op == "disconnect":
                s.close()
                break
        except Exception as e:
            msg_retorno += f"Erro ao contactar servidor de processamento: {e}"
    
    print("\nObrigado por usar a aplicação!")

if __name__ == "__main__":
    main()