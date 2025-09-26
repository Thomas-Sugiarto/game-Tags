
import socket
import threading
import pickle
import random
import time
import traceback


HOST = '0.0.0.0'
PORT = 5555
MAX_PLAYERS = 3
SERVER_TICK_RATE = 30
GAME_DURATION = 180  
ARENA_WIDTH = 800
ARENA_HEIGHT = 600
PLAYER_RADIUS = 25
ITEM_RADIUS = 15
PLAYER_SPEED = 4
TAG_IMMUNITY_DURATION = 3  

ITEM_TYPES = ['speed_boost', 'banana_trap']
MAX_ITEMS = 5
ITEM_SPAWN_INTERVAL = 5
ITEM_EFFECT_DURATION = {'speed_boost': 5, 'stun': 2}
BANANA_ARM_TIME = 0.5
game_state = {
    'players': {},
    'items': [],
    'game_started': False,
    'game_time': GAME_DURATION,
    'winner': None,
    'game_over_timer': 0
}
static_player_data = {}
player_inputs = {}
clients = {}
lock = threading.Lock()
last_item_spawn_time = time.time()
last_score_update_time = time.time()
game_start_time = 0


def distance(p1, p2):
    return ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
def send_to_client(conn, data):
    try:
        payload = pickle.dumps(data)
        message = f"{len(payload):<10}".encode() + payload
        conn.sendall(message)
    except (ConnectionResetError, BrokenPipeError):
        pass
def broadcast(data):
    with lock:
        for pid, conn in list(clients.items()):
            send_to_client(conn, data)


def receive_from_client(conn):
    try:
        header_size = 10
        header_data = b''
        while len(header_data) < header_size:
            chunk = conn.recv(header_size - len(header_data))
            if not chunk: return None
            header_data += chunk

        msglen = int(header_data.decode())

        full_msg = b''
        while len(full_msg) < msglen:
            chunk = conn.recv(min(msglen - len(full_msg), 4096))
            if not chunk: return None
            full_msg += chunk

        return pickle.loads(full_msg)
    except (ValueError, pickle.UnpicklingError, ConnectionResetError, EOFError):
        return None


def handle_client(conn, player_id):
    global player_inputs
    print(f"[Koneksi] Pemain {player_id} mencoba terhubung...")

    try:
        send_to_client(conn, {'type': 'your_id', 'id': player_id})
        send_to_client(conn, {'type': 'all_players_data', 'data': static_player_data})
        player_info = receive_from_client(conn)
        if player_info is None:
            raise ConnectionAbortedError("Gagal menerima info pemain awal.")

        with lock:
            static_player_data[player_id] = player_info
            game_state['players'][player_id]['username'] = player_info['username']

        print(f"[Koneksi] Pemain {player_id} ({player_info['username']}) berhasil bergabung.")

        broadcast({'type': 'new_player', 'id': player_id, 'data': player_info})

        while True:
            inputs = receive_from_client(conn)
            if inputs is None:
                break  
            with lock:
                player_inputs[player_id] = inputs

    except (ConnectionAbortedError, ConnectionResetError) as e:
        print(f"[Error] Koneksi dengan pemain {player_id} ditutup: {e}")
    finally:
        print(f"[Koneksi] Pemain {player_id} terputus.")
        with lock:
            if player_id in game_state['players']:
                is_it_player = game_state['players'][player_id].get('is_it', False)
                del game_state['players'][player_id]
                if is_it_player and game_state['players']:
                    remaining = list(game_state['players'].keys())
                    if remaining:
                        new_it_id = random.choice(remaining)
                        game_state['players'][new_it_id]['is_it'] = True
                        print(f"[Game] {game_state['players'][new_it_id]['username']} sekarang 'It'.")

            if player_id in player_inputs: del player_inputs[player_id]
            if player_id in clients: del clients[player_id]
            if player_id in static_player_data: del static_player_data[player_id]

        broadcast({'type': 'player_left', 'id': player_id})
        conn.close()


def reset_game():
    global game_start_time, last_item_spawn_time, last_score_update_time
    game_state['game_started'] = False
    game_state['items'] = []
    game_state['winner'] = None
    game_state['game_time'] = GAME_DURATION

    for pid, player in game_state['players'].items():
        player['pos'] = [random.randint(50, 750), random.randint(50, 550)]
        player['is_it'] = False
        player['inventory'] = None
        player['speed'] = PLAYER_SPEED
        player['effect_timer'] = 0
        player['stunned'] = False
        player['score'] = 0
        player['immunity_timer'] = 0 

    game_start_time = 0
    last_item_spawn_time = time.time()
    last_score_update_time = time.time()
    print("[Game] Game direset, kembali ke lobi.")


def game_logic_loop():
    global game_state, last_item_spawn_time, last_score_update_time, game_start_time

    while True:
        try:
            start_time = time.time()
            tick_delta = 1 / SERVER_TICK_RATE

            with lock:
                if game_state.get('game_over_timer', 0) > 0:
                    game_state['game_over_timer'] -= tick_delta
                    if game_state['game_over_timer'] <= 0:
                        reset_game()
                        continue

                if not game_state['game_started'] and len(game_state['players']) == MAX_PLAYERS and not game_state.get('winner'):
                    game_state['game_started'] = True
                    game_start_time = time.time()
                    last_score_update_time = game_start_time
                    it_player_id = random.choice(list(game_state['players'].keys()))
                    game_state['players'][it_player_id]['is_it'] = True
                    game_state['players'][it_player_id]['immunity_timer'] = TAG_IMMUNITY_DURATION
                    print(f"[Game] Game dimulai! {game_state['players'][it_player_id]['username']} adalah 'It'.")

                if game_state['game_started']:
                    elapsed_time = time.time() - game_start_time
                    game_state['game_time'] = max(0, GAME_DURATION - elapsed_time)

                    if game_state['game_time'] <= 0:
                        game_state['game_started'] = False
                        winner = None
                        highest_score = -1
                        for pdata in game_state['players'].values():
                            if not pdata.get('is_it', False) and pdata['score'] > highest_score:
                                highest_score = pdata['score']
                                winner = pdata['username']
                        if not winner:
                            sorted_players = sorted(game_state['players'].values(), key=lambda p: p['score'], reverse=True)
                            if sorted_players:
                                winner = sorted_players[0]['username']
                        game_state['winner'] = winner
                        game_state['game_over_timer'] = 10
                        print(f"[Game] Game Selesai! Pemenangnya adalah {winner}")
                        continue

                    if time.time() - last_score_update_time > 1:
                        for pid, player in game_state['players'].items():
                            if not player.get('is_it', False):
                                player['score'] += 1
                        last_score_update_time = time.time()

                    it_player_data = None
                    it_player_id = None

                    players_copy = list(game_state['players'].items())
                    for pid, player in players_copy:
                        if pid not in game_state['players']: continue

                        if player.get('is_it', False):
                            it_player_data = player
                            it_player_id = pid

                        if player['effect_timer'] > 0:
                            player['effect_timer'] -= tick_delta
                        else:
                            player['speed'] = PLAYER_SPEED
                            player['stunned'] = False

                        if player['immunity_timer'] > 0:
                            player['immunity_timer'] -= tick_delta

                        if player['stunned']: continue

                        inputs = player_inputs.get(pid, {})
                        move_x, move_y = inputs.get('move_x', 0), inputs.get('move_y', 0)

                        player['pos'][0] += move_x * player['speed']
                        player['pos'][1] += move_y * player['speed']
                        player['pos'][0] = max(PLAYER_RADIUS, min(player['pos'][0], ARENA_WIDTH - PLAYER_RADIUS))
                        player['pos'][1] = max(PLAYER_RADIUS, min(player['pos'][1], ARENA_HEIGHT - PLAYER_RADIUS))

                        if inputs.get('use_item') and player['inventory']:
                            item_type = player['inventory']
                            player['inventory'] = None

                            if item_type == 'speed_boost':
                                player['speed'] = PLAYER_SPEED * 1.8
                                player['effect_timer'] = ITEM_EFFECT_DURATION['speed_boost']
                            elif item_type == 'banana_trap':
                                game_state['items'].append({
                                    'type': 'banana_peel', 'pos': list(player['pos']),
                                    'id': time.time(), 'spawn_time': time.time()
                                })

                    if it_player_data and it_player_id in game_state['players'] and not it_player_data.get('stunned', False):
                        for pid_other, pdata_other in game_state['players'].items():
                            if pid_other != it_player_id and pdata_other.get('immunity_timer', 0) <= 0:
                                if distance(it_player_data['pos'], pdata_other['pos']) < PLAYER_RADIUS * 2:
                                    print(f"[Game] TAG! {it_player_data['username']} menyentuh {pdata_other['username']}.")
                                    game_state['players'][it_player_id]['is_it'] = False
                                    game_state['players'][pid_other]['is_it'] = True

                                    game_state['players'][it_player_id]['immunity_timer'] = TAG_IMMUNITY_DURATION
                                    game_state['players'][pid_other]['immunity_timer'] = TAG_IMMUNITY_DURATION

                                    game_state['players'][it_player_id]['score'] += 5
                                    break

                    items_to_remove = []
                    for item in list(game_state['items']):
                        for pid, pdata in list(game_state['players'].items()):
                            if distance(pdata['pos'], item['pos']) < PLAYER_RADIUS + ITEM_RADIUS:
                                if item['type'] in ITEM_TYPES and not pdata['inventory']:
                                    pdata['inventory'] = item['type']
                                    items_to_remove.append(item)
                                    break
                                elif item['type'] == 'banana_peel' and time.time() - item.get('spawn_time', 0) > BANANA_ARM_TIME:
                                    if not pdata.get('is_it', False):
                                        pdata['stunned'] = True
                                        pdata['effect_timer'] = ITEM_EFFECT_DURATION['stun']
                                        items_to_remove.append(item)
                                        break

                    game_state['items'] = [item for item in game_state['items'] if item not in items_to_remove]

                    if time.time() - last_item_spawn_time > ITEM_SPAWN_INTERVAL and len(game_state['items']) < MAX_ITEMS:
                        item_type = random.choice(ITEM_TYPES)
                        pos = [random.randint(ITEM_RADIUS, ARENA_WIDTH - ITEM_RADIUS), random.randint(ITEM_RADIUS, ARENA_HEIGHT - ITEM_RADIUS)]
                        game_state['items'].append({'type': item_type, 'pos': pos, 'id': time.time()})
                        last_item_spawn_time = time.time()
            
            if clients:
                broadcast({'type': 'game_update', 'state': game_state})


            elapsed_time = time.time() - start_time
            sleep_time = (1 / SERVER_TICK_RATE) - elapsed_time
            if sleep_time > 0: time.sleep(sleep_time)

        except Exception:
            print(f"!!--- ERROR FATAL DI GAME LOOP SERVER ---!!")
            traceback.print_exc()
            print(f"!!---------------------------------------!!")


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(MAX_PLAYERS)
    print(f"[Server] Server berjalan di {HOST}:{PORT}, menunggu {MAX_PLAYERS} pemain...")

    logic_thread = threading.Thread(target=game_logic_loop, daemon=True)
    logic_thread.start()

    player_id_counter = 0
    while True:
        conn, addr = server.accept()

        if len(clients) >= MAX_PLAYERS:
            print(f"[Server] Menolak koneksi dari {addr}, server penuh.")
            try:
                send_to_client(conn, {'type': 'error', 'message': 'Server penuh'})
            except:
                pass
            conn.close()
            continue

        with lock:
            clients[player_id_counter] = conn
            start_pos = [random.randint(50, 750), random.randint(50, 550)]
            game_state['players'][player_id_counter] = {
                'pos': start_pos, 'username': '...',
                'is_it': False, 'inventory': None, 'speed': PLAYER_SPEED,
                'effect_timer': 0, 'stunned': False, 'score': 0,
                'immunity_timer': 0
            }
            player_inputs[player_id_counter] = {}

        thread = threading.Thread(target=handle_client, args=(conn, player_id_counter))
        thread.start()
        player_id_counter += 1


if __name__ == "__main__":
    main()