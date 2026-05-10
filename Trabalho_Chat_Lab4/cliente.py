import socket
import json
import os

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear') # 'nt' is for Windows, 'posix' is for Linux/macOS

def main():
    # IP do Servidor
    IP_PROCESSAMENTO = 'xxx.xxx.x.xx'
    PORTA_PROCESSAMENTO = 65432
    status = 1
    msg_retorno = ''

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((IP_PROCESSAMENTO, PORTA_PROCESSAMENTO))
        msg_retorno = "Conectado ao servidor de processamento!"
    except Exception as e:
        print(f"Erro ao conectar ao servidor de processamento: {e}")
        return

    while True:
        clear_terminal()
        if len(msg_retorno) > 0:
            print(f"{msg_retorno}\n\n")
            msg_retorno = ''
        print("======APLICAÇÃO DE CHAT======")
        print(f"Status: {'Ativo' if status == 1 else 'Inativo'}")
        op_str = input(f"\n1 - Mudar status para {'Inativo' if status == 1 else 'Ativo'}\n2 - Iniciar conversa\n3 - Visualizar mensagens recebidas\n4 - Encerrar aplicação\nEscolha uma opção: ").strip()
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
        
        if op == 1:
            status = 1 if status == 0 else 0
            msg_retorno += "Status alterado com sucesso!"
        elif op == 2:  #Se quiser começar uma conversa, vai precisar ver lista de usuarios ativos
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((IP_PROCESSAMENTO, PORTA_PROCESSAMENTO))
                    msg = {"operation": -1, "body": {}}   #Apenas para requisitar a lista e usuários ativos ao servidor
                    msg_json = json.dumps(data)  #Convert to JSON string
                    s.sendall(f"{msg_json}".encode('utf-8'))
                    
                    resultado = s.recv(4096).decode('utf-8')
                    id_user = input(f"{resultado}\nDigite o identificador de um usuário para iniciar a conversa: ")
                    data = input(f"Agora digite a mensagem: ")
            except Exception as e:
                print(f"Erro ao contactar servidor de processamento: {e}")

        msg_data = {"to": id_user, "data": data}
        msg_data_json = json.dumps(msg_data)  #Convert to JSON string
        msg = {"operation": op, "body": msg_data_json}
        msg_json = json.dumps(msg)  #Convert to JSON string
        msg_retorno += f"Mensagem enviada (em JSON): {json_string}\n"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((IP_PROCESSAMENTO, PORTA_PROCESSAMENTO))
                #s.sendall(f"{arquivo};{palavra}".encode('utf-8'))
                s.sendall(f"{msg_json}".encode('utf-8'))

                resultado = s.recv(4096).decode('utf-8')
                msg_retorno += resultado

        except Exception as e:
            print(f"Erro ao contactar servidor de processamento: {e}")
        
        if op == 5: break
    
    print("\nObrigado por usar a aplicação!")

if __name__ == "__main__":
    main()