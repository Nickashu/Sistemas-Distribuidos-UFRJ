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
    # Este arquivo ficou só com a orquestração de inicialização e escolha do modo.
    print("--- A PALAVRA INFILTRADA ---")
    nome_jogador = input("Escolha seu codinome: ").strip()
    while not nome_jogador:
        nome_jogador = input("Escolha um codinome: ").strip()

    modo_rede = input("Rodar em rede local com eleição distribuída? [s/N]: ").strip().lower()
    usar_lan = (modo_rede == 's' or modo_rede == 'sim')
    host_jogo = HOST_LOCAL
    servidor_lan = False
    meu_ip_lan = HOST_LOCAL
    ips_participantes_lan = []

    if usar_lan:
        # No modo LAN, cada máquina informa seu IP e a lista completa de participantes.
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
        # No modo local, a eleição usa portas diferentes nesta mesma máquina.
        for porta in PORTAS_BULLY:
            try:
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
            print("Limite máximo de 5 jogadores locais atingido.")
            sys.exit()

        threading.Thread(target=responder_pings_bully, args=(meu_socket_bully,), daemon=True).start()
    else:
        # No modo LAN, o socket de presença fica em uma porta fixa para todos os nós.
        meu_socket_bully = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        meu_socket_bully.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        meu_socket_bully.bind((HOST_LAN, PORTA_BULLY_LAN))
        meu_socket_bully.listen()
        threading.Thread(target=responder_pings_bully, args=(meu_socket_bully,), daemon=True).start()

    fila_de_teclado = queue.Queue()
    threading.Thread(target=capturar_teclado, args=(fila_de_teclado,), daemon=True).start()

    servidor_ativo = False
    
    while True:
        if usar_lan:
            # Descobre quem é o líder da rodada entre as máquinas da rede.
            host_jogo = executar_eleicao_bully_lan(meu_ip_lan, ips_participantes_lan)
            sou_lider = (host_jogo == meu_ip_lan)
            if sou_lider and not servidor_ativo:
                cerebro = ServidorCerebro(host_bind=HOST_LAN)
                threading.Thread(target=cerebro.iniciar, daemon=True).start()
                servidor_ativo = True
                time.sleep(1)
        else:
            # Mantém o comportamento antigo de eleição local por portas.
            host_jogo = HOST_LOCAL
            sou_lider = executar_eleicao_bully(meu_id, HOST_LOCAL)
            
            if sou_lider and not servidor_ativo:
                cerebro = ServidorCerebro(host_bind=HOST_LOCAL)
                threading.Thread(target=cerebro.iniciar, daemon=True).start()
                servidor_ativo = True
                time.sleep(1) 
            
        jogador = ClienteJogador(fila_de_teclado)
        jogador.conectar(nome_jogador, is_cerebro=sou_lider, host_jogo=host_jogo)
        
        if jogador.rejeitado:
            sys.exit()
            
        if jogador.queda_silenciosa:
            try:
                jogador.socket.close()
            except:
                pass
            servidor_ativo = False
            time.sleep(1) 
            continue