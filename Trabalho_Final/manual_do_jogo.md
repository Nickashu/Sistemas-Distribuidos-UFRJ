# Guia do Usuário e Fluxo de Jogo: "Palavra Infiltrada"

Este manual descreve a mecânica de jogo, as regras, os comandos de terminal e o fluxo passo a passo de uma partida de **Palavra Infiltrada**.

---

## 1. O Conceito do Jogo

**Palavra Infiltrada** é um jogo distribuído de dedução social e blefe (fortemente inspirado no jogo de tabuleiro *Undercover*). 

A partida exige um número mínimo de jogadores e divide os participantes em dois papéis secretos:
*   **Inocentes (Maioria)**: Recebem uma palavra secreta em comum (ex: `Praia`).
*   **Infiltrado (Um jogador)**: Recebe uma palavra secreta diferente, mas muito parecida com a dos inocentes (ex: `Piscina`).

Ninguém sabe qual é o papel ou a palavra dos outros. O objetivo dos **Inocentes** é descobrir e eliminar o **Infiltrado**. O objetivo do **Infiltrado** é passar despercebido, misturando-se com os inocentes e tentando fazê-los eliminar um jogador inocente por engano.

---

## 2. O Fluxo de uma Rodada (Passo a Passo)

Uma partida completa segue uma máquina de estados rígida dividida em 6 fases sequenciais:

```
[ Fase 1: Lobby ] ──➔ [ Fase 2: Distribuição ] ──➔ [ Fase 3: Dicas ]
                                                          │
[ Fase 6: Pontuação ] ◀── [ Fase 5: Votação ] ◀── [ Fase 4: Chat ]
```

### Fase 1: O Lobby
*   Os jogadores executam o programa no terminal e escolhem seus apelidos.
*   Ao entrarem na partida, ficam em uma sala de bate-papo livre (Lobby) aguardando outros participantes.
*   **Como iniciar**: Quando houver pelo menos 3 jogadores conectados, o **Host** (o primeiro a ter se conectado na sala) inicia a partida digitando:
    ```
    /start
    ```

### Fase 2: Distribuição de Papéis e Palavras (Secreto)
*   O servidor sorteia os papéis em segundo plano.
*   Cada jogador recebe privadamente em seu terminal sua palavra secreta e papel.
*   *Exemplo de tela para um Inocente*:
    ```
    SEU PAPEL: INOCENTE | SUA PALAVRA: Praia
    ```
*   *Exemplo de tela para o Infiltrado*:
    ```
    SEU PAPEL: INFILTRADO | SUA PALAVRA: Piscina
    ```

### Fase 3: Fase de Dicas
*   O terminal de todos os jogadores exibe o comando: `Rodada começou! Digite /dica [palavra]`.
*   Cada jogador deve enviar **uma palavra (dica)** relacionada à palavra que recebeu, sem revelar o termo em si.
*   *Exemplo*: Se sua palavra for `Praia`, você pode mandar `/dica sol`. Se for `Piscina`, pode mandar `/dica cloro`.
*   **Envio**:
    ```
    /dica sol
    ```
*   O jogo aguarda até que **todos** os jogadores conectados enviem suas respectivas dicas.

### Fase 4: Fase de Chat (Discussão e Blefe)
*   O servidor compila todas as dicas e faz um multicast para os terminais.
*   *Exemplo de exibição*:
    ```
    --- DICAS DO GRUPO ---
      - Alice disse: 'sol'
      - Bob disse: 'cloro'
      - Carlos disse: 'areia'
    ```
*   O chat é aberto para debate. Os jogadores devem discutir baseando-se nas dicas para tentar identificar quem deu uma dica suspeita (provando que recebeu a palavra infiltrada).
*   **Acelerar Votação (Barreira de Sincronização)**: Se o debate estiver morno e os jogadores já tiverem certeza de quem acusar, qualquer jogador pode digitar `/votar` para pedir para avançar. Quando **todos** os jogadores ativos digitarem `/votar`, o chat é instantaneamente encerrado e a votação começa.

### Fase 5: Votação Final (Secreta)
*   O chat livre é bloqueado. O terminal exibe a instrução para votar.
*   Cada jogador deve digitar no terminal o voto contra o jogador suspeito:
    ```
    /voto Bob
    ```
*   O voto é secreto e enviado diretamente ao servidor. O servidor notifica o grupo em tempo real sobre quem já votou (ex: `[SISTEMA] Alice votou!`), mas não revela em quem foi o voto.

### Fase 6: Veredito e Atualização de Pontos
Assim que o último voto é recebido, o servidor fecha a rodada, faz a apuração e distribui a pontuação:
1.  **Caso 1: Eliminação do Infiltrado**
    *   Se a maioria dos votos foi no Infiltrado, ele é eliminado.
    *   **Pontuação**: Cada Inocente ganha **1 ponto**.
2.  **Caso 2: Acusação Errada (Inocente eliminado)**
    *   Se a maioria dos votos foi em um Inocente, o Infiltrado vence.
    *   **Pontuação**: O Infiltrado ganha **2 pontos**.
3.  **Caso 3: Empate de Votos**
    *   Empates favorecem o Infiltrado, pois não há consenso.
    *   **Pontuação**: O Infiltrado ganha **2 pontos**.

O servidor exibe o placar atualizado no terminal de todos e reabre o Lobby. O Host pode digitar `/start` para iniciar uma nova rodada (novos papéis e novas palavras serão gerados).

---

## 3. Guia Rápido de Comandos

Aqui estão todos os comandos que você pode digitar diretamente no terminal durante a execução:

| Comando | Onde usar? | O que faz? |
| :--- | :--- | :--- |
| **`/start`** | Lobby | Inicia a partida (privilégio exclusivo do Host). |
| **`/dica <palavra>`** | Fase de Dicas | Envia sua dica relacionada à palavra secreta recebida. |
| **`/votar`** | Fase de Chat | Pede para encerrar o debate e ir direto para a votação. |
| **`/voto <apelido>`** | Fase de Votação | Vota no jogador que você suspeita ser o infiltrado. |
| **`/placar`** | Lobby | Solicita ao servidor e imprime a pontuação atual de todos. |
| *(Texto livre)* | Lobby e Chat | Envia uma mensagem comum de chat para todos lerem. |
