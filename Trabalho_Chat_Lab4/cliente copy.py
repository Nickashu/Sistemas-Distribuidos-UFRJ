import socket
import json
import subprocess
import os

def clear_terminal():
    subprocess.run(["cls" if os.name == 'nt' else "clear"], shell=True)  #'nt' for Windows, 'posix' is for Linux/macOS

def main():
    # IP do Servidor
    IP_PROCESSAMENTO = 'xxx.xxx.x.xx'
    PORTA_PROCESSAMENTO = 65432
    STATUS_USUARIO = 1
    NOME_USUARIO = input("Digite seu nome de usuário: ")
    msg_retorno = ''

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((IP_PROCESSAMENTO, PORTA_PROCESSAMENTO))
            msg = {"operation": 0, "username": NOME_USUARIO}   #Apenas para informar o nome do usuário ao servidor de processamento
            msg_json = json.dumps(msg)  #Convert to JSON string
            s.sendall(f"{msg_json}".encode('utf-8'))
            resultado = s.recv(4096).decode('utf-8')   #Essa resposta deve conter a confirmação de conexão e o status inicial do usuário
            
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
        op_str = input(f"\n1 - Mudar status para {'Inativo' if STATUS_USUARIO == 1 else 'Ativo'}\n2 - Iniciar conversa\n3 - Encerrar aplicação\n4 - Visualizar mensagens recebidas\nEscolha uma opção: ").strip()
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
            
        elif op == 2:  #Se quiser começar uma conversa, vai precisar ver lista de usuarios ativos
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((IP_PROCESSAMENTO, PORTA_PROCESSAMENTO))
                    msg = {"operation": -1, "username": NOME_USUARIO}   #Apenas para requisitar a lista e usuários ativos ao servidor
                    msg_json = json.dumps(msg)  #Convert to JSON string
                    s.sendall(f"{msg_json}".encode('utf-8'))
                    
                    resultado = s.recv(4096).decode('utf-8')   #Essa resposta deve conter a lista de usuários ativos
                    id_user = input(f"{resultado}\nDigite o identificador de um usuário para iniciar a conversa: ")
                    data = input(f"Agora digite a mensagem: ")
            except Exception as e:
                msg_retorno += f"Erro ao contactar servidor de processamento: {e}"
        
        elif op == 4:  #Se quiser visualizar mensagens recebidas, não precisa de comunicação com o servidor, só precisa ler o conteúdo do arquivo local onde as mensagens recebidas são armazenadas
            try:
                with open(f"{NOME_USUARIO}_messages.txt", "r") as f:
                    data = f.read()
            except Exception as e:
                msg_retorno += f"Erro ao ler mensagens recebidas: {e}"
            continue  #Não precisa enviar nada ao servidor de processamento, só ler o arquivo local e mostrar para o usuário

        msg_data = {"to": id_user, "data": data}
        msg_data_json = json.dumps(msg_data)  #Convert to JSON string
        msg = {"operation": op, "username": NOME_USUARIO, "status": status, "body": msg_data_json}
        msg_json = json.dumps(msg)  #Convert to JSON string
        msg_retorno += f"Mensagem enviada (em JSON): {msg_json}\n"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((IP_PROCESSAMENTO, PORTA_PROCESSAMENTO))
                #s.sendall(f"{arquivo};{palavra}".encode('utf-8'))
                s.sendall(f"{msg_json}".encode('utf-8'))

                resultado = s.recv(4096).decode('utf-8')
                msg_retorno += resultado
                
                if op == 3: break

        except Exception as e:
            msg_retorno += f"Erro ao contactar servidor de processamento: {e}"
    
    print("\nObrigado por usar a aplicação!")

if __name__ == "__main__":
    main()