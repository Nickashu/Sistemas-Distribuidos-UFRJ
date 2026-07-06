import ipaddress
import socket
import threading
import time

HOST_LOCAL = '127.0.0.1'
HOST_LAN = '0.0.0.0'
PORTA_JOGO = 5555
PORTA_BULLY_LAN = 5556
PORTA_DISCOVERY = 5557
PORTAS_BULLY = [5001, 5002, 5003, 5004, 5005]
BUFFER = 1024

#Método para enviar mensagens para o socket, garantindo que a mensagem termine com uma quebra de linha única:
def enviar_msg(sock, texto):
    msg_completa = texto.strip() + "\n"
    sock.sendall(msg_completa.encode('utf-8'))


class LeitorSocket:
    def __init__(self, sock):
        self.sock = sock
        self.buffer = ""

    #Lê uma mensagem completa do socket, retornando None se a conexão for encerrada:
    def ler_mensagem(self):
        while "\n" not in self.buffer:
            try:
                dados = self.sock.recv(BUFFER).decode('utf-8')
                if not dados:
                    return None
                self.buffer += dados
            except socket.timeout:
                return ""
            except:
                return None
        msg, self.buffer = self.buffer.split("\n", 1)  #Remove a primeira linha (mensagem completa) do buffer
        return msg.strip()

    #Permite iterar sobre as mensagens recebidas do socket, retornando cada mensagem completa:
    def ler_mensagens_iter(self):
        while True:
            msg = self.ler_mensagem()
            if msg is None:
                break
            yield msg  #yield permite que a função seja usada como um gerador, retornando mensagens uma a uma


#Pares de palavras para o jogo: a primeira vai para os inocentes, a segunda para o infiltrado
PARES_DE_PALAVRAS = [
    ("Praia", "Piscina"),
    ("Cachorro", "Lobo"),
    ("Violão", "Baixo"),
    ("Avião", "Helicóptero"),
    ("Computador", "Celular"),
    ("Livro", "Caderno"),
    ("Café", "Chá"),
    ("Futebol", "Basquete"),
    ("Carro", "Moto"),
    ("Sol", "Lua"),
    ("Cinema", "Teatro"),
    ("Maçã", "Pêra"),
    ("Gato", "Tigre"),
    ("Chuva", "Neve"),
    ("Piano", "Teclado"),
    ("Relógio", "Cronômetro"),
    ("Pizza", "Hambúrguer"),
]


def responder_pings_bully(meu_socket):
    #Mantém o socket de presença aberto para que outros nós descubram este processo:
    while True:
        try:
            conn, _ = meu_socket.accept()
            conn.close()
        except:
            break


def executar_eleicao_bully(meu_id, host_jogo):
    #No modo local, o processo com a maior porta disponível assume o papel de líder:
    try:
        teste_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        teste_conn.settimeout(0.5)
        teste_conn.connect((host_jogo, PORTA_JOGO))
        teste_conn.close()
        return False  #Se já existe um servidor ativo, não é necessário eleger outro, e o processo atual entra como cliente
    except:
        pass

    print(f"[BULLY] Identidade local {meu_id}. Varrendo IDs maiores...")
    alguem_maior_vivo = False

    for porta_alvo in range(meu_id + 1, PORTAS_BULLY[-1] + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect((HOST_LOCAL, porta_alvo))
            alguem_maior_vivo = True
            s.close()
            break
        except:
            pass

    if not alguem_maior_vivo:
        return True   #Nesse caso, o processo atual é o maior ID vivo e assume o papel de líder
    else:
        print(f"[BULLY] Nó superior ativo. Aguardando servidor...")
        time.sleep(2)
        return False   #Nesse caso, o processo atual aguarda que o nó superior assuma o papel de líder e entre como cliente


def normalizar_lista_ips(texto_ips):
    #Remove espaços, valida IPs e devolve a lista ordenada sem repetição:
    ips = []
    for item in texto_ips.split(","):
        item = item.strip()
        if not item:
            continue
        ips.append(str(ipaddress.ip_address(item)))  #Valida o IP e converte para string

    ips_unicos = []
    for ip in ips:
        if ip not in ips_unicos:
            ips_unicos.append(ip)

    ips_unicos.sort(key=lambda valor: ipaddress.ip_address(valor))  #Ordena a lista de IPs em ordem crescente
    return ips_unicos


def iniciar_discovery_lan(meu_ip):
    #Inicia uma thread contínua que anuncia presença e coleta IPs de outros jogadores via UDP broadcast:
    ips_encontrados = {meu_ip}
    ips_lock = threading.Lock()

    def _loop_discovery():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', PORTA_DISCOVERY))
        sock.settimeout(0.5)

        while True:
            sock.sendto(meu_ip.encode(), ('255.255.255.255', PORTA_DISCOVERY))
            try:
                dados, _ = sock.recvfrom(256)
                ip = dados.decode().strip()
                if ip:
                    with ips_lock:
                        ips_encontrados.add(ip)
            except socket.timeout:
                pass

    threading.Thread(target=_loop_discovery, daemon=True).start()
    return ips_encontrados, ips_lock


def executar_eleicao_bully_lan(meu_ip, ips_participantes):
    #Verifica se já existe um cérebro (servidor de jogo) rodando na rede:
    for ip_alvo in ips_participantes:
        try:
            teste_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            teste_conn.settimeout(0.5)
            teste_conn.connect((ip_alvo, PORTA_JOGO))
            teste_conn.close()
            return ip_alvo
        except:
            continue

    #Se não houver servidor ativo, o maior IP vivo assume:
    ips_ordenados = sorted(ips_participantes, key=lambda valor: ipaddress.ip_address(valor), reverse=True)  #Ordena a lista de IPs em ordem decrescente

    #Tenta se conectar a cada IP da lista, do maior para o menor, para verificar se algum está ativo:
    for ip_alvo in ips_ordenados:
        try:
            teste_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            teste_conn.settimeout(0.5)
            teste_conn.connect((ip_alvo, PORTA_BULLY_LAN))
            teste_conn.close()
            return ip_alvo
        except:
            continue

    return meu_ip
