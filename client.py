# client.py (Diperbaiki dengan input IP)
import pygame
import threading
import pickle
import os
import io
import cv2  # pip install opencv-python
import time
from network import Network
from server import PLAYER_SPEED, MAX_PLAYERS

# --- Konfigurasi Klien ---
# SERVER_IP DIHAPUS DARI SINI, AKAN DIINPUT OLEH PENGGUNA
SERVER_PORT = 5555
SCREEN_WIDTH, SCREEN_HEIGHT = 800, 600
FPS = 60
PLAYER_RADIUS = 25
ITEM_RADIUS = 15

# --- Warna ---
WHITE, BLACK, RED, BLUE, YELLOW, GRAY, GREEN = (255, 255, 255), (0, 0, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0), (150, 150, 150), (40, 150, 50)
TRANSPARENT_GRAY = (50, 50, 50, 180)

# --- Status Klien Global ---
latest_game_state = {}
running = True
lock = threading.Lock()
player_avatars = {}
my_player_id = -1
network = None

# --- Inisialisasi ---
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Tag Arena Multiplayer")
clock = pygame.time.Clock()
assets = {}
FONT_BOLD = None
FONT_REGULAR = None
FONT_LARGE = None

# --- Fungsi Aset ---

def crop_surface(surface):
    try:
        mask = pygame.mask.from_surface(surface)
        bounding_rect = mask.get_bounding_rects()
        if bounding_rect:
            crop_rect = bounding_rect[0]
            cropped_surface = pygame.Surface(crop_rect.size, pygame.SRCALPHA)
            cropped_surface.blit(surface, (0, 0), crop_rect)
            return cropped_surface
    except (pygame.error, IndexError) as e:
        print(f"Gagal meng-crop surface: {e}")
    return surface


def load_assets():
    global FONT_BOLD, FONT_REGULAR, FONT_LARGE
    try:
        font_path = os.path.join('assets', 'Poppins-Bold.ttf')
        FONT_BOLD = pygame.font.Font(font_path, 38)
        FONT_REGULAR = pygame.font.Font(font_path, 20)
        FONT_LARGE = pygame.font.Font(font_path, 52)
    except FileNotFoundError:
        print("Font Poppins-Bold.ttf tidak ditemukan di folder assets. Menggunakan font default.")
        FONT_BOLD = pygame.font.SysFont('Arial', 38, bold=True)
        FONT_REGULAR = pygame.font.SysFont('Arial', 20)
        FONT_LARGE = pygame.font.SysFont('Arial', 52, bold=True)

    asset_files = {
        'banana_trap': 'banana.png', 'speed_boost': 'speed_boost.png',
        'banana_peel': 'banana_peel.png', 'background': 'background.png',
        'avatar_placeholder': 'placeholder.png',
        'stun_stars': 'stun_stars.png', 'speed_aura': 'speed_aura.png'
    }
    for name, filename in asset_files.items():
        try:
            path = os.path.join('assets', filename)
            image = pygame.image.load(path).convert_alpha()
            if name != 'background':
                image = crop_surface(image)
            if name == 'background':
                assets[name] = pygame.transform.scale(image, (SCREEN_WIDTH, SCREEN_HEIGHT))
            elif name == 'speed_aura':
                assets[name] = pygame.transform.scale(image, (PLAYER_RADIUS * 3, PLAYER_RADIUS * 3))
            elif name in ['stun_stars']:
                assets[name] = image
            else:
                size = (ITEM_RADIUS * 2, ITEM_RADIUS * 2) if name not in ['avatar_placeholder'] else (PLAYER_RADIUS * 2, PLAYER_RADIUS * 2)
                assets[name] = pygame.transform.scale(image, size)
        except pygame.error:
            print(f"Gagal memuat aset: {filename}.")
            assets[name] = pygame.Surface((30, 30)); assets[name].fill(RED)


def create_circular_avatar(image_surface, size):
    if not image_surface: return None
    try:
        avatar = pygame.Surface((size, size), pygame.SRCALPHA)
        scaled_img = pygame.transform.scale(image_surface, (size, size))
        pygame.draw.circle(avatar, (255, 255, 255, 0), (size // 2, size // 2), size // 2)
        img_rect = scaled_img.get_rect(center=(size // 2, size // 2))
        avatar.blit(scaled_img, img_rect)
        mask_circle = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(mask_circle, (255, 255, 255, 255), (size // 2, size // 2), size // 2)
        avatar.blit(mask_circle, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return avatar
    except Exception as e:
        print(f"Gagal membuat avatar melingkar: {e}")
        return assets.get('avatar_placeholder')


def process_and_store_avatar(pid, pdata):
    if pdata and pdata.get('avatar_data'):
        try:
            img_bytes = io.BytesIO(pdata['avatar_data'])
            img_surface = pygame.image.load(img_bytes).convert_alpha()
            player_avatars[pid] = create_circular_avatar(img_surface, PLAYER_RADIUS * 2)
        except Exception as e:
            print(f"Gagal memuat avatar untuk pemain {pid}: {e}")
            player_avatars[pid] = create_circular_avatar(assets['avatar_placeholder'], PLAYER_RADIUS * 2)

# --- Fungsi Jaringan ---
def receive_data_from_server(network_handler):
    global latest_game_state, running, my_player_id
    while running:
        data_packet = network_handler.receive()
        if data_packet is None:
            print("Koneksi ke server terputus.")
            running = False
            break

        msg_type = data_packet.get('type')

        with lock:
            if msg_type == 'your_id':
                my_player_id = data_packet['id']
                print(f"Anda adalah Pemain {my_player_id}.")

            elif msg_type == 'all_players_data':
                for pid, pdata in data_packet.get('data', {}).items():
                    process_and_store_avatar(pid, pdata)
                    if 'players' not in latest_game_state:
                        latest_game_state['players'] = {}
                    if pid not in latest_game_state['players']:
                         latest_game_state['players'][pid] = {}
                    latest_game_state['players'][pid]['username'] = pdata.get('username', '...')

            elif msg_type == 'game_update':
                latest_game_state = data_packet['state']

            elif msg_type == 'new_player':
                pid = data_packet['id']
                pdata = data_packet['data']
                print(f"Pemain baru bergabung: {pdata.get('username', '')} ({pid})")
                process_and_store_avatar(pid, pdata)
                if pid not in latest_game_state.get('players', {}):
                    latest_game_state['players'][pid] = {'username': pdata.get('username')}

            elif msg_type == 'player_left':
                pid = data_packet['id']
                if pid in latest_game_state.get('players', {}):
                    print(f"Pemain {latest_game_state['players'][pid].get('username', '')} keluar.")
                    del latest_game_state['players'][pid]
                if pid in player_avatars:
                    del player_avatars[pid]


# --- Komponen UI ---
def draw_text(text, font, color, center_pos):
    render = font.render(text, True, color)
    rect = render.get_rect(center=center_pos)
    screen.blit(render, rect)

class InputBox:
    def __init__(self, x, y, w, h, text=''):
        self.rect = pygame.Rect(x, y, w, h)
        self.color = GRAY
        self.text = text
        self.txt_surface = FONT_REGULAR.render(text, True, self.color)
        self.active = False
    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_RETURN: return "enter"
            elif event.key == pygame.K_BACKSPACE: self.text = self.text[:-1]
            else: self.text += event.unicode
    def draw(self, screen):
        self.txt_surface = FONT_REGULAR.render(self.text, True, BLACK)
        pygame.draw.rect(screen, WHITE, self.rect)
        screen.blit(self.txt_surface, (self.rect.x + 10, self.rect.y + 10))
        pygame.draw.rect(screen, BLACK, self.rect, 2)

# --- Adegan Game ---
def main_menu():
    global running, network, my_player_id
    username_box = InputBox(SCREEN_WIDTH//2 - 150, 300, 300, 50)
    ip_box = InputBox(SCREEN_WIDTH//2 - 150, 400, 300, 50, '127.0.0.1') # Tambahkan input box untuk IP

    while running:
        screen.blit(assets['background'], (0,0))
        draw_text("Tag Arena", FONT_BOLD, WHITE, (SCREEN_WIDTH//2, 100))
        draw_text("Masukkan Username:", FONT_REGULAR, WHITE, (SCREEN_WIDTH//2, 260))
        draw_text("Alamat IP Server:", FONT_REGULAR, WHITE, (SCREEN_WIDTH//2, 370))


        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False; return "quit", None
            res_user = username_box.handle_event(event)
            res_ip = ip_box.handle_event(event)

            if (res_user == "enter" or res_ip == "enter") and len(username_box.text) > 2 and len(ip_box.text) > 6:
                return avatar_creation(username_box.text, ip_box.text)

        username_box.draw(screen)
        ip_box.draw(screen)
        pygame.display.flip()
        clock.tick(FPS)
    return "quit", None

def avatar_creation(username, server_ip):
    global running
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Tidak dapat membuka kamera, menggunakan avatar default.")
        return game_loop(username, assets['avatar_placeholder'], server_ip)

    capture_button = pygame.Rect(SCREEN_WIDTH//2 - 100, 520, 200, 50)

    while running:
        ret, frame = cap.read()
        if not ret:
             print("Gagal mengambil frame dari kamera.")
             return game_loop(username, assets['avatar_placeholder'], server_ip)

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.flip(frame, 1)
        frame_surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))

        cam_w, cam_h = frame_surface.get_size()
        scale = SCREEN_HEIGHT / cam_h
        scaled_w, scaled_h = int(cam_w * scale), int(cam_h * scale)
        frame_surface = pygame.transform.scale(frame_surface, (scaled_w, scaled_h))

        screen.fill(BLACK)
        screen.blit(frame_surface, (SCREEN_WIDTH//2 - scaled_w//2, 0))
        draw_text("Posisikan Wajah Anda", FONT_BOLD, WHITE, (SCREEN_WIDTH//2, 480))

        pygame.draw.rect(screen, GREEN, capture_button)
        draw_text("Ambil Foto", FONT_REGULAR, BLACK, capture_button.center)

        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False; break
            if event.type == pygame.MOUSEBUTTONDOWN and capture_button.collidepoint(event.pos):
                cap.release()
                center_x, center_y = frame.shape[1] // 2, frame.shape[0] // 2
                crop_size = min(center_x, center_y)
                cropped_frame = frame[center_y-crop_size:center_y+crop_size, center_x-crop_size:center_x+crop_size]
                final_avatar_surface = pygame.surfarray.make_surface(cropped_frame.swapaxes(0, 1))
                return game_loop(username, final_avatar_surface, server_ip)

        pygame.display.flip()
        clock.tick(FPS)

    cap.release()
    return "quit", None

def game_loop(username, avatar_surface, server_ip):
    global running, network, my_player_id, latest_game_state

    player_avatars.clear()

    network = Network(server_ip, SERVER_PORT) # Gunakan IP dari input
    if not network.is_connected():
        print("Gagal terhubung ke server.")
        return "menu"

    receive_thread = threading.Thread(target=receive_data_from_server, args=(network,), daemon=True)
    receive_thread.start()

    time.sleep(0.5)
    if my_player_id == -1:
        print("Tidak menerima ID dari server atau server penuh.")
        network.disconnect()
        return "menu"

    my_avatar = create_circular_avatar(avatar_surface, PLAYER_RADIUS * 2)
    player_avatars[my_player_id] = my_avatar

    img_byte_arr = io.BytesIO()
    pygame.image.save(avatar_surface, img_byte_arr, 'PNG')
    img_byte_arr_val = img_byte_arr.getvalue()

    network.send({'username': username, 'avatar_data': img_byte_arr_val})

    stun_frame = 0
    while running:
        with lock:
            current_state = latest_game_state.copy()

        use_item_event = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False; break
            if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE: use_item_event = True

        if current_state and current_state.get('game_started', False):
            keys = pygame.key.get_pressed()
            move_x, move_y = 0, 0
            if keys[pygame.K_w] or keys[pygame.K_UP]: move_y -= 1
            if keys[pygame.K_s] or keys[pygame.K_DOWN]: move_y += 1
            if keys[pygame.K_a] or keys[pygame.K_LEFT]: move_x -= 1
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]: move_x += 1

            mag = (move_x**2 + move_y**2)**0.5
            if mag > 0: move_x /= mag; move_y /= mag

            network.send({'move_x': move_x, 'move_y': move_y, 'use_item': use_item_event})
        else:
             network.send({})

        screen.blit(assets['background'], (0,0))

        if not current_state:
            draw_text("Menghubungkan & menunggu data...", FONT_BOLD, WHITE, (SCREEN_WIDTH//2, SCREEN_HEIGHT//2))
        elif current_state.get('winner'):
            draw_text("Game Selesai!", FONT_LARGE, YELLOW, (SCREEN_WIDTH//2, 150))
            winner_name = current_state.get('winner', 'Tidak ada')
            draw_text(f"Pemenang: {winner_name}", FONT_BOLD, WHITE, (SCREEN_WIDTH//2, 250))
            draw_hud(current_state)
            draw_text("Kembali ke lobi sebentar lagi...", FONT_REGULAR, WHITE, (SCREEN_WIDTH//2, 400))
        elif not current_state.get('game_started', False):
            draw_text("Menunggu Pemain Lain...", FONT_BOLD, WHITE, (SCREEN_WIDTH//2, 100))
            players = current_state.get('players', {})
            draw_text(f"{len(players)}/{MAX_PLAYERS}", FONT_REGULAR, WHITE, (SCREEN_WIDTH//2, 150))

            # **PERBAIKAN DI SINI**: Loop menggunakan pid (angka) langsung
            for i, (pid, pdata) in enumerate(players.items()):
                y_pos = 250 + i * 80
                avatar = player_avatars.get(pid)
                if avatar: screen.blit(avatar, (200, y_pos - PLAYER_RADIUS))
                draw_text(pdata.get('username', '...'), FONT_REGULAR, WHITE, (350, y_pos))
        else:
            for item in current_state.get('items',[]):
                icon = assets.get(item['type'])
                if icon: screen.blit(icon, (item['pos'][0] - ITEM_RADIUS, item['pos'][1] - ITEM_RADIUS))

            # **PERBAIKAN DI SINI**: Loop menggunakan pid (angka) langsung
            for pid, pdata in current_state.get('players', {}).items():
                pos = (int(pdata['pos'][0]), int(pdata['pos'][1]))
                p_avatar = player_avatars.get(pid)

                if pdata['speed'] > PLAYER_SPEED:
                    aura_rect = assets['speed_aura'].get_rect(center=pos)
                    screen.blit(assets['speed_aura'], aura_rect.topleft)

                if p_avatar:
                    avatar_rect = p_avatar.get_rect(center=pos)
                    screen.blit(p_avatar, avatar_rect.topleft)

                draw_text(pdata.get('username', ''), FONT_REGULAR, WHITE, (pos[0], pos[1] + PLAYER_RADIUS + 10))

                if pdata.get('is_it', False):
                    pygame.draw.circle(screen, RED, pos, PLAYER_RADIUS + 5, 3)
                if pdata.get('stunned', False):
                    stun_w, stun_h = assets['stun_stars'].get_size()
                    frame_width = stun_w / 3
                    stun_asset_rect = pygame.Rect(int(stun_frame) * frame_width, 0, frame_width, stun_h)

                    blit_pos_x = pos[0] - frame_width / 2
                    blit_pos_y = pos[1] - PLAYER_RADIUS - stun_h/2 - 5
                    screen.blit(assets['stun_stars'], (blit_pos_x, blit_pos_y), stun_asset_rect)

            stun_frame = (stun_frame + 0.2) % 3
            draw_hud(current_state)

        pygame.display.flip()
        clock.tick(FPS)

    if network:
        network.disconnect()
    return "menu"

def draw_hud(state):
    # **PERBAIKAN DI SINI**: Mengakses dictionary players dengan my_player_id (angka), bukan string.
    my_player_data = state.get('players', {}).get(my_player_id)

    if my_player_data:
        inventory_rect = pygame.Rect(10, SCREEN_HEIGHT - 60, 50, 50)
        pygame.draw.rect(screen, TRANSPARENT_GRAY, inventory_rect, border_radius=5)
        if my_player_data.get('inventory'):
            icon = assets.get(my_player_data['inventory'])
            if icon:
                icon_rect = icon.get_rect(center=inventory_rect.center)
                screen.blit(icon, icon_rect.topleft)
        pygame.draw.rect(screen, WHITE, inventory_rect, 2, border_radius=5)

    players_sorted = sorted(state.get('players', {}).values(), key=lambda p: p['score'], reverse=True)
    scoreboard_height = 70 + len(players_sorted) * 25
    scoreboard_surf = pygame.Surface((200, scoreboard_height), pygame.SRCALPHA)
    scoreboard_surf.fill(TRANSPARENT_GRAY)

    game_time = state.get('game_time', 0)
    minutes = int(game_time // 60)
    seconds = int(game_time % 60)
    time_text = f"Sisa Waktu: {minutes:02}:{seconds:02}"
    time_render = FONT_REGULAR.render(time_text, True, WHITE)
    scoreboard_surf.blit(time_render, (scoreboard_surf.get_width()//2 - time_render.get_width()//2, 5))

    title = FONT_REGULAR.render("Papan Skor", True, YELLOW)
    scoreboard_surf.blit(title, (scoreboard_surf.get_width()//2 - title.get_width()//2, 35))

    for i, pdata in enumerate(players_sorted):
        p_text = f"{i+1}. {pdata.get('username', '')}: {pdata.get('score', 0)}"
        p_render = FONT_REGULAR.render(p_text, True, WHITE)
        scoreboard_surf.blit(p_render, (10, 65 + i * 25))

    screen.blit(scoreboard_surf, (SCREEN_WIDTH - 210, 10))


# --- Main Execution ---
if __name__ == "__main__":
    load_assets()
    scene_result = "menu"
    server_ip_from_menu = "127.0.0.1" # Default IP
    while running:
        if scene_result == "menu":
            scene_result, server_ip_from_menu = main_menu()
        elif scene_result == "quit":
            running = False
    pygame.quit()