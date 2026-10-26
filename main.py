import math
import pygame

# ---------------- Configuração ----------------
TILE = 16
VIEW_W, VIEW_H = 256, 240
SCALE = 3
FPS = 60

# ---------------- Física (ajuste os valores aqui) ----------------
ACCEL_GROUND = 0.09
ACCEL_AIR = 0.07
SKID = 0.22              # freada rápida ao virar de direção
FRICTION = 0.06
WALK_MAX = 1.45
RUN_MAX = 2.65
GRAVITY = 0.38
GRAVITY_HOLD = 0.20      # gravidade menor enquanto segura o pulo
MAX_FALL = 4.6
JUMP_BASE = -4.4
JUMP_RUN_BONUS = -0.9    # correndo, o pulo fica mais alto
JUMP_HOLD_FRAMES = 14
WALKER_SPEED = 0.5
SHELL_SPEED = 3.0

# ---------------- Cores ----------------
SKY = (92, 148, 252)
CLOUD = (252, 252, 252)
HILL = (0, 168, 0)
HILL_DARK = (0, 110, 0)
GROUND = (176, 96, 40)
GROUND_DARK = (88, 44, 12)
BRICK = (200, 76, 12)
BRICK_DARK = (110, 36, 0)
QBLOCK = (252, 188, 60)
QBLOCK_DARK = (150, 80, 0)
USED = (120, 90, 60)
PIPE = (0, 168, 0)
PIPE_LIGHT = (120, 232, 88)
PIPE_DARK = (0, 72, 0)
COIN = (252, 216, 0)
COIN_DARK = (168, 100, 0)
POLE = (190, 190, 190)
WALKER = (150, 80, 30)
WALKER_DARK = (60, 28, 0)
SHELL = (0, 160, 40)
SHELL_LIGHT = (120, 230, 120)
MUSH_RED = (216, 40, 0)
MUSH_SKIN = (252, 200, 150)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

SOLID = set('#BP?U')

PLAYER_ROWS = [
    "...rrrrr....",
    "..rrrrrrrr..",
    "..ssksssss..",
    ".ssksssskss.",
    ".ssssssssss.",
    "..sssssss...",
    "..rrbbbbrr..",
    ".rrrbbbbrrr.",
    "ssrbbbbbbrss",
    "sssbbbbbbsss",
    "ssbbbbbbbbss",
    "..bbb..bbb..",
    ".nnn....nnn.",
    ".nnnn..nnnn.",
]
PLAYER_PAL = {
    'r': (216, 40, 0),
    's': (252, 152, 56),
    'k': (0, 0, 0),
    'b': (0, 0, 180),
    'n': (110, 60, 20),
}

_sprite_cache = {}


def player_sprite(big, facing):
    key = (big, facing)
    if key not in _sprite_cache:
        rows = PLAYER_ROWS
        if big:
            rows = rows[:10] + rows[8:10] * 3 + rows[10:]
        surf = pygame.Surface((12, len(rows)), pygame.SRCALPHA)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in PLAYER_PAL:
                    surf.set_at((x, y), PLAYER_PAL[ch])
        if facing < 0:
            surf = pygame.transform.flip(surf, True, False)
        _sprite_cache[key] = surf
    return _sprite_cache[key]


# ---------------- Mapa ----------------
def build_level():
    W, H = 200, 15
    g = [['.'] * W for _ in range(H)]

    gaps = (set(range(68, 70)) | set(range(86, 89)) | set(range(120, 122))
            | set(range(150, 152)) | set(range(165, 168)))
    for x in range(W):
        if x not in gaps:
            g[13][x] = '#'
            g[14][x] = '#'

    def pipe(x, h):
        for y in range(13 - h, 13):
            g[y][x] = 'P'
            g[y][x + 1] = 'P'

    for x, h in ((28, 2), (46, 3), (58, 2), (110, 2), (136, 3), (156, 2)):
        pipe(x, h)

    for x, c in ((16, 'B'), (17, '?'), (18, 'B'), (19, '?'), (20, 'B'), (24, '?')):
        g[10][x] = c

    for x in range(100, 104):
        g[9][x] = 'B'
    g[9][101] = '?'

    for x in range(34, 39):
        g[11][x] = 'o'
    for x in range(62, 67):
        g[10][x] = 'o'
    for x in range(130, 135):
        g[10][x] = 'o'

    # Escadaria de subida e descida
    for i in range(8):
        for y in range(12 - i, 13):
            g[y][174 + i] = '#'
    for x in (182, 183):
        for y in range(5, 13):
            g[y][x] = '#'
    for i in range(7):
        for y in range(6 + i, 13):
            g[y][184 + i] = '#'

    # Mastro da bandeira
    for y in range(3, 13):
        g[y][193] = 'F'

    contents = {(24, 10): 'mush'}   # bloco que solta cogumelo
    spawns = [(tx, 'walker') for tx in (22, 40, 52, 66, 80, 100, 112, 128, 144, 160, 172)]
    spawns += [(tx, 'turtle') for tx in (56, 90, 132, 148)]
    return g, contents, spawns


class Level:
    def __init__(self):
        self.grid, self.contents, self.enemy_spawns = build_level()
        self.rows = len(self.grid)
        self.cols = len(self.grid[0])
        self.bumps = {}   # blocos que estão "pulando" ao serem batidos

    def get(self, tx, ty):
        if 0 <= ty < self.rows and 0 <= tx < self.cols:
            return self.grid[ty][tx]
        return '.'

    def is_solid(self, tx, ty):
        if tx < 0 or tx >= self.cols:
            return True
        if ty < 0 or ty >= self.rows:
            return False
        return self.grid[ty][tx] in SOLID

    def tick_bumps(self):
        for pos in list(self.bumps):
            self.bumps[pos] -= 1
            if self.bumps[pos] <= 0:
                del self.bumps[pos]


# ---------------- Física e colisão ----------------
class Body:
    def __init__(self, x, y, w, h):
        self.x = float(x)
        self.y = float(y)
        self.w = w
        self.h = h
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = False
        self.hit_wall = False
        self.bump_tile = None

    def rect(self):
        return pygame.Rect(round(self.x), round(self.y), self.w, self.h)


def covered_tiles(b):
    tx0 = math.floor(b.x) // TILE
    tx1 = (math.ceil(b.x + b.w) - 1) // TILE
    ty0 = math.floor(b.y) // TILE
    ty1 = (math.ceil(b.y + b.h) - 1) // TILE
    return [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]


def solid_hits(b, level):
    return [(tx, ty) for tx, ty in covered_tiles(b) if level.is_solid(tx, ty)]


def move_x(b, level):
    b.hit_wall = False
    b.x += b.vx
    hits = solid_hits(b, level)
    if hits:
        b.hit_wall = True
        if b.vx > 0:
            b.x = min(tx for tx, _ in hits) * TILE - b.w
        elif b.vx < 0:
            b.x = (max(tx for tx, _ in hits) + 1) * TILE


def move_y(b, level):
    b.on_ground = False
    b.bump_tile = None
    b.y += b.vy
    hits = solid_hits(b, level)
    if not hits:
        return
    top = min(ty for _, ty in hits)
    if b.vy > 0:
        b.y = top * TILE - b.h
        b.vy = 0.0
        b.on_ground = True
    elif b.vy < 0:
        b.y = (top + 1) * TILE
        b.vy = 0.0
        cx = b.x + b.w / 2
        row = [(tx, ty) for tx, ty in hits if ty == top]
        b.bump_tile = min(row, key=lambda t: abs(t[0] * TILE + TILE / 2 - cx))


def approach(value, target, step):
    if value < target:
        return min(value + step, target)
    return max(value - step, target)


# ---------------- Personagem ----------------
class Player(Body):
    def __init__(self, x, y):
        super().__init__(x, y, 10, 14)
        self.big = False
        self.facing = 1
        self.jump_timer = 0
        self.invuln = 0

    def set_big(self, big):
        if big == self.big:
            return
        if big:
            self.y -= 6
            self.h = 20
        else:
            self.y += 6
            self.h = 14
        self.big = big

    def update(self, level, left, right, run, jump_pressed, jump_held):
        max_speed = RUN_MAX if run else WALK_MAX
        accel = ACCEL_GROUND if self.on_ground else ACCEL_AIR

        if right and not left:
            self.facing = 1
            if self.vx < 0:
                self.vx += SKID
            else:
                self.vx = approach(self.vx, max_speed, accel)
        elif left and not right:
            self.facing = -1
            if self.vx > 0:
                self.vx -= SKID
            else:
                self.vx = approach(self.vx, -max_speed, accel)
        elif self.on_ground:
            self.vx = approach(self.vx, 0.0, FRICTION)

        if jump_pressed and self.on_ground:
            self.vy = JUMP_BASE + JUMP_RUN_BONUS * abs(self.vx) / RUN_MAX
            self.jump_timer = JUMP_HOLD_FRAMES

        if self.jump_timer > 0 and jump_held and self.vy < 0:
            gravity = GRAVITY_HOLD
            self.jump_timer -= 1
        else:
            gravity = GRAVITY
            self.jump_timer = 0

        self.vy = min(self.vy + gravity, MAX_FALL)
        move_x(self, level)
        if self.hit_wall:
            self.vx = 0.0
        move_y(self, level)


# ---------------- Inimigos e itens ----------------
class Enemy(Body):
    def __init__(self, tx, kind):
        h = 12 if kind == 'walker' else 14
        super().__init__(tx * TILE, 13 * TILE - h, 12, h)
        self.kind = kind
        self.state = 'walk'     # walk, squash, shell, shell_move, fall
        self.vx = -WALKER_SPEED
        self.timer = 0
        self.alive = True

    def update(self, level):
        if self.state == 'squash':
            self.timer -= 1
            if self.timer <= 0:
                self.alive = False
            return

        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        if self.state == 'walk':
            self.vx = math.copysign(WALKER_SPEED, self.vx)
        elif self.state in ('shell', 'fall'):
            self.vx = 0.0

        move_x(self, level)
        if self.hit_wall and self.state in ('walk', 'shell_move'):
            self.vx = -self.vx
        move_y(self, level)

        if self.y > level.rows * TILE:
            self.alive = False


class Mushroom(Body):
    def __init__(self, tx, ty):
        super().__init__(tx * TILE, (ty - 1) * TILE, 12, 12)
        self.vx = 0.8
        self.alive = True

    def update(self, level):
        self.vy = min(self.vy + GRAVITY, MAX_FALL)
        move_x(self, level)
        if self.hit_wall:
            self.vx = -self.vx
        move_y(self, level)
        if self.y > level.rows * TILE:
            self.alive = False


# ---------------- Estado do jogo ----------------
class Game:
    def __init__(self):
        self.score = 0
        self.coins = 0
        self.lives = 3
        self.new_level()

    def new_level(self):
        self.level = Level()
        self.player = Player(32, 13 * TILE - 14)
        self.enemies = [Enemy(tx, kind) for tx, kind in self.level.enemy_spawns]
        self.items = []
        self.cam_x = 0.0
        self.time_left = 400
        self.frame = 0
        self.death_timer = 0
        self.flag_timer = 0
        self.state = 'play'     # play, dying, flag, win, gameover

    def kill(self):
        if self.state != 'play':
            return
        self.lives -= 1
        self.state = 'dying'
        self.death_timer = 120
        self.player.vx = 0.0
        self.player.vy = -5.0

    def hurt(self):
        p = self.player
        if p.invuln > 0 or self.state != 'play':
            return
        if p.big:
            p.set_big(False)
            p.invuln = 90
        else:
            self.kill()

    def hit_block(self, tx, ty):
        lvl = self.level
        t = lvl.get(tx, ty)
        if t == 'B':
            if self.player.big:
                lvl.grid[ty][tx] = '.'
                self.score += 50
            else:
                lvl.bumps[(tx, ty)] = 8
        elif t == '?':
            lvl.grid[ty][tx] = 'U'
            lvl.bumps[(tx, ty)] = 8
            if (tx, ty) in lvl.contents:
                self.items.append(Mushroom(tx, ty))
            else:
                self.coins += 1
                self.score += 200

    def check_items(self):
        pr = self.player.rect()
        for it in self.items:
            if it.alive and pr.colliderect(it.rect()):
                it.alive = False
                self.score += 1000
                self.player.set_big(True)

    def check_enemies(self):
        p = self.player
        pr = p.rect()
        for e in self.enemies:
            if not e.alive or e.state in ('squash', 'fall'):
                continue
            er = e.rect()
            if not pr.colliderect(er):
                continue

            if p.vy > 0 and pr.bottom - er.top <= 8:     # pisou no inimigo
                if e.kind == 'walker':
                    e.state = 'squash'
                    e.timer = 25
                    e.vx = 0.0
                elif e.state == 'walk':
                    e.state = 'shell'
                    e.vx = 0.0
                elif e.state == 'shell':
                    e.state = 'shell_move'
                    e.vx = SHELL_SPEED if p.x + p.w / 2 < e.x + e.w / 2 else -SHELL_SPEED
                else:                                    # casco em movimento
                    e.state = 'shell'
                    e.vx = 0.0
                self.score += 100
                p.vy = -3.5
                continue

            if e.state == 'shell':                       # chutar o casco parado
                e.state = 'shell_move'
                e.vx = SHELL_SPEED if e.x + e.w / 2 >= p.x + p.w / 2 else -SHELL_SPEED
                continue

            self.hurt()
            return

    def check_shells(self):
        for s in self.enemies:
            if s.state != 'shell_move' or not s.alive:
                continue
            sr = s.rect()
            for e in self.enemies:
                if e is s or e.state != 'walk' or not e.alive:
                    continue
                if sr.colliderect(e.rect()):
                    e.state = 'fall'
                    e.vy = -3.0
                    self.score += 200

    def check_tiles(self):
        p = self.player
        for tx, ty in covered_tiles(p):
            t = self.level.get(tx, ty)
            if t == 'o':
                self.level.grid[ty][tx] = '.'
                self.coins += 1
                self.score += 200
            elif t == 'F':
                self.start_flag(tx)
                return

    def start_flag(self, tx):
        self.state = 'flag'
        self.player.x = tx * TILE + 3
        self.player.vx = 0.0
        self.player.vy = 0.0
        self.flag_timer = 0

    def update_flag(self):
        p = self.player
        floor = 13 * TILE - p.h
        if p.y < floor:
            p.y = min(p.y + 2, floor)
        else:
            self.flag_timer += 1
            if self.flag_timer == 1:
                self.score += self.time_left * 50
            if self.flag_timer >= 90:
                self.state = 'win'

    def update_dying(self):
        p = self.player
        p.vy = min(p.vy + GRAVITY, MAX_FALL)
        p.y += p.vy
        self.death_timer -= 1
        if self.death_timer <= 0:
            if self.lives <= 0:
                self.state = 'gameover'
            else:
                self.new_level()

    def update_camera(self):
        target = self.player.x - VIEW_W * 0.4
        self.cam_x = max(self.cam_x, target)
        self.cam_x = min(self.cam_x, self.level.cols * TILE - VIEW_W)

    def update(self, left, right, run, jump_pressed, jump_held):
        if self.state == 'dying':
            self.update_dying()
            return
        if self.state == 'flag':
            self.update_flag()
            return
        if self.state != 'play':
            return

        self.frame += 1
        if self.frame % FPS == 0:
            self.time_left -= 1
            if self.time_left <= 0:
                self.kill()
                return

        p = self.player
        if p.invuln > 0:
            p.invuln -= 1
        p.update(self.level, left, right, run, jump_pressed, jump_held)
        if p.bump_tile is not None:
            self.hit_block(*p.bump_tile)

        for it in self.items:
            it.update(self.level)
        for e in self.enemies:
            e.update(self.level)

        self.check_items()
        self.check_enemies()
        self.check_shells()
        self.enemies = [e for e in self.enemies if e.alive]
        self.items = [i for i in self.items if i.alive]

        if self.state == 'play':
            self.check_tiles()
        if self.state == 'play' and p.y > self.level.rows * TILE:
            self.kill()

        self.update_camera()
        self.level.tick_bumps()


# ---------------- Desenho ----------------
def draw_cloud(surf, x, y):
    pygame.draw.ellipse(surf, CLOUD, (x, y + 8, 44, 16))
    pygame.draw.ellipse(surf, CLOUD, (x + 12, y, 28, 18))


def draw_background(surf, cam):
    surf.fill(SKY)
    for x0 in range(0, 3200, 240):
        x = x0 - int(cam * 0.7)
        if -120 < x < VIEW_W + 120:
            pygame.draw.ellipse(surf, HILL_DARK, (x - 4, 156, 104, 56))
            pygame.draw.ellipse(surf, HILL, (x, 160, 96, 48))
    for x0 in range(0, 3200, 170):
        x = x0 - int(cam * 0.4)
        if -60 < x < VIEW_W + 60:
            draw_cloud(surf, x, 40)


def draw_tiles(surf, level, cam):
    cam = int(cam)
    first = max(0, cam // TILE)
    last = min(level.cols, (cam + VIEW_W) // TILE + 2)
    for ty in range(level.rows):
        for tx in range(first, last):
            t = level.grid[ty][tx]
            if t == '.':
                continue
            x = tx * TILE - cam
            y = ty * TILE
            if (tx, ty) in level.bumps:
                y -= 4
            r = pygame.Rect(x, y, TILE, TILE)

            if t == '#':
                pygame.draw.rect(surf, GROUND, r)
                pygame.draw.rect(surf, GROUND_DARK, r, 1)
                pygame.draw.line(surf, GROUND_DARK, (x, y + 8), (x + TILE - 1, y + 8))
            elif t == 'B':
                pygame.draw.rect(surf, BRICK, r)
                pygame.draw.rect(surf, BRICK_DARK, r, 1)
                pygame.draw.line(surf, BRICK_DARK, (x, y + 8), (x + TILE - 1, y + 8))
                pygame.draw.line(surf, BRICK_DARK, (x + 8, y), (x + 8, y + 7))
            elif t == '?':
                pygame.draw.rect(surf, QBLOCK, r)
                pygame.draw.rect(surf, QBLOCK_DARK, r, 2)
                pygame.draw.rect(surf, BLACK, (x + 5, y + 3, 6, 2))
                pygame.draw.rect(surf, BLACK, (x + 9, y + 5, 2, 3))
                pygame.draw.rect(surf, BLACK, (x + 7, y + 8, 2, 2))
                pygame.draw.rect(surf, BLACK, (x + 7, y + 11, 2, 2))
            elif t == 'U':
                pygame.draw.rect(surf, USED, r)
                pygame.draw.rect(surf, BLACK, r, 1)
            elif t == 'P':
                pygame.draw.rect(surf, PIPE, r)
                pygame.draw.rect(surf, PIPE_LIGHT, (x + 2, y, 3, TILE))
                pygame.draw.rect(surf, PIPE_DARK, r, 1)
            elif t == 'o':
                pygame.draw.ellipse(surf, COIN_DARK, (x + 4, y + 1, 8, 14))
                pygame.draw.ellipse(surf, COIN, (x + 5, y + 2, 6, 12))
            elif t == 'F':
                pygame.draw.rect(surf, POLE, (x + 7, y, 2, TILE))
                if ty == 3:
                    pygame.draw.polygon(surf, MUSH_RED, [(x + 9, y + 2), (x + 16, y + 5), (x + 9, y + 8)])


def draw_enemy(surf, e, cam):
    x = round(e.x) - int(cam)
    y = round(e.y)
    if e.kind == 'walker':
        if e.state == 'squash':
            pygame.draw.rect(surf, WALKER_DARK, (x, y + 8, 12, 4))
            return
        pygame.draw.ellipse(surf, WALKER, (x, y, 12, 9))
        pygame.draw.rect(surf, WHITE, (x + 2, y + 2, 3, 3))
        pygame.draw.rect(surf, WHITE, (x + 7, y + 2, 3, 3))
        pygame.draw.rect(surf, BLACK, (x + 3, y + 3, 1, 2))
        pygame.draw.rect(surf, BLACK, (x + 8, y + 3, 1, 2))
        pygame.draw.rect(surf, WALKER_DARK, (x, y + 9, 12, 3))
    else:
        if e.state in ('shell', 'shell_move'):
            pygame.draw.ellipse(surf, SHELL, (x, y, 12, 14))
            pygame.draw.ellipse(surf, SHELL_LIGHT, (x + 3, y + 2, 6, 4))
        else:
            pygame.draw.ellipse(surf, SHELL, (x, y + 3, 12, 11))
            pygame.draw.rect(surf, SHELL_LIGHT, (x + 8, y, 5, 6))
            pygame.draw.rect(surf, BLACK, (x + 10, y + 2, 1, 1))


def draw_mushroom(surf, m, cam):
    x = round(m.x) - int(cam)
    y = round(m.y)
    pygame.draw.ellipse(surf, MUSH_RED, (x, y, 12, 8))
    pygame.draw.rect(surf, WHITE, (x + 2, y + 2, 3, 3))
    pygame.draw.rect(surf, WHITE, (x + 7, y + 2, 3, 3))
    pygame.draw.rect(surf, MUSH_SKIN, (x + 3, y + 7, 6, 5))


def draw_player(surf, p, cam):
    if p.invuln > 0 and (p.invuln // 4) % 2 == 0:
        return                      # pisca enquanto está invulnerável
    sprite = player_sprite(p.big, p.facing)
    surf.blit(sprite, (round(p.x) - int(cam) - 1, round(p.y)))


def draw_hud(surf, game, font):
    entries = [
        (10, 6, "PONTOS"), (10, 16, f"{game.score:06d}"),
        (100, 6, "MOEDAS"), (100, 16, f"x{game.coins:02d}"),
        (160, 6, "MUNDO"), (160, 16, "1-1"),
        (200, 6, "TEMPO"), (200, 16, f"{game.time_left:03d}"),
        (10, 226, f"VIDAS x{game.lives}"),
    ]
    for x, y, text in entries:
        surf.blit(font.render(text, False, WHITE), (x, y))


def draw_overlay(surf, big, font, title, subtitle):
    shade = pygame.Surface((VIEW_W, VIEW_H), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 150))
    surf.blit(shade, (0, 0))
    t = big.render(title, False, WHITE)
    s = font.render(subtitle, False, WHITE)
    surf.blit(t, t.get_rect(center=(VIEW_W // 2, VIEW_H // 2 - 8)))
    surf.blit(s, s.get_rect(center=(VIEW_W // 2, VIEW_H // 2 + 12)))


def draw(canvas, game, font, big):
    cam = game.cam_x
    draw_background(canvas, cam)
    draw_tiles(canvas, game.level, cam)
    for it in game.items:
        draw_mushroom(canvas, it, int(cam))
    for e in game.enemies:
        draw_enemy(canvas, e, int(cam))
    if game.state != 'gameover':
        draw_player(canvas, game.player, int(cam))
    draw_hud(canvas, game, font)

    if game.state == 'win':
        draw_overlay(canvas, big, font, "FASE CONCLUIDA", "ENTER para jogar de novo")
    elif game.state == 'gameover':
        draw_overlay(canvas, big, font, "FIM DE JOGO", "ENTER para recomecar")


# ---------------- Loop principal ----------------
def main():
    pygame.init()
    window = pygame.display.set_mode((VIEW_W * SCALE, VIEW_H * SCALE))
    pygame.display.set_caption("Plataforma 8-bit")
    canvas = pygame.Surface((VIEW_W, VIEW_H))
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 18)
    big = pygame.font.Font(None, 36)
    game = Game()
    paused = False

    running = True
    while running:
        jump_pressed = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_z, pygame.K_SPACE):
                    jump_pressed = True
                elif event.key == pygame.K_ESCAPE and game.state == 'play':
                    paused = not paused
                elif event.key == pygame.K_RETURN and game.state in ('gameover', 'win'):
                    game = Game()
                    paused = False

        keys = pygame.key.get_pressed()
        left = keys[pygame.K_LEFT]
        right = keys[pygame.K_RIGHT]
        run = keys[pygame.K_x] or keys[pygame.K_LSHIFT]
        jump_held = keys[pygame.K_z] or keys[pygame.K_SPACE]

        if not paused:
            game.update(left, right, run, jump_pressed, jump_held)
        draw(canvas, game, font, big)
        if paused:
            draw_overlay(canvas, big, font, "PAUSA", "ESC para continuar")

        pygame.transform.scale(canvas, window.get_size(), window)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()