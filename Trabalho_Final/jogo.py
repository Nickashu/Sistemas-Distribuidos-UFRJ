import socket
import threading
import time
import sys
import queue 
from game_core import ClienteJogador, ServidorCerebro, capturar_teclado
from rede import (
    HOST_LAN,
    HOST_LOCAL,
    PORTA_BULLY_LAN,
    PORTAS_BULLY,
    executar_eleicao_bully,
    executar_eleicao_bully_lan,
    normalizar_lista_ips,
    responder_pings_bully,
)

#INÍCIO DO PROGRAMA
if __name__ == "__main__":
    print("--- PALAVRA INFILTRADA ---")
    nome_jogador = input("Escolha seu apelido: ").strip()
    while not nome_jogador:
        nome_jogador = input("Escolha um apelido: ").strip()

    modo_rede = input("Rodar em rede local com eleição distribuída? [s/n]: ").strip().lower()
    usar_lan = (modo_rede == 's' or modo_rede == 'sim')
    host_jogo = HOST_LOCAL
    servidor_lan = False
    meu_ip_lan = HOST_LOCAL
    ips_participantes_lan = []

    if usar_lan:
        #No modo LAN, cada máquina informa seu IP e a lista completa de participantes:
        meu_ip_lan = input("IP desta máquina na rede local: ").strip()
        while not meu_ip_lan:
            meu_ip_lan = input("IP desta máquina na rede local: ").strip()

        ips_texto = input("IPs participantes, separados por vírgula, incluindo o seu: ").strip()
        while not ips_texto:
            ips_texto = input("IPs participantes, separados por vírgula, incluindo o seu: ").strip()

        ips_participantes_lan = normalizar_lista_ips(ips_texto)
        if meu_ip_lan not in ips_participantes_lan:
            ips_participantes_lan.append(meu_ip_lan)
            ips_participantes_lan = normalizar_lista_ips(",".join(ips_participantes_lan))
    
    meu_id = 0
    meu_socket_bully = None

    if not usar_lan:
        #No modo local, a eleição usa portas diferentes numa mesma máquina:
        for porta in PORTAS_BULLY:
            try:
                #Tenta criar um socket na porta atual. Se conseguir, define meu_id e meu_socket_bully:
                tentativa_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tentativa_socket.bind((HOST_LOCAL, porta))
                tentativa_socket.listen()
                meu_id = porta
                meu_socket_bully = tentativa_socket
                break
            except OSError:
                tentativa_socket.close()
                continue
            
        if meu_id == 0:
            print("Limite máximo de jogadores locais atingido.")  #Todas as portas já estão em uso
            sys.exit()

        threading.Thread(target=responder_pings_bully, args=(meu_socket_bully,), daemon=True).start()
    else:
        #No modo LAN, o socket de presença fica em uma porta fixa para todos os nós:
        meu_socket_bully = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        meu_socket_bully.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) #Aqui, o SO_REUSEADDR permite que o socket seja reutilizado rapidamente após ser fechado, evitando erros de "Address already in use" ao reiniciar o programa
        meu_socket_bully.bind((HOST_LAN, PORTA_BULLY_LAN))   #O socket é vinculado a uma porta fixa para todos os nós na rede local, permitindo que eles se comuniquem e realizem a eleição distribuída
        meu_socket_bully.listen()
        threading.Thread(target=responder_pings_bully, args=(meu_socket_bully,), daemon=True).start()

    #Fila de teclado para capturar entradas do jogador (será uma thread separada para cada jogador que lê o teclado e coloca as entradas na fila):
    fila_de_teclado = queue.Queue()
    threading.Thread(target=capturar_teclado, args=(fila_de_teclado,), daemon=True).start()

    servidor_ativo = False
    
    while True:
        #Fazendo a eleição do líder (cérebro) do jogo, em LAN ou local:
        if usar_lan:
            #Descobre quem é o líder da rodada entre as máquinas da rede (se tiver um):
            host_jogo = executar_eleicao_bully_lan(meu_ip_lan, ips_participantes_lan)
            sou_lider = (host_jogo == meu_ip_lan)
            if sou_lider and not servidor_ativo:
                cerebro = ServidorCerebro(host_bind=HOST_LAN)
                threading.Thread(target=cerebro.iniciar, daemon=True).start()   #Mantém o servidor ativo enquanto o nó for o líder
                servidor_ativo = True
                time.sleep(1)
        else:
            #Eleição local usando as portas:
            host_jogo = HOST_LOCAL
            sou_lider = executar_eleicao_bully(meu_id, HOST_LOCAL)
            
            if sou_lider and not servidor_ativo:
                cerebro = ServidorCerebro(host_bind=HOST_LOCAL)
                threading.Thread(target=cerebro.iniciar, daemon=True).start()  #Mantém o servidor ativo enquanto o nó for o líder
                servidor_ativo = True
                time.sleep(1)
            
        jogador = ClienteJogador(fila_de_teclado)  #Indepentente de ser o cérebro ou não, cada nó cria um cliente para se conectar ao servidor do jogo
        jogador.conectar(nome_jogador, is_cerebro=sou_lider, host_jogo=host_jogo)  #Essa chamada é bloqueante
        
        if jogador.rejeitado:   #Entra nesse if se o jogador foi rejeitado pelo servidor (por exemplo, se o nome já estiver em uso):
            sys.exit()
            
        if jogador.queda_silenciosa:   #Entra nesse if se o jogador foi desconectado silenciosamente
            try:
                jogador.socket.close()
            except:
                pass
            servidor_ativo = False
            time.sleep(1) 
            continue